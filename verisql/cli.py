"""
VeriSQL Command Line Interface

A CLI for interacting with the VeriSQL agent, designed for AI iterative testing.
Features:
- Configurable SQLite database path
- Load questions from BIRD dev.json
- Real-time agent thinking process output
- JSON output for parsing
"""
import argparse
import sqlite3
import os
import sys
import json
import csv
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from verisql.agents.nodes import (
    create_llm,
    INTENT_PARSER_PROMPT,
    AUTO_FORMALIZER_PROMPT,
    SQL_GENERATOR_PROMPT,
    SPEC_GENERATOR_PROMPT,
)
from verisql.config import SQL_MODEL, SPEC_MODEL, LLM_PROVIDER, get_llm_config
from verisql.core.dsl import ConstraintSpec
from verisql.utils.z3_utils import verify_sql_against_spec
from verisql.utils.spec_utils import parse_spec_safely
from verisql.utils.sql_safety import validate_read_only_sql
import re


def parse_json_from_markdown(text: str) -> Dict[str, Any]:
    """
    Robustly extract JSON from text that may contain Markdown code blocks
    or other conversational noise.
    """
    try:
        # 1. Try to find JSON inside markdown code blocks
        pattern = r"```(?:json)?\s*(.*?)```"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            json_str = match.group(1).strip()
        else:
            # 2. Heuristic: Find first '{' and last '}'
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                json_str = text[start : end + 1]
            else:
                json_str = text.strip()
        
        # 3. Remove C-style comments (// ...) which are invalid in std JSON
        json_str = re.sub(r"//.*", "", json_str)
        
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {str(e)} | Content: {text[:100]}...")


# ============== Default Paths ==============
REPO_ROOT = Path(__file__).resolve().parents[1]
BIRD_DEV_ROOT = REPO_ROOT / "verisql" / "DataBase" / "Bird" / "dev_20240627"
DEFAULT_BIRD_DB_ID = "california_schools"
DEFAULT_DB_PATH = (
    BIRD_DEV_ROOT
    / "dev_databases"
    / DEFAULT_BIRD_DB_ID
    / f"{DEFAULT_BIRD_DB_ID}.sqlite"
)
DEFAULT_DEV_JSON = BIRD_DEV_ROOT / "dev.json"


def infer_db_path_from_dev_json(dev_json_path: Path, db_id: Optional[str]) -> Path:
    if db_id:
        return dev_json_path.parent / "dev_databases" / db_id / f"{db_id}.sqlite"
    return DEFAULT_DB_PATH


def _quote_sqlite_ident(name: str) -> str:
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


# ============== Database Utils ==============

class CLIDatabaseManager:
    """Manage SQLite database connections and schema extraction for CLI"""
    
    def __init__(self):
        self.db_path: Optional[str] = None
        self.conn: Optional[sqlite3.Connection] = None
        self.schema_info: Dict[str, Any] = {}
    
    def load_database(self, file_path: str, description_dir: Optional[str] = None) -> Tuple[bool, str]:
        """
        Load a SQLite database and extract schema.
        
        Returns: (success, message)
        """
        try:
            if self.conn:
                self.conn.close()
            
            self.db_path = file_path
            self.conn = sqlite3.connect(file_path)
            
            # Extract schema
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            self.schema_info = {"tables": {}}
            
            for (table_name,) in tables:
                if table_name.startswith('sqlite_'):
                    continue
                    
                cursor.execute(f"PRAGMA table_info({_quote_sqlite_ident(table_name)})")
                columns = cursor.fetchall()
                
                col_info = []
                for col in columns:
                    col_id, name, dtype, not_null, default, pk = col
                    col_info.append({
                        "name": name,
                        "type": dtype,
                        "primary_key": bool(pk)
                    })
                
                self.schema_info["tables"][table_name] = col_info
            
            # Load external descriptions
            if description_dir:
                self._load_external_descriptions(description_dir)
            else:
                # Try default location
                db_dir = Path(file_path).parent
                desc_dir = db_dir / "database_description"
                if desc_dir.exists():
                    self._load_external_descriptions(str(desc_dir))
            
            return True, f"Database loaded: {Path(file_path).name}"
            
        except Exception as e:
            return False, f"Error loading database: {str(e)}"

    def _load_external_descriptions(self, desc_dir: str):
        """Load CSV description files"""
        desc_path = Path(desc_dir)
        if not desc_path.exists():
            return

        self.schema_info["descriptions"] = {}
        
        for csv_file in desc_path.glob("*.csv"):
            table_name = csv_file.stem
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    self.schema_info["descriptions"][table_name] = list(reader)
            except Exception as e:
                print(f"[WARN] Error loading description {csv_file}: {e}", file=sys.stderr)
    
    def execute_sql(self, sql: str) -> Tuple[bool, str, dict]:
        """Execute SQL and return results"""
        if not self.conn:
            return False, "No database loaded", {}

        is_safe, safety_error = validate_read_only_sql(sql)
        if not is_safe:
            return False, safety_error, {}
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return True, "Query executed successfully", {"columns": columns, "rows": rows}
                
        except Exception as e:
            return False, f"SQL Error: {str(e)}", {}

    def get_schema_text(self) -> str:
        """Get a text representation of the schema"""
        lines = []
        for table_name, columns in self.schema_info.get("tables", {}).items():
            col_strs = [f"  - {c['name']}: {c['type']}" + (" (PK)" if c['primary_key'] else "") 
                       for c in columns]
            lines.append(f"Table: {table_name}")
            lines.extend(col_strs)
            lines.append("")
        
        if self.schema_info.get("descriptions"):
            lines.append("Semantic Descriptions Loaded:")
            for table, desc_list in self.schema_info["descriptions"].items():
                lines.append(f"  - {table}: {len(desc_list)} columns described")
        
        return "\n".join(lines)


