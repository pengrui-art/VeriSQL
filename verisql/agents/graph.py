"""
VeriSQL LangGraph Workflow

Defines the main StateGraph that orchestrates all VeriSQL modules.
"""

from typing import Literal
from langgraph.graph import StateGraph, END

from verisql.agents.state import VeriSQLState
from verisql.agents.nodes import (
    intent_parser_node,
    auto_formalizer_node,
    sql_generator_node,
    spec_generator_node,
    symbolic_verifier_node,
    dynamic_verifier_node,
    formal_repair_node,
    executor_node,
)
from verisql.config import MAX_REPAIR_ITERATIONS


def create_verisql_graph() -> StateGraph:
    """
    Create the VeriSQL LangGraph workflow.

    Flow:
    1. Intent Parser -> AutoFormalizer -> [SQL Generator, Spec Generator] (parallel)
    2. Symbolic Verifier
    3. If PASS -> Executor -> END
       If FAIL -> Formal Repair -> SQL Generator (loop, max 3 times)
    4. If max retries exceeded -> END with error
    """

    # Create the graph
    workflow = StateGraph(VeriSQLState)

    # Add all nodes
    workflow.add_node("intent_parser", intent_parser_node)
    workflow.add_node("auto_formalizer", auto_formalizer_node)
    workflow.add_node("sql_generator", sql_generator_node)
    workflow.add_node("spec_generator", spec_generator_node)
    workflow.add_node("symbolic_verifier", symbolic_verifier_node)
    workflow.add_node("dynamic_verifier", dynamic_verifier_node)
    workflow.add_node("formal_repair", formal_repair_node)
    workflow.add_node("executor", executor_node)

    # Set entry point
    workflow.set_entry_point("intent_parser")

    # Define edges
    workflow.add_edge("intent_parser", "auto_formalizer")

    # After AutoFormalizer, go to SQL generator
    # (Spec generator will be called after SQL for simplicity)
    workflow.add_edge("auto_formalizer", "sql_generator")
    workflow.add_edge("sql_generator", "spec_generator")
    workflow.add_edge("spec_generator", "symbolic_verifier")
    workflow.add_edge("symbolic_verifier", "dynamic_verifier")

    # Conditional edge after verification (Now checks output of Dynamic)
    def route_after_verification(
        state: VeriSQLState,
    ) -> Literal["executor", "formal_repair", "end"]:
        """Route based on verification result"""
        verification_result = state.get("verification_result")
        repair_count = state.get("repair_count", 0)
        ablation_mode = state.get("ablation_mode", "none")

        if verification_result is None:
            return "end"

        if verification_result.status == "PASS":
            return "executor"
        elif verification_result.status == "ERROR":
            # Prevent Destructive Repairs: System crashes should not be passed to LLM as "bugs"
            return "executor"
        elif ablation_mode == "no_repair":
            return "executor"  # If no repair is allowed, just proceed to execute (or end) regardless of failure
        elif repair_count < MAX_REPAIR_ITERATIONS:
            return "formal_repair"
        else:
            # Max retries exceeded
            return "executor"  # changed from end to executor to allow final eval even if verify failed

    workflow.add_conditional_edges(
        "dynamic_verifier",
        route_after_verification,
        {"executor": "executor", "formal_repair": "formal_repair", "end": END},
    )

    # After repair, go back to SQL generator
    workflow.add_edge("formal_repair", "sql_generator")

    # After executor, end
    workflow.add_edge("executor", END)

    return workflow


def compile_verisql_app():
    """Compile the VeriSQL application"""
    graph = create_verisql_graph()
    return graph.compile()


# Create the app instance
verisql_app = compile_verisql_app()
