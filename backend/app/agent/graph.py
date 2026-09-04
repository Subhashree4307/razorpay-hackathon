from langgraph.graph import StateGraph, START, END 
from backend.app.agent.state import RecoveryAgentState, NextAction
from backend.app.agent.execution import tool_send_rescue_link, tool_schedule_retry, tool_escalate
from backend.app.agent.decision import agent_decision_node
from backend.app.agent.score import agent_scoring_node
def conditional_router(state: RecoveryAgentState)-> str:
    next_action = state.get("next_action")
    if next_action== "SEND_RESCUE_LINK" or next_action== "SEND_PERSONALIZED_MESSAGE":
        return "tool_send_rescue_link"
    elif next_action== "SCHEDULE_RETRY":
        return "tool_schedule_retry"
    elif next_action== "ESCALATE_TO_SUPPORT":
        return "tool_escalate"
    return "END"
builder = StateGraph(RecoveryAgentState)
builder.add_node("compute_score", agent_scoring_node)
builder.add_node("agent_decision_node", agent_decision_node)
builder.add_node("tool_send_rescue_link", tool_send_rescue_link)
builder.add_node("tool_schedule_retry", tool_schedule_retry)
builder.add_node("tool_escalate", tool_escalate)
builder.add_edge(START, "compute_score")
builder.add_edge("compute_score", "agent_decision_node")
builder.add_conditional_edge(
    "agent_decision_node", 
    conditional_router,
    {
        "tool_send_rescue_link": "tool_send_rescue_link",
        "tool_schedule_retry": "tool_schedule_retry",
        "tool_escalate": "tool_escalate",
        "END": END
    }
)
builder.add_edge("tool_schedule_retry", END)
builder.add_edge("tool_execute_comms", END)
builder.add_edge("tool_escalate", END)

recovery_graph = builder.compile()