# ============== Agent Runner ==============

def truncate_str(s: str, max_len: int = 300) -> str:
    """Truncate long strings for display"""
    s = str(s)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def run_agent(
    query: str,
    schema_info: dict,
    verbose: bool = True,
    max_repair_iters: int = 3
) -> Dict[str, Any]:
    """
    Run VeriSQL agent and return results.
    
    Returns dict with:
        - success: bool
        - ilr: dict or None
        - sql: str or None
        - verification_status: str
        - verification_passed: bool
        - error: str or None
        - steps: list of step descriptions
    """
    result = {
        "success": False,
        "ilr": None,
        "sql": None,
        "spec": None,
        "verification_status": "",
        "verification_passed": False,
        "error": None,
        "steps": []
    }
    
    def log(msg: str):
        result["steps"].append(msg)
        if verbose:
            print(msg)
    
    try:
        # Check API configuration
        config = get_llm_config()
        if not config["api_key"]:
            result["error"] = f"No API key configured for {LLM_PROVIDER}"
            log(f"[ERROR] {result['error']}")
            return result
        
        # Step 1: Intent Parsing
        log(f"[Step 1] Intent Parsing (model: {SQL_MODEL})")
        
        llm = create_llm(SQL_MODEL)
        chain = INTENT_PARSER_PROMPT | llm
        
        response = chain.invoke({
            "query": query,
            "schema_info": json.dumps(schema_info, ensure_ascii=False)
        })
        
        try:
            parsed_intent = parse_json_from_markdown(response.content)
        except Exception as parse_err:
            result["error"] = f"Intent parsing failed: {truncate_str(str(parse_err))}"
            log(f"[ERROR] {result['error']}")
            return result
        
        log(f"[Step 1] Intent parsed: {json.dumps(parsed_intent, indent=2, ensure_ascii=False)}")
        
        # Step 2: AutoFormalizer
        log(f"[Step 2] AutoFormalizer - ILR Generation (model: {SPEC_MODEL})")
        
        llm2 = create_llm(SPEC_MODEL)
        chain2 = AUTO_FORMALIZER_PROMPT | llm2
        
        response2 = chain2.invoke({
            "parsed_intent": json.dumps(parsed_intent, ensure_ascii=False),
            "query": query
        })
        
        try:
            ilr_dict = parse_json_from_markdown(response2.content)
        except Exception as parse_err:
            result["error"] = f"ILR parsing failed: {truncate_str(str(parse_err))}"
            log(f"[ERROR] {result['error']}")
            return result
        
        result["ilr"] = ilr_dict
        log(f"[Step 2] ILR generated successfully")
        
        # Iterative Repair Loop
        repair_count = 0
        repair_count = 0
        repair_feedback = ""
        execution_feedback = ""
        spec_dict = None
        
        while repair_count <= max_repair_iters:
            iter_label = f" (Iteration {repair_count + 1})" if repair_count > 0 else ""
            
            # Step 3A: SQL Generation
            log(f"[Step 3A] SQL Generation{iter_label}")
            
            chain3 = SQL_GENERATOR_PROMPT | llm
            
            response3 = chain3.invoke({
                "ilr": json.dumps(ilr_dict, ensure_ascii=False),
                "schema_info": json.dumps(schema_info, ensure_ascii=False),
                "dialect": "sqlite",
                "repair_feedback": repair_feedback,
                "execution_feedback": execution_feedback
            })
            
            # Robust SQL extraction
            content = response3.content
            pattern_block = r"```(?:sql)?\s*(.*?)```"
            match = re.search(pattern_block, content, re.DOTALL | re.IGNORECASE)
            if match:
                sql = match.group(1).strip()
            else:
                pattern_select = r"(SELECT\s+.*)"
                match_select = re.search(pattern_select, content, re.DOTALL | re.IGNORECASE)
                if match_select:
                    sql = match_select.group(1).strip()
                else:
                    sql = content.strip()
            
            result["sql"] = sql
            log(f"[Step 3A] SQL: {sql}")
            
            # --- Runtime Execution Step ---
            # Create temporary DB manager for execution
            temp_db = CLIDatabaseManager()
            if hasattr(schema_info, "db_path"): # Pass db path if available
                temp_db.conn = sqlite3.connect(schema_info["db_path"])
            else:
                 # Fallback: assume we are identifying DB by the CLIDatabaseManager instance passed to run_agent? 
                 # Actually run_agent receives schema_info. We need the db_path to execute.
                 # Let's pass 'db_path' in schema_info from the caller.
                 if "db_path" in schema_info:
                     temp_db.conn = sqlite3.connect(schema_info["db_path"])
                 else:
                     # Attempt to find db path from CLIDatabaseManager if possible? 
                     # simpler: just warn if no execution possible
                     log("[WARN] No DB path available for runtime execution")
            
            execution_ok = True
            if temp_db.conn:
                success, msg, data = temp_db.execute_sql(sql)
                if not success:
                    log(f"[Runtime] SQL Error: {msg}")
                    execution_feedback = f"Runtime SQL Error: {msg}"
                    execution_ok = False
                else:
                    rows = data.get("rows", [])
                    if len(rows) == 0:
                        log(f"[Runtime] Warning: Query returned 0 rows.")
                        execution_feedback = f"Warning: The query returned 0 rows. This might mean your filters (like strings) are incorrect (e.g., 'California' vs 'CA'). Check the descriptions."
                        execution_ok = False
                    else:
                        log(f"[Runtime] Success: Returned {len(rows)} rows.")
                        execution_feedback = ""
            
            if not execution_ok and repair_count < max_repair_iters:
                log(f"[Runtime] Triggering repair based on execution feedback...")
                repair_count += 1
                continue
            # ------------------------------
            
            # Step 3B: Spec Generation (only first time)
            if repair_count == 0:
                log(f"[Step 3B] Constraint Specification Generation")
                
                chain4 = SPEC_GENERATOR_PROMPT | llm2
                response4 = chain4.invoke({
                    "ilr": json.dumps(ilr_dict, ensure_ascii=False),
                    "query": query,
                    "schema_info": json.dumps(schema_info, ensure_ascii=False)
                })
                
                # Use safe parsing with sanitization
                fallback_table = schema_info.get("tables", {}).keys()
                fallback_table = list(fallback_table)[0] if fallback_table else "unknown"
                constraint_spec = parse_spec_safely(response4.content, fallback_table)
                spec_dict = constraint_spec.model_dump()
                
                result["spec"] = spec_dict
                log(f"[Step 3B] Spec: {json.dumps(spec_dict, indent=2, ensure_ascii=False)}")
            
            # Step 4: Verification
            log(f"[Step 4] Symbolic Verification")
            
            try:
                verify_result = verify_sql_against_spec(sql, constraint_spec, schema_info)
                
                if verify_result.status == "PASS":
                    result["verification_status"] = "VERIFIED - SQL satisfies all constraints"
                    result["verification_passed"] = True
                    log(f"[Step 4] Verification PASSED")
                    break
                else:
                    result["verification_status"] = f"{verify_result.status} - {truncate_str(verify_result.message)}"
                    log(f"[Step 4] Verification {verify_result.status}: {verify_result.message}")
                    
                    if verify_result.missing_constraints:
                        log(f"[Step 4] Violations: {verify_result.missing_constraints}")
                    
                    if repair_count < max_repair_iters:
                        log(f"[Step 4] Initiating repair attempt {repair_count + 1}...")
                        repair_feedback = f"Verification failed. Issues: {truncate_str(str(verify_result.missing_constraints), 150)}"
                        repair_count += 1
                    else:
                        log(f"[Step 4] Max repair iterations reached")
                        break
                        
            except Exception as e:
                result["verification_status"] = f"Verification skipped: {truncate_str(str(e))}"
                log(f"[Step 4] Could not verify: {truncate_str(str(e))}")
                break
        
        result["success"] = True
        log("[Done] Agent completed")
        return result
        
    except Exception as e:
        result["error"] = str(e)
        log(f"[ERROR] {str(e)}")
        return result


