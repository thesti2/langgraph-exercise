"""Parent graph for the Claims Copilot (M2 skeleton).

Every node is a stub that returns fake but well-shaped output, so the graph runs end to end today.
Replace each TODO with real logic, one milestone at a time.

Run from the project root (the exercise2 folder):

    uv run python -m copilot.graph            # runs eval case E01
    uv run python -m copilot.graph E04        # runs another case

Rules this file is built around (EXERCISE.md section 5):
  * Nodes never touch claims.db directly. They call the @tool functions.
  * Only `execute` calls issue_payment / send_letter.
  * Keep state JSON-friendly (dict, list, str, int, float). If a sub-agent returns a Pydantic model, store
    `model.model_dump()` so the checkpointer can always save and load it.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt

from copilot.tools.claims import get_customer, issue_payment, send_letter  # noqa: F401  (used in TODOs)

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
DATASET_PATH = ROOT_DIR / "evals" / "claims_dataset.jsonl"
CHECKPOINT_DB = DATA_DIR / "checkpoints.db"

HUMAN_REVIEW_PAYOUT_LIMIT = 1000   # M6: payout above this needs an adjuster
MAX_DRAFT_RETRIES = 2              # M5: output guardrail sends the draft back at most this many times




# --------------------------------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------------------------------

def input_guardrail(state: ClaimState) -> dict:
    """M5: redact PII, detect prompt injection and off-topic text. Runs before any LLM sees the raw text."""
    text = state["claim_input"]["text"]

    # TODO M5:
    #   1. PII: find card numbers (Luhn check), passport numbers, emails, phones -> replace with tags,
    #      keep the originals in pii_vault.
    #   2. Injection: regex heuristics first (e.g. "ignore previous", "SYSTEM OVERRIDE"), then an LLM classifier
    #      on the *redacted* text. Set blocked_reason if it fires (E11).
    #   3. Off-topic / abusive: set blocked_reason (E21).
    return {
        "redacted_text": text,
        "pii_vault": {},
        "blocked_reason": None,
        "retry_count": 0,
        "decision_version": 1,
    }


def reject_with_reason(state: ClaimState) -> dict:
    """Polite refusal for a blocked claim. No payment, no supervisor."""
    # TODO M5: write a short, polite reply based on blocked_reason. Never echo the injected text back.
    return {
        "draft": {
            "decision": "blocked",
            "payout": 0,
            "citations": [],
            "letter": f"We could not process this request: {state.get('blocked_reason')}.",
        }
    }


def load_memory(state: ClaimState, runtime: Runtime) -> dict:
    """M8: load the customer's plan, their long-term profile and the promoted lessons."""
    customer_id = state["claim_input"]["customer_id"]

    # Plan comes from the claims system, through the tool (never a direct DB query).
    customer = get_customer.invoke({"customer_id": customer_id})
    plan = customer.get("plan", "Basic") if "errorMessage" not in customer else "Basic"

    profile, lessons = {}, []
    if runtime.store is not None:
        # TODO M8: read ("customers", customer_id) and the promoted lessons from ("lessons",).
        item = runtime.store.get(("customers", customer_id), "profile")
        profile = item.value if item else {}
        lessons = [
            it.value["text"]
            for it in runtime.store.search(("lessons",))
            if it.value.get("status") == "promoted"
        ]

    return {"plan": plan, "customer_profile": profile, "lessons": lessons}


def supervisor(state: ClaimState) -> Command[Literal["extractor", "fraud_screener", "coverage_analyst", "compute_payout"]]:
    """M3: decide which sub-agent runs next, and when the facts are complete.

    Extractor and Fraud Screener don't depend on each other, so they fan out in parallel. Coverage needs the facts.
    """
    if state.get("facts") is None and state.get("fraud") is None:
        return Command(goto=["extractor", "fraud_screener"])   # a list = run in parallel
    if state.get("coverage") is None:
        return Command(goto="coverage_analyst")
    # TODO M3: also loop back if facts are incomplete (e.g. Extractor could not read an attachment).
    return Command(goto="compute_payout")


