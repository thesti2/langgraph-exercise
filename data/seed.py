"""Create and seed data/claims.db for the Claims Copilot exercise.

Run from the exercise2 folder:

    uv run data/seed.py            # creates data/claims.db (refuses if it exists)
    uv run data/seed.py --reset    # deletes and recreates it

Standard library only. Import `receipt_hash` from here in your claims tools so
the duplicate-receipt check hashes receipts exactly the way the seed data does.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("claims.db")


def receipt_hash(merchant: str, receipt_no: str) -> str:
    """Stable fingerprint of a receipt: sha256 of 'merchant|RECEIPT_NO' (normalised)."""
    key = f"{merchant.strip().lower()}|{receipt_no.strip().upper()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


SCHEMA = """
CREATE TABLE customers (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    email                TEXT NOT NULL,
    plan                 TEXT NOT NULL CHECK (plan IN ('Basic', 'Plus', 'Premier')),
    policy_start         TEXT NOT NULL,          -- ISO date
    policy_end           TEXT NOT NULL,          -- ISO date
    country_of_residence TEXT NOT NULL,
    preferred_language   TEXT NOT NULL DEFAULT 'en'
);

CREATE TABLE claims (
    id             TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL REFERENCES customers(id),
    type           TEXT NOT NULL CHECK (type IN ('flight_delay', 'baggage', 'cancellation', 'medical')),
    amount_claimed REAL NOT NULL,
    amount_paid    REAL NOT NULL DEFAULT 0,
    status         TEXT NOT NULL CHECK (status IN ('paid', 'denied', 'withdrawn', 'pending')),
    receipt_hash   TEXT,                         -- see receipt_hash(); NULL for delay claims
    summary        TEXT NOT NULL,
    created_at     TEXT NOT NULL                 -- ISO date the claim was submitted
);

CREATE TABLE payments (
    id              TEXT PRIMARY KEY,
    claim_id        TEXT NOT NULL REFERENCES claims(id),
    amount          REAL NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL
);

CREATE TABLE letters (
    id       TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(id),
    body     TEXT NOT NULL,
    sent_at  TEXT NOT NULL
);

