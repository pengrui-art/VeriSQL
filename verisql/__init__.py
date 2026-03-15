"""
VeriSQL - Neuro-Symbolic Runtime Verification for Database Analysis Agents

A verifiable agent architecture for Text-to-SQL with formal correctness guarantees.
"""

__version__ = "0.1.0"
__author__ = "VeriSQL Team"

# Keep package import lightweight.
# Some submodules (LangGraph workflow / UI) have heavier optional dependencies.

__all__ = [
    "run_verisql",
    "create_verisql_graph",
    "verisql_app",
    "ILR",
    "ConstraintSpec",
]


def __getattr__(name: str):  # pragma: no cover
    if name == "run_verisql":
        from verisql.main import run_verisql

        return run_verisql
    if name in ("create_verisql_graph", "verisql_app"):
        from verisql.agents.graph import create_verisql_graph, verisql_app

        return create_verisql_graph if name == "create_verisql_graph" else verisql_app
    if name in ("ILR", "ConstraintSpec"):
        from verisql.core.ilr import ILR
        from verisql.core.dsl import ConstraintSpec

        return ILR if name == "ILR" else ConstraintSpec

    raise AttributeError(f"module 'verisql' has no attribute {name!r}")