# Sub-agent nodes. Each is a thin wrapper: map parent state -> sub-agent input, invoke the compiled subgraph,
# map its output back. The subgraph keeps its own state schema (and its own messages).

def extractor(state: ClaimState) -> dict:
    """M3: read attachments (filesystem MCP) and compute delay hours (time MCP) -> ClaimFacts.

    MCP tools are async-only. When this calls them, make it `async def extractor(...)`, use
    `await extractor_graph.ainvoke(...)`, and run the parent graph with ainvoke/astream.
    """
    # TODO M3: result = await extractor_graph.ainvoke({"claim_id": ..., "attachments": ..., "text": state["redacted_text"]})
    # TODO M5: run the tool-output guardrail on each read_text_file result; on injection return
    #          {"risk_flags": ["injection_in_attachment"]} along with the facts.
    return {
        "facts": {
            "documents": state["claim_input"].get("attachments", []),
            "delay_hours": 13.25,
            "items": [],
            "pir_present": None,
        },
        "risk_flags": [],
    }


def fraud_screener(state: ClaimState) -> dict:
    """M3: ReAct agent with get_customer, get_claim_history, check_duplicate_receipt -> FraudAssessment.

    Pass submitted_at in from code (e.g. ToolRuntime context) so get_claim_history counts back from it.
    Give it state["customer_profile"] from the store (M8).
    """
    # TODO M3: result = fraud_graph.invoke({...}, context=...)
    return {"fraud": {"score": "low", "signals": []}}


def coverage_analyst(state: ClaimState) -> dict:
    """M4: agentic RAG over the policy booklets, filtered by state["plan"] -> CoverageFinding."""
    # TODO M4: result = coverage_graph.invoke({"plan": state["plan"], "facts": state["facts"], "lessons": state["lessons"]})
    return {
        "coverage": {
            "applicable_clauses": ["DLY-1"],
            "exclusions_hit": [],
            "missing_docs": [],
            "needs_human": False,
            "reasoning": "stub",
        }
    }


def compute_payout(state: ClaimState) -> dict:
    """Rule 1: no LLM arithmetic. Call the pure functions in copilot/payout.py."""
    # TODO: from copilot.payout import compute; return {"payout": compute(state["plan"], state["facts"], state["coverage"])}
    return {"payout": {"amount": 200.0, "breakdown": ["stub: 2 x 6h blocks x $100"]}}


def draft_decision(state: ClaimState) -> dict:
    """LLM writes the decision + letter from facts, coverage, payout. On a retry, feed it guardrail_report."""
    # TODO: decision from coverage (deny / request_info / approve / escalate), payout copied from state["payout"],
    #       letter by an LLM. If state.get("guardrail_report", {}).get("problems"), include them in the prompt.
    return {
        "draft": {
            "decision": "approve",
            "payout": state["payout"]["amount"],
            "citations": state["coverage"]["applicable_clauses"],
            "letter": "Dear customer, your claim has been approved. (stub)",
        }
    }


def output_guardrail(state: ClaimState) -> dict:
    """M5: check the draft (or the adjuster's edit). Deterministic checks only, in Python."""
    problems: list[str] = []

    # TODO M5:
    #   - every citation exists and is in coverage.applicable_clauses
    #   - payout <= plan / clause limits (recompute, don't trust the draft)
    #   - letter has no PII apart from the first name (check against pii_vault too)
    #   - deny / request_info / blocked means payout == 0

    passed = not problems
    update: dict = {"guardrail_report": {"passed": passed, "problems": problems}}
    if not passed:
        update["retry_count"] = state.get("retry_count", 0) + 1
    return update


