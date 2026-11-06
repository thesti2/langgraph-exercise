"""Graph state. TODO (M1): define the fields your nodes read and write."""

from typing import TypedDict


class RefundState(TypedDict, total=False):
    # --- input ---
    ticket_id: str
    customer_email: str
    message: str  # the customer's message (you may append their answers from ask_customer)

    # TODO: extracted request (order_id, reason, damaged, ...)
    # TODO: order + customer data from lookup_order
    # TODO: policy result (recommendation, amount, method, reasons, needs_review)
    # TODO: reviewer decision
    # TODO: refund result
    # TODO: email draft (subject, body)
    # TODO (M5): audit_log: Annotated[list[dict], operator.add]