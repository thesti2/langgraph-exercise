from langchain_core.tools import tool
from pathlib import Path
from dateutil.relativedelta import relativedelta
from datetime import datetime, date, timezone
from contextlib import closing
import importlib.util
import sqlite3

DATA_DIR = "data"

# Always resolves to the exact folder where this .py file is saved
DB_PATH = Path(__file__).parent.parent.parent / DATA_DIR / "claims.db"

# Reuse receipt_hash() from data/seed.py so our hashes match the seeded ones exactly.
# data/ is not a Python package, so load the module from its file path.
_seed_spec = importlib.util.spec_from_file_location("seed", DB_PATH.parent / "seed.py")
_seed = importlib.util.module_from_spec(_seed_spec)
_seed_spec.loader.exec_module(_seed)
receipt_hash = _seed.receipt_hash

@tool
def get_customer(customer_id: str) -> dict:
    """ Get information of a customer based on the given customer ID """

    with closing(sqlite3.connect(DB_PATH)) as conn:
        # Return rows as dictionary-like objects so we can convert to a dict
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Use '?' placeholder and pass (customer_id,) as a single-item tuple
        query = "SELECT id, plan, policy_start, policy_end FROM customers WHERE id = ?"
        cursor.execute(query, (customer_id,))
        
        row = cursor.fetchone()
        
        # Convert sqlite3.Row to a standard Python dict if found
        return dict(row) if row else {"errorMessage": f"Customer {customer_id} not found"} 

# parse_docstring can be used to describe the arguments. There is a strict format  to follow if we set this to true. Otherwise runtime will error "Found invalid Google-Style docstring"
@tool(parse_docstring=True)
def get_claim_history(customer_id: str, months: int = 12, as_of: str | None = None) -> list[dict] | dict:
    """Get list of claim history for the customer count back to number of months mentioned in the parameter from as_of (the claim's submitted_at)

    Args:
        customer_id: ID of the customer
        months: how many months back to check for claim history (default = 12)
        as_of: start date of the count back (submit the claim date), in ISO format, e.g. 2026-07-01T17:25:00Z or 2026-07-01
    """

    if months < 1:
        return {"errorMessage": f"months must be 1 or more, got {months}."}

    try:
        # AVOID SETTING as_of to TODAY, we always want to count from the submitted date
        # # if as_of is empty, count back from today
        # if as_of is None:
        #     dt = date.today()
        # else:
        #     # fromisoformat accepts "2026-07-01", "2026-07-01T17:25:00" and "2026-07-01T17:25:00Z" (Python 3.11+)
        #     dt = datetime.fromisoformat(as_of.strip()).date()

        dt = datetime.fromisoformat(as_of.strip()).date()
    except ValueError:
        return {"errorMessage": f"Invalid date format: '{as_of}'. Expected ISO format, e.g. 2026-07-01T17:25:00Z or 2026-07-01."}

    # months must be passed by keyword: relativedelta's first positional argument is a date (dt1), not months
    start_dt = dt - relativedelta(months=months)

    # created_at is stored as yyyy-MM-dd, so compare using the same format
    start_str = start_dt.isoformat()
    end_str = dt.isoformat()

    try:

        # Use '?' placeholder and pass (customer_id,) as a single-item tuple
        query = """SELECT * FROM claims 
                    WHERE customer_id = ?
                        AND created_at BETWEEN ? AND ?
                    ORDER BY created_at DESC"""

        with closing(sqlite3.connect(DB_PATH)) as conn:
            # Return rows as dictionary-like objects so we can convert to a dict
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (customer_id, start_str, end_str)).fetchall()
                        
            # Always returns a list[dict] (returns [] if no rows match)
            return [dict(row) for row in rows]

    except sqlite3.Error as e:
        # str(e): the exception object itself can't be serialised back to the model
        return {"errorMessage": str(e)}


@tool(parse_docstring=True)
def check_duplicate_receipt(merchant: str, receipt_no: str, exclude_claim_id: str | None = None) -> dict:
    """Check whether a receipt has already been used in an earlier claim (a fraud signal).

    Call this for every receipt or booking confirmation attached to a claim. For bookings, use the
    booking reference as the receipt number.

    Args:
        merchant: merchant name exactly as printed on the receipt, e.g. "ElectroHub Lisbon"
        receipt_no: receipt or booking number as printed, e.g. "EH-58821"
        exclude_claim_id: the current claim's ID, so the claim does not match itself once it is saved
    """

    if not merchant.strip() or not receipt_no.strip():
        return {"errorMessage": "Both merchant and receipt_no are required."}

    rhash = receipt_hash(merchant, receipt_no)

    query = """SELECT id, customer_id, type, status, created_at FROM claims
                WHERE receipt_hash = ?
                    AND (? IS NULL OR id != ?)
                ORDER BY created_at"""

    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (rhash, exclude_claim_id, exclude_claim_id)).fetchall()
    except sqlite3.Error as e:
        return {"errorMessage": str(e)}

    if not rows:
        return {"duplicate": False, "claim_id": None, "customer_id": None}

    # Report the earliest claim that used this receipt, plus every match for the fraud screener
    first = rows[0]
    return {
        "duplicate": True,
        "claim_id": first["id"],
        "customer_id": first["customer_id"],
        "created_at": first["created_at"],
        "matches": [dict(row) for row in rows],
    }


