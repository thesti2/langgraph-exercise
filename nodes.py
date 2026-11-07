"""Graph nodes. Each node takes RefundState and returns a partial state update
(or a Command). Replace every NotImplementedError.
"""

from langchain.messages import HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain.tools import tool
from langgraph.types import Command, interrupt  # noqa: F401  (you'll need these in M3)
from langgraph.graph import END

import orders  # noqa: F401
from llm import llm  # noqa: F401
from state import RefundState, Request, RefundRecommendation, Email
from orders import ORDERS

ORDER_SYSTEM_MESSAGE = """
    You will be given a customer input for a refund request. Your task is to extract the information order id (if mentioned in the input, otherwise return as none), refund reason, if the item is damaged, list of item code from the input 
    (*DO NOT RETURN ANY INFORMATION THAT IS NOT IN THE INPUT*). If you don't find the information in the prompt, you return as None.

    *IMPORTANT*: DO NOT RETURN any information outside of the user input. If you don't find the information from the user input, return as None.
    """

DRAFT_SYSTEM_MESSAGE = """
    You are an agent that will draft an email result regarding the result of a refund claim.
    The final refund result is:
    {outcome}
    """

# agent creation
orderAgent = llm.with_structured_output(Request)
draftAgent = llm.with_structured_output(Email)

# Helper function
def get_refund_amount(refund_request: Request, order: dict) -> float:
    refund_amount = 0

    if len(refund_request.items) > 0:
        for refund_item in refund_request.items:
            for order_item in order["items"]:
                if refund_item == order_item["sku"]:
                    refund_amount += order_item["price"]
    else:
        # refund all items, if refund request does not mention the item
        for order_item in order["items"]:
            refund_amount += order_item["price"]

    return refund_amount


def extract_request(state: RefundState) -> dict:
    """LLM: pull order_id / reason / damaged / item_skus out of state["message"].

    Use llm.with_structured_output(<your Pydantic model>).
    """    
    # return {"refund_request": Request(order_id="SF-1001", reason="too heavy", damaged=False, items=["MUG-01"])}   
    message = state["message"]
    
    result = orderAgent.invoke([SystemMessage(ORDER_SYSTEM_MESSAGE), HumanMessage(message)])

    log_entry = {
        "step": "extract_request",
        "details": result,
    }
    return {"refund_request": result, "audit_log": [log_entry]}


def ask_customer(state: RefundState) -> dict:
    """interrupt() with {"type": "ask_customer", "question": ...}.

    Append the customer's answer to the message so extract_request can try again.
    Guard against looping forever (e.g. max 2 attempts, then hand off to a human).
    """
    # remember every interrupt node will be run again from the start after resume (code before interrupt)
    # any duplicate possibility should be avoided by idempotent check in the interrupt node
    # everything before interrupt() call must be safe to repeat
    print("ask_customer entered")

    ask_attempts = state.get("ask_attempts", 0)
    ask_attempts += 1
    
    # return {"message": state["message"] + "\n\nCustomer follow-up: SF-1002"}
    answer = interrupt({"type": "ask_customer", "question": "Could you share your order number?"})


    # audit log
    log_entry = {
            "step": "ask_customer",            
            "details": answer,
        }

    # return the order ID
    # refund_request = state.get("refund_request")
    # refund_request.order_id = answer
    # return {"refund_request": refund_request}
    return {"message": state["message"] + f"\n\nCustomer follow-up: {answer}", "ask_attempts": ask_attempts, "audit_log": [log_entry]}


def lookup_order(state: RefundState) -> dict:
    """orders.get_order + orders.get_customer. Handle "order not found"."""    
    order_id = state["refund_request"].order_id.upper()
    customer_email = state["customer_email"] 

    order = orders.get_order(order_id)
    customer = orders.get_customer(customer_email)

    # audit log
    log_entry = {
            "step": "lookup_order", 
            "detail": [order, customer]
        }

    return {"order": order,
            "customer": customer,
            "audit_log": [log_entry]}    

