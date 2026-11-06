"""Graph wiring. TODO (M1): add nodes and edges to match the README diagram."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph  # noqa: F401

import nodes  # noqa: F401
from state import RefundState


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    builder = StateGraph(RefundState)

    # TODO: builder.add_node(...) for every node in nodes.py
    # TODO: builder.add_edge / add_conditional_edges to match the diagram
    #   - after extract_request: missing order_id -> ask_customer, else lookup_order
    #   - after lookup_order: not found -> ask_customer, else check_policy
    #   - after check_policy: needs review -> human_review, else issue_refund
    #   - after human_review: approve/edit -> issue_refund, reject -> draft_reply

    # Interrupts need a checkpointer, or there is nowhere to save the paused state.
    return builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    print(build_graph().get_graph().draw_mermaid())
