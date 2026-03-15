"""Agents package.

Keep imports lightweight: importing `verisql.agents.state` should not require LangGraph.
Graph/nodes are exposed via lazy attribute loading.
"""

from verisql.agents.state import VeriSQLState, VerificationResult, RepairSuggestion

__all__ = [
    "VeriSQLState",
    "VerificationResult",
    "RepairSuggestion",
    "create_verisql_graph",
    "compile_verisql_app",
    "verisql_app",
    "intent_parser_node",
    "auto_formalizer_node",
    "sql_generator_node",
    "spec_generator_node",
    "symbolic_verifier_node",
    "formal_repair_node",
    "executor_node",
]


def __getattr__(name: str):  # pragma: no cover
    if name in ("create_verisql_graph", "compile_verisql_app", "verisql_app"):
        from verisql.agents.graph import (
            create_verisql_graph,
            compile_verisql_app,
            verisql_app,
        )

        if name == "create_verisql_graph":
            return create_verisql_graph
        if name == "compile_verisql_app":
            return compile_verisql_app
        return verisql_app

    if name in (
        "intent_parser_node",
        "auto_formalizer_node",
        "sql_generator_node",
        "spec_generator_node",
        "symbolic_verifier_node",
        "formal_repair_node",
        "executor_node",
    ):
        from verisql.agents import nodes as _nodes

        return getattr(_nodes, name)

    raise AttributeError(f"module 'verisql.agents' has no attribute {name!r}")
