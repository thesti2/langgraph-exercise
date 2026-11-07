"""Check check_policy against every order, without the LLM or the graph.

    uv run test_policy.py
"""

import sys
from nodes import check_policy
import orders
from state import Request, RefundRecommendation, RefundState

# (order_id, damaged, expected recommendation, amount, method, needs_review)
# amount/method are None where they don't matter (rejections).
CASES = [
    ("SF-1001", False, "approve", 18.0, "original_payment", False),  # <=30 days, small: auto-approve
    ("SF-1002", False, "approve", 449.0, "original_payment", True),  # > $100
    ("SF-1003", False, "approve", 120.0, "store_credit", True),  # 45 days -> store credit, > $100
    ("SF-1004", False, "reject", None, None, True),  # final sale
    ("SF-1005", False, "approve", 89.0, "original_payment", True),  # flagged customer (3 refunds)
    ("SF-1006", True, "approve", 129.0, "original_payment", True),  # damaged beats the 60-day limit
    ("SF-1006", False, "reject", None, None, True),  # same order, not damaged: 75 days -> reject
]


def build_state(order_id: str, damaged: bool) -> dict:
    """The state check_policy would see after extract_request + lookup_order.

    items=[] on purpose: that's what the LLM returns for real tickets.
    """
    order = orders.get_order(order_id)
    return {
        "refund_request": Request(order_id=order_id, reason="test", damaged=damaged, items=[]),
        "order": order,
        "customer": orders.get_customer(order["customer_email"]),
    }


def main() -> int:
    failures = 0
    for order_id, damaged, rec, amount, method, review in CASES:
        label = f"{order_id} damaged={damaged!s:5}"
        try:
            result = check_policy(build_state(order_id, damaged))["policy_result"]
            got = (result.recommendation, result.amount, result.method, result.needs_review)
        except Exception as e:
            print(f"FAIL {label}  crashed: {type(e).__name__}: {str(e).splitlines()[0]}")
            failures += 1
            continue

        want = (rec, amount, method, review)
        ok = all(w is None or w == g for w, g in zip(want, got))
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'} {label}  got={got}" + ("" if ok else f"  want={want}"))

    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