CREATE INDEX idx_claims_customer ON claims(customer_id, created_at);
CREATE INDEX idx_claims_receipt  ON claims(receipt_hash);
"""

CUSTOMERS = [
    # id,     name,             email,                         plan,      start,        end,          country, lang
    ("C-001", "Aiko Tanaka",    "aiko.tanaka@example.com",     "Plus",    "2025-06-01", "2026-12-31", "US", "en"),
    ("C-002", "Ben Okafor",     "ben.okafor@example.com",      "Basic",   "2025-06-01", "2026-12-31", "US", "en"),
    ("C-003", "Clara Jensen",   "clara.jensen@example.com",    "Premier", "2025-06-01", "2026-12-31", "US", "en"),
    ("C-004", "Diego Ramos",    "diego.ramos@example.com",     "Plus",    "2025-06-01", "2026-12-31", "US", "es"),
    ("C-005", "Elif Yilmaz",    "elif.yilmaz@example.com",     "Basic",   "2025-06-01", "2026-12-31", "US", "en"),
    ("C-006", "Farah Haddad",   "farah.haddad@example.com",    "Plus",    "2025-06-01", "2026-12-31", "US", "en"),
    ("C-007", "Grant Miller",   "grant.miller@example.com",    "Plus",    "2025-06-01", "2026-12-31", "US", "en"),
    ("C-008", "Hana Kim",       "hana.kim@example.com",        "Premier", "2025-06-01", "2026-12-31", "US", "en"),
    ("C-009", "Ivan Petrov",    "ivan.petrov@example.com",     "Basic",   "2025-06-01", "2026-12-31", "US", "en"),
    ("C-010", "Julia Santos",   "julia.santos@example.com",    "Plus",    "2025-06-01", "2026-12-31", "US", "pt"),
]

# Historical claims. Receipts are given as (merchant, receipt_no) and hashed below.
# Notes for the exercise:
#   * C-007 has three baggage claims in the 12 months before eval case E09 (their 4th).
#   * CL-25-0087's receipt (ElectroHub Lisbon / EH-58821) is reused by eval case E10.
HISTORICAL_CLAIMS = [
    # id,           customer, type,           claimed, paid,   status,      receipt,                                   summary,                                                        created_at
    ("CL-25-0031", "C-001", "flight_delay",   200,     200,    "paid",      None,                                      "13 h delay LIS-JFK, technical fault. 2 periods.",              "2025-09-12"),
    ("CL-25-0044", "C-003", "baggage",        640,     640,    "paid",      ("TravelGear Porto", "TG-1201"),           "Lost suitcase Porto, clothes and shoes. PIR supplied.",        "2025-10-02"),
    ("CL-25-0087", "C-002", "baggage",        450,     270,    "paid",      ("ElectroHub Lisbon", "EH-58821"),         "Lost bag Lisbon: smartwatch. Paid at Basic per-item limit.",   "2025-10-20"),
    ("CL-25-0102", "C-004", "medical",        1900,    1850,   "paid",      ("Clinica Sol Malaga", "CSM-77310"),       "Sprained ankle, ER visit and X-ray in Malaga.",                "2025-11-08"),
    ("CL-25-0119", "C-007", "baggage",        460,     410,    "paid",      ("UrbanStep Shoes Denver", "US-40192"),    "Lost bag Denver: shoes and jacket. PIR supplied.",             "2025-12-05"),
    ("CL-25-0126", "C-006", "flight_delay",   100,     100,    "paid",      None,                                      "7 h delay LHR-BOS, crew shortage. 1 period.",                  "2025-12-19"),
    ("CL-26-0008", "C-005", "flight_delay",   50,      0,      "denied",    None,                                      "9 h delay, strike announced 6 days before. DLY-2.",            "2026-01-15"),
    ("CL-26-0014", "C-008", "cancellation",   2400,    2400,   "paid",      ("Hotel Aurora Kyoto", "HA-2291"),         "Cancelled Kyoto trip, death of grandparent. Premier, $0 ded.", "2026-01-28"),
    ("CL-26-0023", "C-007", "baggage",        415,     365,    "paid",      ("SoundWave Electronics", "SW-88213"),     "Lost bag Chicago: earbuds and charger. PIR supplied.",         "2026-02-22"),
    ("CL-26-0031", "C-010", "medical",        370,     320,    "paid",      ("Farmacia Central Lima", "FCL-1180"),     "Food poisoning in Lima, clinic visit and medication.",         "2026-03-03"),
    ("CL-26-0040", "C-009", "baggage",        380,     0,      "denied",    ("Outdoor Depot Oslo", "OD-5521"),         "Lost bag Oslo, no PIR obtained. BAG-3.",                       "2026-03-17"),
    ("CL-26-0047", "C-001", "medical",        240,     0,      "withdrawn", ("Hospital da Luz Lisboa", "HL-90017"),    "Withdrawn by customer, costs covered by employer insurance.",  "2026-04-02"),
    ("CL-26-0052", "C-007", "baggage",        340,     290,    "paid",      ("Northside Outfitters", "NO-31877"),      "Lost bag Seattle: rain jacket and fleece. PIR supplied.",      "2026-04-30"),
    ("CL-26-0061", "C-003", "flight_delay",   300,     300,    "paid",      None,                                      "14 h delay CDG-JFK, weather. 2 periods at Premier rate.",      "2026-05-06"),
    ("CL-26-0066", "C-002", "flight_delay",   50,      50,     "paid",      None,                                      "6 h 20 m delay ORD-MEX, technical fault. 1 period.",           "2026-05-21"),
]


def seed(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)", CUSTOMERS)

    for cid, cust, ctype, claimed, paid, status, receipt, summary, created in HISTORICAL_CLAIMS:
        rhash = receipt_hash(*receipt) if receipt else None
        conn.execute(
            "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, cust, ctype, claimed, paid, status, rhash, summary, created),
        )
        if status == "paid":
            conn.execute(
                "INSERT INTO payments VALUES (?, ?, ?, ?, ?)",
                (f"PAY-{cid}", cid, paid, f"{cid}:v1", created),
            )
            conn.execute(
                "INSERT INTO letters VALUES (?, ?, ?, ?)",
                (f"LTR-{cid}", cid, f"Your claim {cid} has been approved. Amount paid: ${paid:,.2f}.", created),
            )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="delete the existing database first")
    args = parser.parse_args()

    if DB_PATH.exists():
        if not args.reset:
            raise SystemExit(f"{DB_PATH} already exists. Use --reset to recreate it.")
        DB_PATH.unlink()

    with sqlite3.connect(DB_PATH) as conn:
        seed(conn)
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("customers", "claims", "payments", "letters")}
    print(f"Created {DB_PATH}: " + ", ".join(f"{n} {t}" for t, n in counts.items()))


if __name__ == "__main__":
    main()
