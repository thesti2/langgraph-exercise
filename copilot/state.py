from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
import operator

# --------------------------------------------------------------------------------------------------
# State (move to copilot/state.py when it grows)
# --------------------------------------------------------------------------------------------------

class ClaimState(TypedDict, total=False):
    # Input
    claim_input: dict              # one eval row's "input": claim_id, customer_id, claim_type, submitted_at, trip, text, attachments

    # Input guardrail (M5)
    redacted_text: str             # claim text with PII replaced by [CARD_REDACTED] etc. The only text an LLM may see.
    pii_vault: dict[str, str]      # tag -> original value. NEVER put this in a prompt.
    blocked_reason: str | None     # set when the claim is blocked (prompt injection, off-topic)

    # Memory (M8)
    plan: str                      # "Basic" | "Plus" | "Premier". M11 changes this with update_state() to replay.
    customer_profile: dict         # from the store: ("customers", customer_id)
    lessons: list[str]             # promoted lessons from the store: ("lessons",)

    # Sub-agent outputs (M3, M4)
    facts: dict | None             # Extractor -> ClaimFacts
    coverage: dict | None          # Coverage Analyst -> CoverageFinding
    fraud: dict | None             # Fraud Screener -> FraudAssessment
    # The Extractor and Fraud Screener run in parallel. If both wrote to `fraud` in the same step, LangGraph would
    # raise InvalidUpdateError, so the Extractor's tool-output guardrail appends here instead (e.g.
    # "injection_in_attachment"). operator.add merges the lists from both branches.
    risk_flags: Annotated[list[str], operator.add]

    # Decision
    payout: dict                   # compute_payout: {"amount": float, "breakdown": [...]} (pure Python, M5 rule 1)
    draft: dict                    # draft_decision: {"decision", "payout", "citations", "letter"}
    guardrail_report: dict         # output_guardrail: {"passed": bool, "problems": [str]}
    retry_count: int               # number of failed output-guardrail checks

    # Human in the loop (M6) and execution (M7)
    review: dict | None            # adjuster's resume value: {"action", "payout", "letter", "note"}
    decision_version: int          # bump on every human edit, so the idempotency key changes with the decision
    executed: dict                 # {"payment": ..., "letter": ...}

    messages: Annotated[list[AnyMessage], add_messages]