def adjuster_review(state: ClaimState) -> Command[Literal["output_guardrail", "execute"]]:
    """M6: pause for a human. Resumed with Command(resume={"action", "payout", "letter", "note"}).

    Everything above interrupt() runs again on resume, so keep it free of side effects.
    """
    packet = {
        "claim_id": state["claim_input"]["claim_id"],
        "summary": state.get("redacted_text"),
        "citations": state["draft"]["citations"],   # TODO M6: include the clause text too
        "payout": state.get("payout"),
        "fraud": state.get("fraud"),
        "risk_flags": state.get("risk_flags", []),
        "draft_letter": state["draft"]["letter"],
        "guardrail_problems": state.get("guardrail_report", {}).get("problems", []),
    }
    answer = interrupt(packet)
    action = answer["action"]

    if action == "approve":
        return Command(goto="execute", update={"review": answer})

    # edit / reject: the human's version replaces the draft and must pass the output guardrail again.
    draft = dict(state["draft"])
    if action == "edit":
        draft["payout"] = answer.get("payout", draft["payout"])
        draft["letter"] = answer.get("letter", draft["letter"])
    else:  # reject
        draft.update(decision="deny", payout=0, letter=answer.get("letter", draft["letter"]))
    # TODO M6: decide how "reject" should be worded and cited.
    return Command(
        goto="output_guardrail",
        update={"review": answer, "draft": draft, "decision_version": state.get("decision_version", 1) + 1},
    )


def execute(state: ClaimState) -> dict:
    """M7: the ONLY node with side effects. Both tools are idempotent, so a replay is safe."""
    claim_id = state["claim_input"]["claim_id"]
    draft = state["draft"]
    idempotency_key = f"{claim_id}:v{state.get('decision_version', 1)}"

    payment = None
    if draft["decision"] == "approve" and draft["payout"] > 0:
        # TODO M7: payment = issue_payment.invoke({"claim_id": claim_id, "amount": draft["payout"], "idempotency_key": idempotency_key})
        payment = {"status": "stub", "idempotency_key": idempotency_key}
        if os.environ.get("CRASH_AFTER") == "issue_payment":
            raise SystemExit("CRASH_AFTER=issue_payment")   # M7 crash test

    # TODO M7: letter = send_letter.invoke({"claim_id": claim_id, "body": draft["letter"]})
    letter = {"status": "stub"}

    return {"executed": {"payment": payment, "letter": letter}}


def save_memory(state: ClaimState, runtime: Runtime) -> dict:
    """M8: update ("customers", customer_id) with a summary of this claim."""
    if runtime.store is not None:
        customer_id = state["claim_input"]["customer_id"]
        profile = dict(state.get("customer_profile") or {})
        summaries = list(profile.get("prior_claim_summaries", []))
        # TODO M8: write a better summary (no PII), plus preferred_language / tone_notes / known_documents.
        summaries.append(f"{state['claim_input']['claim_id']}: {state['draft']['decision']} ${state['draft']['payout']}")
        profile["prior_claim_summaries"] = summaries
        runtime.store.put(("customers", customer_id), "profile", profile)
    return {}


def reflect(state: ClaimState, runtime: Runtime) -> dict:
    """M9: when the adjuster edited or rejected, turn the difference into one candidate lesson."""
    review = state.get("review")
    if not review or review["action"] == "approve" or runtime.store is None:
        return {}

    # TODO M9: ask an LLM to compare the AI draft with the human's final version and write ONE general lesson.
    lesson = f"(stub) adjuster {review['action']}ed: {review.get('note', '')}"
    runtime.store.put(
        ("lessons",),
        str(uuid.uuid4()),
        {
            "text": lesson,
            "status": "candidate",   # promote_lessons.py flips this to "promoted" after the eval gate
            "claim_type": state["claim_input"]["claim_type"],
            "source_claim_id": state["claim_input"]["claim_id"],
        },
    )
    return {}


# --------------------------------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------------------------------

def route_after_input_guardrail(state: ClaimState) -> Literal["reject_with_reason", "load_memory"]:
    return "reject_with_reason" if state.get("blocked_reason") else "load_memory"