def check_policy(state: RefundState) -> dict:
    """Deterministic refund policy from the README. No LLM here."""
    refund_request = state["refund_request"]
    order = state["order"]
    customer = state["customer"]
    is_decided = False
    days = (orders.TODAY - order["delivered_on"]).days

    # default values
    refund_recommendation = RefundRecommendation(recommendation="reject", amount=0.0, method="original_payment",
                                                needs_review=True, reason="")

    # Policy 1. check if the refunded item is marked as final sale
    if len(refund_request.items) > 0:
        for refund_item in refund_request.items:
            for order_item in order["items"]:
                if refund_item == order_item["sku"]:
                    if order_item["final_sale"]:
                        refund_recommendation.recommendation = "reject"
                        refund_recommendation.reason = "Item is final sale"
                        is_decided = True
    else:
        for order_item in order["items"]:
            if order_item["final_sale"]:
                refund_recommendation.recommendation = "reject"
                refund_recommendation.reason = "Item is final sale"
                is_decided = True

    # Policy 2. check if item damaged / defective
    if not is_decided:
        if refund_request.damaged:
            refund_recommendation.recommendation = "approve"
            refund_recommendation.method = "original_payment"
            refund_recommendation.reason = "Item is damaged / defective"
            is_decided = True            

            # get full amount
            refund_recommendation.amount = get_refund_amount(refund_request=refund_request, order=order)

    # Policy 3.
    if not is_decided:
        if days <= 30:
            refund_recommendation.recommendation = "approve"
            refund_recommendation.method = "original_payment"
            refund_recommendation.reason = "Item is less than 30 days"
            is_decided = True

            # get full amount
            refund_recommendation.amount = get_refund_amount(refund_request=refund_request, order=order)

    # Policy 4
    if not is_decided:
        if days > 30 and days <= 60:
            refund_recommendation.recommendation = "approve"
            refund_recommendation.method = "store_credit"
            refund_recommendation.reason = "Item is more than 30 days but less than 60 days"
            is_decided = True

            # get full amount
            refund_recommendation.amount = get_refund_amount(refund_request=refund_request, order=order)

    # Policy 5
    if not is_decided:
        if days > 60:
            refund_recommendation.recommendation = "reject"
            refund_recommendation.reason = "Item is more than 60 days"
            is_decided = True

    log_entry = {
            "step": "check_policy",            
            "decision": refund_recommendation.recommendation,
            "by": "policy",
            "detail": refund_recommendation.reason,
        }
    # Auto Approve checking
    refund_recommendation.needs_review = True
    decision = {}
    if (
        refund_recommendation.recommendation != "reject"
        and refund_recommendation.amount <= 100
        and customer["refunds_last_90_days"] < 3
    ):
        # This is auto approve, so we set the decision result as well
        refund_recommendation.needs_review = False        
        decision = {"action": "approve", "amount": refund_recommendation.amount, "method": refund_recommendation.method, "reason": refund_recommendation.reason}         

        # audit log
        log_entry = {
                    "step": "check_policy",            
                    "decision": "auto_approve",
                    "by": "policy",
                }

    return {"policy_result": refund_recommendation, "decision": decision, "audit_log": [log_entry]}


def human_review(state: RefundState) -> dict | Command:
    """interrupt() with the human_review payload. Handle approve / edit / reject.

    Remember: on resume this function runs again from the top.
    """    
    print("human_review entered")

    # return {"decision": {"action": "approve"}}
    refund_recommendation = state["policy_result"]

    # human_review
    answer = interrupt({"type": "human_review", "order_id": state["order"]["order_id"], "amount": refund_recommendation.amount, "method": refund_recommendation.method,
                        "recommendation": refund_recommendation.recommendation, "reasons": [refund_recommendation.reason], "customer_message": state["message"]})
    
    # audit_log
    log_entry = {
        "step": "human_review",
        "decision": answer["action"],                       # approve / edit / reject
        "by": "finance_reviewer",
        "details": {
            "policy_recommended": {
                "recommendation": refund_recommendation.recommendation,
                "amount": refund_recommendation.amount,
                "method": refund_recommendation.method,
            },
            "reviewer_input": answer,                       # e.g. {"action": "edit", "amount": 60.0, ...}
        },
    }
    return {"decision": answer, "audit_log": [log_entry]}


