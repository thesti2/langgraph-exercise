"""Fake ShopFast back-office: orders, customers, refund ledger and email outbox.

This file is GIVEN — you don't need to change it. Treat these functions as the
"real systems" your agent talks to.
"""

from datetime import date, timedelta

# Fixed "today" so policy decisions are deterministic.
TODAY = date(2026, 11, 6)


def _days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


ORDERS: dict[str, dict] = {
    "SF-1001": {
        "customer_email": "maya@example.com",
        "items": [{"sku": "MUG-01", "name": "Ceramic mug", "price": 18.00, "final_sale": False}],
        "delivered_on": _days_ago(5),
    },
    "SF-1002": {
        "customer_email": "dan@example.com",
        "items": [{"sku": "LAP-14", "name": "14in Ultrabook", "price": 449.00, "final_sale": False}],
        "delivered_on": _days_ago(10),
    },
    "SF-1003": {
        "customer_email": "priya@example.com",
        "items": [{"sku": "JKT-RN", "name": "Rain jacket", "price": 120.00, "final_sale": False}],
        "delivered_on": _days_ago(45),
    },
    "SF-1004": {
        "customer_email": "leo@example.com",
        "items": [{"sku": "SNK-CL", "name": "Clearance sneakers", "price": 60.00, "final_sale": True}],
        "delivered_on": _days_ago(3),
    },
    "SF-1005": {
        "customer_email": "sam@example.com",
        "items": [{"sku": "HP-BT", "name": "Bluetooth headphones", "price": 89.00, "final_sale": False}],
        "delivered_on": _days_ago(12),
    },
    "SF-1006": {
        "customer_email": "ana@example.com",
        "items": [{"sku": "BLN-PRO", "name": "Pro blender", "price": 129.00, "final_sale": False}],
        "delivered_on": _days_ago(75),
    },
}

CUSTOMERS: dict[str, dict] = {
    "maya@example.com": {"refunds_last_90_days": 0},
    "dan@example.com": {"refunds_last_90_days": 1},
    "priya@example.com": {"refunds_last_90_days": 0},
    "leo@example.com": {"refunds_last_90_days": 0},
    "sam@example.com": {"refunds_last_90_days": 3},  # flagged: frequent refunder
    "ana@example.com": {"refunds_last_90_days": 0},
}

REFUND_LEDGER: list[dict] = []
OUTBOX: list[dict] = []


def get_order(order_id: str) -> dict | None:
    order = ORDERS.get(order_id.strip().upper())
    return None if order is None else {"order_id": order_id.strip().upper(), **order}


def get_customer(email: str) -> dict:
    return CUSTOMERS.get(email, {"refunds_last_90_days": 0})


def issue_refund(order_id: str, amount: float, method: str, idempotency_key: str) -> dict:
    """Issue a refund. `method` is "original_payment" or "store_credit".

    Like a real payment API, calling it again with the same idempotency_key
    returns the original refund instead of paying twice.
    """
    for entry in REFUND_LEDGER:
        if entry["idempotency_key"] == idempotency_key:
            print(f"  [payments] duplicate call ignored (key={idempotency_key})")
            return entry
    entry = {
        "refund_id": f"RF-{len(REFUND_LEDGER) + 1:04d}",
        "order_id": order_id,
        "amount": round(amount, 2),
        "method": method,
        "idempotency_key": idempotency_key,
    }
    REFUND_LEDGER.append(entry)
    print(f"  [payments] refunded ${entry['amount']:.2f} via {method} -> {entry['refund_id']}")
    return entry


def send_email(to: str, subject: str, body: str) -> None:
    OUTBOX.append({"to": to, "subject": subject, "body": body})
    print(f"  [email] sent to {to}: {subject!r}")
