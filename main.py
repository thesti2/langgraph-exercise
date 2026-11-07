"""CLI driver: run a ticket, and play the human whenever the graph pauses.

    uv run main.py T2
"""

import sys

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command  # noqa: F401  (you'll need this in M3)

import orders
from graph import build_graph
from tickets import TICKETS
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer




def ask_human(payload: dict):
    """Show an interrupt payload to the person at the terminal and return the
    resume value, using the shapes in the README's "Interrupt payload contract".

    TODO (M3): branch on payload["type"]:
      - "ask_customer"  -> input() the customer's answer, return str
      - "human_review"  -> show the recommendation, return {"action": "approve" | "edit" | "reject", ...}
      - "review_reply"  -> show the email, return {"action": "send"} or {"action": "edit", "body": ...}
    """
    input_type = payload["type"]

    match input_type:
        case "ask_customer":
            print(payload["question"])

            answer = input("please input your answer:")
            return answer
        case "human_review":
            print(f"order_id: {payload["order_id"]}, amount: {payload["amount"]}, method: {payload["method"]}, recommendation: {payload["recommendation"]}, reason: {payload["reasons"]}, customer message: {payload["customer_message"]}")

            action = input("approve / edit / reject: ").strip()
            if action == "edit":
                return {"action": "edit",
                        "amount": float(input("amount: ")),
                        "method": input("method (original_payment / store_credit): ").strip()}
            if action == "reject":
                return {"action": "reject", "reason": input("reason: ")}
            return {"action": "approve"}
        case "review_reply":
            print(f"to: {payload["to"]}, subject: {payload["subject"]}, body: {payload["body"]}")

            action = input("send / edit: ").strip()
            if action == "edit":
                return {"action": "edit",
                        "body": input("new body:")}
            return {"action": "send"}
        case _:
            pass
    

def run_ticket(graph, ticket_id: str) -> dict:
    ticket = TICKETS[ticket_id]
    config = {"configurable": {"thread_id": f"ticket-{ticket_id}"}}

    result = graph.invoke(
        {"ticket_id": ticket_id, "customer_email": ticket["from"], "message": ticket["message"]},
        config,
    )

    # TODO (M3): while the result contains "__interrupt__":
    #   payload = result["__interrupt__"][0].value
    #   answer  = ask_human(payload)
    #   result  = graph.invoke(Command(resume=answer), config)
    while ("__interrupt__" in result):
        answer = ask_human(result["__interrupt__"][0].value)
        result = graph.invoke(Command(resume=answer), config)

    return result


if __name__ == "__main__":
    ticket_ids = sys.argv[1:] or list(TICKETS)
    serde = JsonPlusSerializer(allowed_msgpack_modules=[
    ("state", "Request"), ("state", "RefundRecommendation"), ("state", "Email")])
    graph = build_graph(checkpointer=InMemorySaver(serde=serde))

    for tid in ticket_ids:
        print(f"\n===== {tid} =====")
        final = run_ticket(graph, tid)
        for entry in final.get("audit_log", []):
            print("  audit:", entry)

    print("\nREFUND_LEDGER:", orders.REFUND_LEDGER)
    print("OUTBOX:", len(orders.OUTBOX), "email(s)")