def needs_human(state: ClaimState) -> bool:
    """M6: any of these sends the claim to an adjuster."""
    fraud = state.get("fraud") or {}
    coverage = state.get("coverage") or {}
    return (
        state["draft"]["payout"] > HUMAN_REVIEW_PAYOUT_LIMIT
        or fraud.get("score") in ("medium", "high")
        or bool(coverage.get("needs_human"))
        or bool(state.get("risk_flags"))
    )


def route_after_output_guardrail(state: ClaimState) -> Literal["draft_decision", "adjuster_review", "execute"]:
    review = state.get("review") or {}
    human_override = review.get("action") in ("edit", "reject")

    if not state["guardrail_report"]["passed"]:
        if human_override:
            return "adjuster_review"            # the human's edit broke a rule: ask them again
        if state.get("retry_count", 0) <= MAX_DRAFT_RETRIES:
            return "draft_decision"             # let the LLM fix it
        return "adjuster_review"                # out of retries: force human review

    if human_override:
        return "execute"                        # the human already decided, and it passed
    return "adjuster_review" if needs_human(state) else "execute"


# --------------------------------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------------------------------

def build_graph(checkpointer=None, store=None):
    builder = StateGraph(ClaimState)

    builder.add_node("input_guardrail", input_guardrail)
    builder.add_node("reject_with_reason", reject_with_reason)
    builder.add_node("load_memory", load_memory)
    builder.add_node("supervisor", supervisor)
    builder.add_node("extractor", extractor)
    builder.add_node("fraud_screener", fraud_screener)
    builder.add_node("coverage_analyst", coverage_analyst)
    builder.add_node("compute_payout", compute_payout)
    builder.add_node("draft_decision", draft_decision)
    builder.add_node("output_guardrail", output_guardrail)
    builder.add_node("adjuster_review", adjuster_review)
    builder.add_node("execute", execute)
    builder.add_node("save_memory", save_memory)
    builder.add_node("reflect", reflect)

    builder.add_edge(START, "input_guardrail")
    builder.add_conditional_edges("input_guardrail", route_after_input_guardrail)
    builder.add_edge("reject_with_reason", END)
    builder.add_edge("load_memory", "supervisor")

    # supervisor routes with Command(goto=...); every sub-agent reports back to it
    builder.add_edge("extractor", "supervisor")
    builder.add_edge("fraud_screener", "supervisor")
    builder.add_edge("coverage_analyst", "supervisor")

    builder.add_edge("compute_payout", "draft_decision")
    builder.add_edge("draft_decision", "output_guardrail")
    builder.add_conditional_edges("output_guardrail", route_after_output_guardrail)
    # adjuster_review routes with Command(goto=...)

    builder.add_edge("execute", "save_memory")
    builder.add_edge("save_memory", "reflect")
    builder.add_edge("reflect", END)

    return builder.compile(checkpointer=checkpointer, store=store)


# --------------------------------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------------------------------

def load_case(case_id: str) -> dict:
    with open(DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["id"] == case_id:
                return row
    raise KeyError(f"No eval case {case_id} in {DATASET_PATH}")


if __name__ == "__main__":
    case = load_case(sys.argv[1] if len(sys.argv) > 1 else "E01")
    claim_id = case["input"]["claim_id"]
    config = {"configurable": {"thread_id": claim_id}}   # M2: thread_id = claim_id

    with SqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as checkpointer:
        graph = build_graph(checkpointer=checkpointer, store=InMemoryStore())

        result = graph.invoke({"claim_input": case["input"]}, config, durability="sync")

        if "__interrupt__" in result:
            print("Paused for an adjuster:")
            print(json.dumps(result["__interrupt__"][0].value, indent=2))
            # Resume later, even from a new process:
            # graph.invoke(Command(resume={"action": "approve"}), config, durability="sync")
        else:
            print(json.dumps({"draft": result.get("draft"), "executed": result.get("executed")}, indent=2))

        history = list(graph.get_state_history(config))
        print(f"\n{len(history)} checkpoints for thread {claim_id}")
