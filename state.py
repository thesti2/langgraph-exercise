"""Graph state. TODO (M1): define the fields your nodes read and write."""

import operator
from typing import Annotated, TypedDict, Literal
from pydantic import BaseModel, Field

class RefundState(TypedDict, total=False):
    # --- input ---
    ticket_id: str
    customer_email: str
    message: str  # the customer's message (you may append their answers from ask_customer)

    # extracted request (order_id, reason, damaged, ...)
    refund_request: Request
    # order + customer data from lookup_order
    order: dict | None
    customer: dict 
    # policy result (recommendation, amount, method, reasons, needs_review)
    policy_result: RefundRecommendation
    # reviewer decision
    decision: dict       # {"action": "approve"} | {"action": "edit", "amount": 60.0, "method": "store_credit"} | {"action": "reject", "reason": "..."}
    # refund result
    refund_result: dict | None
    # email draft (subject, body)
    email_draft: Email
    email_review: Literal["send", "edit"]
    # (M5): audit_log: Annotated[list[dict], operator.add]
    audit_log: Annotated[list[dict], operator.add]

    ask_attempts: int


# Pydantic structure
class Request(BaseModel):
    """Claim Request model"""
    order_id: str | None = Field(default=None,description="order ID that want to be refunded")
    reason: str = Field(description="refund reason")
    damaged: bool = Field(default=False,description="boolean flag if the item is damaged")
    items: list[str] = Field(default_factory=list,description="List of item code (SKU). Example: MUG-01, BLN-PRO, JKT-RN")

class RefundRecommendation(BaseModel):
    """Recommendation decision for the refund request"""
    reason: str = Field(description="reasoning of why giving this recommendation")
    recommendation: Literal["approve", "reject"]
    amount: float = Field(description="refund amount")
    method: Literal["original_payment", "store_credit"]
    needs_review: bool = Field(description="does this refund request needs review by a human?")

class Email(BaseModel):
    """Email structure"""
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body")