@tool(parse_docstring=True)
def send_letter(claim_id: str, body: str) -> dict:
    """Send the decision letter for a claim to the customer. Only the execute step may call this.

    Sending the same letter body for the same claim again does not send a second copy; it returns
    the letter that was already sent. This keeps the tool safe when a graph node is replayed.

    Args:
        claim_id: ID of the claim the letter is about, e.g. "CLM-26-0101"
        body: full text of the letter, already checked by the output guardrail
    """

    if not claim_id.strip():
        return {"errorMessage": "claim_id is required."}
    if not body.strip():
        return {"errorMessage": "Letter body is empty."}

    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row

            # Idempotency: same claim + same body means this letter was already sent
            existing = conn.execute(
                "SELECT id, sent_at FROM letters WHERE claim_id = ? AND body = ?",
                (claim_id, body),
            ).fetchone()
            if existing:
                return {"letter_id": existing["id"], "status": "already_sent", "sent_at": existing["sent_at"]}

            # Number letters per claim: LTR-<claim_id>-1, -2, ... (a claim can get a revised letter)
            count = conn.execute("SELECT COUNT(*) FROM letters WHERE claim_id = ?", (claim_id,)).fetchone()[0]
            letter_id = f"LTR-{claim_id}-{count + 1}"
            sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

            conn.execute(
                "INSERT INTO letters (id, claim_id, body, sent_at) VALUES (?, ?, ?, ?)",
                (letter_id, claim_id, body, sent_at),
            )
            # leaving the 'with' block commits the insert

        return {"letter_id": letter_id, "status": "sent", "sent_at": sent_at}

    except sqlite3.Error as e:
        return {"errorMessage": str(e)}

@tool(parse_docstring=True)
def issue_payment(claim_id: str, amount: float, idempotency_key: str) -> dict:
    """Issue a payment for the claim. Only the execute step may call this.

    Calling it again with the same idempotency_key never pays twice; it returns the existing payment.

    Args:
        claim_id: claim ID
        amount: amount to pay for the claim, in USD
        idempotency_key: idempotency key for duplicate checking, e.g. "CLM-26-0101:v1" (claim ID + decision version)
    """

    if not claim_id.strip() or not idempotency_key.strip():
        return {"errorMessage": "claim_id and idempotency_key are required."}
    if amount <= 0:
        return {"errorMessage": f"amount must be greater than 0, got {amount}."}

    # Derive the ID from the idempotency key, not the claim ID: a claim can be paid again under a
    # new key (e.g. a revised decision "...:v2") without colliding on the primary key, and a replay
    # with the same key always produces the same ID.
    payment_id = f"PAY-{idempotency_key}"
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    query = """
            INSERT INTO payments (id, claim_id, amount, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (idempotency_key) DO NOTHING
            """

    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, (payment_id, claim_id, amount, idempotency_key, created_at))

            if cursor.rowcount:
                return {"payment_id": payment_id, "status": "paid", "claim_id": claim_id,
                        "amount": amount, "created_at": created_at}

            # Nothing inserted: this key was used before. Return the payment that already exists.
            existing = conn.execute(
                "SELECT id, claim_id, amount, created_at FROM payments WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            result = {"payment_id": existing["id"], "status": "already_paid", "claim_id": existing["claim_id"],
                      "amount": existing["amount"], "created_at": existing["created_at"]}
            if existing["claim_id"] != claim_id or existing["amount"] != amount:
                # Same key, different request: a bug upstream. Surface it rather than hide it.
                result["warning"] = (f"idempotency_key was already used for {existing['claim_id']} "
                                     f"amount {existing['amount']}; this request was not paid.")
            return result

    except sqlite3.Error as e:
        return {"errorMessage": str(e)}



if __name__ == "__main__":
    customer = get_customer.invoke("C-001")
    print(customer)

    claim_list = get_claim_history.invoke(customer["id"])
    print(claim_list)

    # E10: this receipt was already used in historical claim CL-25-0087
    print(check_duplicate_receipt.invoke({"merchant": "ElectroHub Lisbon", "receipt_no": "EH-58821"}))
    print(check_duplicate_receipt.invoke({"merchant": "Sol Optics", "receipt_no": "SO-1934"}))