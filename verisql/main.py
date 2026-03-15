"""
VeriSQL Main Entry Point

Usage:
    python main.py "What is the total sales of active products in Q3?"
"""

import argparse
import json
from typing import Optional

from verisql.agents.graph import verisql_app
from verisql.agents.state import VeriSQLState


def run_verisql(
    query: str,
    schema_info: Optional[dict] = None,
    db_path: Optional[str] = None,
    verbose: bool = False,
    ablation_mode: str = "none",
) -> dict:
    """
    Run VeriSQL on a natural language query.

    Args:
        query: Natural language query
        schema_info: Optional database schema information
        db_path: Path to database
        verbose: Print intermediate steps
        ablation_mode: Ablation logic skip ("none", "no_dynamic", "no_repair")

    Returns:
        Dictionary with final SQL, verification status, and results
    """
    # Initialize state
    initial_state: VeriSQLState = {
        "query": query,
        "schema_info": schema_info or {},
        "db_path": db_path,
        "ilr": None,
        "sql": None,
        "constraint_spec": None,
        "ltl_formula": None,
        "verification_result": None,
        "repair_count": 0,
        "repair_history": [],
        "current_feedback": None,
        "final_sql": None,
        "final_result": None,
        "execution_status": "pending",
        "errors": [],
        "ablation_mode": ablation_mode,
        "fault_localizations": [],
        "patch_actions": [],
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"VeriSQL - Neuro-Symbolic Runtime Verification")
        print(f"{'='*60}")
        print(f"\n📝 Query: {query}\n")

    # Run the workflow
    try:
        final_state = verisql_app.invoke(initial_state)

        if verbose:
            print(f"\n{'─'*60}")
            print("📊 Results:")
            print(f"{'─'*60}")

            if final_state.get("ilr"):
                print(f"\n✅ ILR Generated")

            if final_state.get("sql"):
                print(f"\n📄 SQL Generated:\n{final_state['sql']}")

            if final_state.get("ltl_formula"):
                print(f"\n📐 LTL Formula:\n{final_state['ltl_formula']}")

            if final_state.get("verification_result"):
                vr = final_state["verification_result"]
                status_icon = "✅" if vr.status == "PASS" else "❌"
                print(f"\n{status_icon} Verification: {vr.status}")
                if vr.missing_constraints:
                    print(f"   Missing: {vr.missing_constraints}")

            if final_state.get("repair_count", 0) > 0:
                print(f"\n🔧 Repair Iterations: {final_state['repair_count']}")

            if final_state.get("errors"):
                print(f"\n⚠️ Errors: {final_state['errors']}")

        return {
            "query": query,
            "sql": final_state.get("final_sql") or final_state.get("sql"),
            "verified": (
                final_state.get("verification_result").status == "PASS"
                if final_state.get("verification_result")
                else False
            ),
            "repair_iterations": final_state.get("repair_count", 0),
            "ltl_formula": final_state.get("ltl_formula"),
            "errors": final_state.get("errors", []),
            "execution_status": final_state.get("execution_status", "unknown"),
        }

    except Exception as e:
        if verbose:
            print(f"\n❌ Error: {str(e)}")
        return {
            "query": query,
            "sql": None,
            "verified": False,
            "errors": [str(e)],
            "execution_status": "failed",
        }


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="VeriSQL - Neuro-Symbolic Runtime Verification for Text-to-SQL"
    )
    parser.add_argument(
        "query", type=str, help="Natural language query to convert to SQL"
    )
    parser.add_argument(
        "--schema", type=str, help="Path to schema JSON file", default=None
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print verbose output"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Load schema if provided
    schema_info = None
    if args.schema:
        with open(args.schema, "r") as f:
            schema_info = json.load(f)

    # Run VeriSQL
    result = run_verisql(
        query=args.query, schema_info=schema_info, verbose=args.verbose
    )

    if args.json:
        print(json.dumps(result, indent=2))
    elif not args.verbose:
        # Print just the SQL
        if result.get("sql"):
            print(result["sql"])
        else:
            print("Error: Could not generate SQL")
            for error in result.get("errors", []):
                print(f"  - {error}")


if __name__ == "__main__":
    main()
