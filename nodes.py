"""Graph nodes. Each node takes RefundState and returns a partial state update
(or a Command). Replace every NotImplementedError.
"""

from langgraph.types import Command, interrupt  # noqa: F401  (you'll need these in M3)

import orders  # noqa: F401
from llm import llm  # noqa: F401
from state import RefundState


def extract_request(state: RefundState) -> dict:
    """LLM: pull order_id / reason / damaged / item_skus out of state["message"].

    Use llm.with_structured_output(<your Pydantic model>).
    """
    raise NotImplementedError


def ask_customer(state: RefundState) -> dict:
    """interrupt() with {"type": "ask_customer", "question": ...}.

    Append the customer's answer to the message so extract_request can try again.
    Guard against looping forever (e.g. max 2 attempts, then hand off to a human).
    """
    raise NotImplementedError


def lookup_order(state: RefundState) -> dict:
    """orders.get_order + orders.get_customer. Handle "order not found"."""
    raise NotImplementedError


def check_policy(state: RefundState) -> dict:
    """Deterministic refund policy from the README. No LLM here."""
    raise NotImplementedError


def human_review(state: RefundState) -> dict | Command:
    """interrupt() with the human_review payload. Handle approve / edit / reject.

    Remember: on resume this function runs again from the top.
    """
    raise NotImplementedError


def issue_refund(state: RefundState) -> dict:
    """orders.issue_refund(..., idempotency_key=...). Must be safe to re-run."""
    raise NotImplementedError


def draft_reply(state: RefundState) -> dict:
    """LLM: write a short, friendly email reflecting the FINAL decision
    (refunded amount + method, or the rejection reason)."""
    raise NotImplementedError


def review_reply(state: RefundState) -> dict:
    """interrupt() with {"type": "review_reply", ...}. Apply edits if any."""
    raise NotImplementedError


def send_reply(state: RefundState) -> dict:
    """orders.send_email(...)."""
    raise NotImplementedError
