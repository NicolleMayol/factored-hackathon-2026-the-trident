"""Compila el grafo LangGraph. Loop Verify → Act máx. 2 iteraciones (loop engineering)."""
from __future__ import annotations
from langgraph.graph import END, StateGraph

from agent.adapters import Deps
from agent.config.settings import Settings
from agent.graph.nodes import Nodes
from agent.graph.state import AgentState


def build_graph(deps: Deps, settings: Settings):
    n = Nodes(deps, settings)
    g = StateGraph(AgentState)
    g.add_node("understand", n.understand)
    g.add_node("decide", n.decide)
    g.add_node("act", n.act)
    g.add_node("verify", n.verify)
    g.add_node("escalate", n.escalate)
    g.add_node("respond", n.respond)
    g.set_entry_point("understand")
    g.add_edge("understand", "decide")

    def after_decide(st: AgentState) -> str:
        a = st.get("_policy_action")
        if a in ("auto", "confirm"):
            return "act"
        if a in ("escalate",):
            return "escalate"
        return "respond"  # clarify, abstain, block, reject

    def after_act(st: AgentState) -> str:
        return "escalate" if st.get("action") == "escalate" else "verify"

    def after_verify(st: AgentState) -> str:
        if st.get("verify_ok"):
            return "respond"
        if st.get("iterations", 0) < settings.max_tool_iterations and "no_citation" in st.get("verify_notes", []):
            return "act"  # re-Act una vez más
        return "escalate"

    g.add_conditional_edges("decide", after_decide, {"act": "act", "escalate": "escalate", "respond": "respond"})
    g.add_conditional_edges("act", after_act, {"verify": "verify", "escalate": "escalate"})
    g.add_conditional_edges("verify", after_verify, {"respond": "respond", "act": "act", "escalate": "escalate"})
    g.add_edge("escalate", "respond")
    g.add_edge("respond", END)
    return g.compile()