def issue_refund(state: RefundState) -> dict:
    """orders.issue_refund(..., idempotency_key=...). Must be safe to re-run."""
    # return {"refund_result": {"refund_id": "RF-STUB", "amount": 18.0, "method": "original_payment"}}    
    refund_recommendation = state["policy_result"]
    refund_decision = state["decision"]
    order = state["order"]

    idempotent_key = order["order_id"] + state["customer_email"]
    amount = refund_recommendation.amount
    method = refund_recommendation.method

    # check if there is an edit decision
    if refund_decision["action"] == "edit":
        # get values from edit action
        if refund_decision.get("amount") is not None and refund_decision["amount"] != 0.0:
            amount = refund_decision["amount"]
        if refund_decision.get("method") is not None:
            method = refund_decision["method"]

    # calculate refund only if amount is not 0
    refund = {}
    if amount != 0.0:
        refund = orders.issue_refund(order_id=order["order_id"], amount=amount, method=method, idempotency_key=idempotent_key)
    return {"refund_result": refund}


def draft_reply(state: RefundState) -> dict:
    """LLM: write a short, friendly email reflecting the FINAL decision
    (refunded amount + method, or the rejection reason)."""
    # return {"email_draft": Email(subject="test subject email", body="email body")}
    refund = state.get("refund_result")
    if refund:
        outcome = f"Refund issued: ${refund['amount']:.2f} via {refund['method']}"
    else:
        reason = state.get("decision", {}).get("reason") or state["policy_result"].reason
        outcome = f"No refund. Reason: {reason}"

    # prompt template to fill-in placeholder in system message with outcome
    # template = PromptTemplate.from_template(DRAFT_SYSTEM_MESSAGE)
    # system_message_template = template.partial(outcome=outcome)
    # system_message = system_message_template.format()
    # OR: option 2
    system_message = DRAFT_SYSTEM_MESSAGE.format(outcome=outcome)

    result = draftAgent.invoke([SystemMessage(system_message), HumanMessage("write a short, friendly email reflecting the FINAL decision (refunded amount + method, or the rejection reason).")])
    return {"email_draft": result}


def review_reply(state: RefundState) -> dict:
    """interrupt() with {"type": "review_reply", ...}. Apply edits if any."""
    # return {"email_review": "send"}
    print("review_reply entered")

    draft_email = state.get("email_draft")
    answer = interrupt({"type": "review_reply", "to": state["customer_email"], "subject": draft_email.subject, "body": draft_email.body})

    # review_reply: also apply the edit
    if answer["action"] == "edit":
        draft_email = Email(subject=draft_email.subject, body=answer["body"])

    # log entry
    log_entry = {
        "step": "review_reply",
        "decision": answer["action"],            # send / edit
        "by": "support_lead",
        "details": {"original_body": state["email_draft"].body, "sent_body": draft_email.body}
                if answer["action"] == "edit" else {},
    }
    return {"email_draft": draft_email, "email_review": answer["action"], "audit_log": [log_entry]}


def send_reply(state: RefundState) -> dict:
    """orders.send_email(...)."""
    orders.send_email(to=state["customer_email"], subject=state["email_draft"].subject, body=state["email_draft"].body)


# EDGES
def after_request(state: RefundState):
    """Conditional edge after request missing information"""
    # check max attemp
    
    if (state["refund_request"].order_id is not None):
        return "lookup_order"
    elif state.get("ask_attempts", 0) >= 2:
        return END
    else:
        return "ask_customer"


def after_lookup_order(state: RefundState):
    """Conditional edge after lookup order"""
    if (state.get("order")):
        return "check_policy"
    elif state.get("ask_attempts", 0) >= 2:
        return END
    else:
        return "ask_customer"
    

def after_check_policy(state: RefundState):
    """Conditional edge after checking refund policy"""
    if (state["policy_result"].needs_review):
        return "human_review"
    else:
        return "issue_refund"


def after_human_review(state: RefundState):
    """Conditional edge after human review"""
    if (state["decision"]["action"] == "reject"):
        return "draft_reply"
    else:
        return "issue_refund"


if __name__ == "__main__":
    message = "I want to return the laptop I bought recently, it's not what I need. How do I get a refund?"

    # extract check
    # result = orderAgent.invoke([SystemMessage(ORDER_SYSTEM_MESSAGE), HumanMessage(message)])
    # print(result)

    # policy check
    