# ============== Question Loading ==============

def load_questions_from_json(json_path: str, db_id: Optional[str] = None) -> list:
    """Load questions from BIRD dev.json, optionally filtering by db_id"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if db_id:
        data = [q for q in data if q.get("db_id") == db_id]
    
    return data


def get_question_by_id(questions: list, question_id: int) -> Optional[dict]:
    """Get a specific question by its ID"""
    for q in questions:
        if q.get("question_id") == question_id:
            return q
    return None


# ============== Main CLI ==============

def main():
    parser = argparse.ArgumentParser(
        description="VeriSQL CLI - Command line interface for Text-to-SQL with verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with a specific question
  python cli.py --query "What is the highest eligible free rate for K-12 students?"
  
  # Run a question from BIRD dev.json by ID  
  python cli.py --question-id 0
  
  # Use a different database
  python cli.py --db /path/to/database.sqlite --query "List all users"
  
  # Output as JSON (for AI parsing)
  python cli.py --question-id 0 --json
  
  # Quiet mode (less verbose)
  python cli.py --question-id 0 --quiet
        """
    )
    
    # Database options
    parser.add_argument(
        "--db", "--database",
        type=str,
        default=None,
        help="Path to SQLite database. If omitted, it is inferred from --question-id/--db-id when possible."
    )
    parser.add_argument(
        "--description-dir",
        type=str,
        default=None,
        help="Path to database description directory (CSV files)"
    )
    
    # Query options
    query_group = parser.add_mutually_exclusive_group()
    query_group.add_argument(
        "--query", "-q",
        type=str,
        help="Natural language query to process"
    )
    query_group.add_argument(
        "--question-id", "-qid",
        type=int,
        help="Question ID from dev.json to process"
    )
    
    # BIRD dataset options
    parser.add_argument(
        "--dev-json",
        type=str,
        default=str(DEFAULT_DEV_JSON),
        help="Path to BIRD dev.json file"
    )
    parser.add_argument(
        "--db-id",
        type=str,
        default=None,
        help="Optional database ID filter for dev.json questions"
    )
    
    # Output options
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--quiet", "-Q",
        action="store_true",
        help="Quiet mode - only show final results"
    )
    parser.add_argument(
        "--execute", "-e",
        action="store_true",
        help="Execute generated SQL and show results"
    )
    
    # Agent options
    parser.add_argument(
        "--max-repair",
        type=int,
        default=3,
        help="Maximum repair iterations (default: 3)"
    )
    
    # Info options
    parser.add_argument(
        "--list-questions",
        action="store_true",
        help="List available questions from dev.json"
    )
    parser.add_argument(
        "--show-schema",
        action="store_true",
        help="Show database schema and exit"
    )
    
    args = parser.parse_args()
    dev_json_path = Path(args.dev_json)

    # List questions if requested
    if args.list_questions:
        questions = load_questions_from_json(str(dev_json_path), args.db_id)
        print(f"\n=== Available Questions ({len(questions)} total) ===")
        for q in questions[:50]:  # Show first 50
            difficulty = q.get("difficulty", "unknown")
            print(f"[{q['question_id']:3d}] ({difficulty:10s}) {q['question'][:80]}...")
        if len(questions) > 50:
            print(f"... and {len(questions) - 50} more")
        sys.exit(0)

    if args.show_schema and args.query is None and args.question_id is None:
        resolved_db_path = Path(args.db) if args.db else infer_db_path_from_dev_json(
            dev_json_path, args.db_id
        )
        resolved_description_dir = (
            Path(args.description_dir) if args.description_dir else None
        )
        db_manager = CLIDatabaseManager()
        success, msg = db_manager.load_database(
            str(resolved_db_path),
            str(resolved_description_dir) if resolved_description_dir else None,
        )
        if not success:
            print(f"[ERROR] {msg}", file=sys.stderr)
            sys.exit(1)
        print("\n=== Database Schema ===")
        print(db_manager.get_schema_text())
        sys.exit(0)
    
    # Determine the query to process
    query = None
    evidence = None
    gold_sql = None
    question_id = None
    selected_db_id = args.db_id
    
    if args.query:
        query = args.query
    elif args.question_id is not None:
        questions = load_questions_from_json(str(dev_json_path), args.db_id)
        q = get_question_by_id(questions, args.question_id)
        if not q:
            print(f"[ERROR] Question ID {args.question_id} not found", file=sys.stderr)
            sys.exit(1)
        query = q["question"]
        evidence = q.get("evidence", "")
        gold_sql = q.get("SQL", "")
        question_id = args.question_id
        selected_db_id = q.get("db_id") or selected_db_id
        
        if not args.quiet and not args.json:
            print(f"\n=== Question {question_id} ===")
            print(f"Query: {query}")
            if evidence:
                print(f"Evidence: {evidence}")
            print(f"Difficulty: {q.get('difficulty', 'unknown')}")
            print()
    else:
        parser.print_help()
        print("\n[ERROR] Please provide --query or --question-id", file=sys.stderr)
        sys.exit(1)

    resolved_db_path = Path(args.db) if args.db else infer_db_path_from_dev_json(
        dev_json_path, selected_db_id
    )
    resolved_description_dir = (
        Path(args.description_dir) if args.description_dir else None
    )

    # Initialize database after query/db resolution so question-driven runs can infer the correct DB.
    db_manager = CLIDatabaseManager()
    success, msg = db_manager.load_database(
        str(resolved_db_path),
        str(resolved_description_dir) if resolved_description_dir else None,
    )

    if not success:
        print(f"[ERROR] {msg}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet and not args.json:
        print(f"[INFO] {msg}")

    # Show schema if requested
    if args.show_schema:
        print("\n=== Database Schema ===")
        print(db_manager.get_schema_text())
        sys.exit(0)
    
    # Inject db_path for runtime execution
    db_manager.schema_info["db_path"] = db_manager.db_path
    
    # Run the agent
    result = run_agent(
        query=query,
        schema_info=db_manager.schema_info,
        verbose=not args.quiet and not args.json,
        max_repair_iters=args.max_repair
    )
    
    # Add metadata
    result["query"] = query
    if evidence:
        result["evidence"] = evidence
    if gold_sql:
        result["gold_sql"] = gold_sql
    if question_id is not None:
        result["question_id"] = question_id
    
    # Execute SQL if requested
    if args.execute and result["sql"]:
        exec_success, exec_msg, exec_data = db_manager.execute_sql(result["sql"])
        result["execution"] = {
            "success": exec_success,
            "message": exec_msg,
            "data": exec_data
        }
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n" + "=" * 60)
        print("=== RESULTS ===")
        print("=" * 60)
        
        if result["sql"]:
            print(f"\nGenerated SQL:")
            print("-" * 40)
            print(result["sql"])
            print("-" * 40)
        
        if gold_sql:
            print(f"\nGold SQL (reference):")
            print("-" * 40)
            print(gold_sql)
            print("-" * 40)
        
        print(f"\nVerification: {result['verification_status']}")
        print(f"Passed: {result['verification_passed']}")
        
        if args.execute and "execution" in result:
            exec_info = result["execution"]
            print(f"\nExecution: {exec_info['message']}")
            if exec_info.get("data", {}).get("rows"):
                rows = exec_info["data"]["rows"]
                cols = exec_info["data"]["columns"]
                print(f"Results ({len(rows)} rows):")
                print(" | ".join(cols))
                print("-" * 40)
                for row in rows[:10]:
                    print(" | ".join(str(v) for v in row))
                if len(rows) > 10:
                    print(f"... and {len(rows) - 10} more rows")
        
        if result["error"]:
            print(f"\nError: {result['error']}")
    
    # Exit code
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
