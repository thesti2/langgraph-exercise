"""Graph wiring. TODO (M1): add nodes and edges to match the README diagram."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph  # noqa: F401

from nodes import extract_request, ask_customer, lookup_order, check_policy, human_review, issue_refund, draft_reply, review_reply, send_reply, after_request, after_lookup_order, after_check_policy, after_human_review
from state import RefundState


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    builder = StateGraph(RefundState)

    # builder.add_node(...) for every node in nodes.py
    builder.add_node("extract_request", extract_request)
    builder.add_node("ask_customer", ask_customer)
    builder.add_node("lookup_order", lookup_order)
    builder.add_node("check_policy", check_policy)
    builder.add_node("human_review", human_review)
    builder.add_node("issue_refund", issue_refund)
    builder.add_node("draft_reply", draft_reply)
    builder.add_node("review_reply", review_reply)
    builder.add_node("send_reply", send_reply)
    # builder.add_edge / add_conditional_edges to match the diagram
    #   - after extract_request: missing order_id -> ask_customer, else lookup_order
    #   - after lookup_order: not found -> ask_customer, else check_policy
    #   - after check_policy: needs review -> human_review, else issue_refund
    #   - after human_review: approve/edit -> issue_refund, reject -> draft_reply
    builder.add_edge(START, "extract_request")
    builder.add_conditional_edges("extract_request", after_request, ["ask_customer", "lookup_order", END])
    builder.add_edge("ask_customer", "extract_request")
    builder.add_conditional_edges("lookup_order", after_lookup_order, ["ask_customer", "check_policy", END])
    builder.add_conditional_edges("check_policy", after_check_policy, ["issue_refund", "human_review"])
    builder.add_conditional_edges("human_review", after_human_review, ["issue_refund", "draft_reply"])
    builder.add_edge("issue_refund", "draft_reply")
    builder.add_edge("draft_reply", "review_reply")
    builder.add_edge("review_reply", "send_reply")
    builder.add_edge("send_reply", END)


    # Interrupts need a checkpointer, or there is nowhere to save the paused state.
    return builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    build_graph().get_graph().draw_mermaid_png(output_file_path="graph.png")
