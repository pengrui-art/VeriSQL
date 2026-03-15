"""
VeriSQL Gradio Web Interface

A web UI for interacting with the VeriSQL agent, featuring:
- SQLite database loading
- Natural language query input
- Real-time agent thinking process visualization
- Results display with SQL, verification status, and execution results
"""
import gradio as gr
import sqlite3
import os
import json
import time
from typing import Generator, Tuple, Optional, Dict, Any
from pathlib import Path

from verisql.agents.state import VeriSQLState, VerificationResult
from verisql.core.ilr import ILR
from verisql.core.dsl import ConstraintSpec
from verisql.core.ltl_compiler import compile_to_ltl
from verisql.agents.nodes import (
    create_llm,
    INTENT_PARSER_PROMPT,
    AUTO_FORMALIZER_PROMPT,
    SQL_GENERATOR_PROMPT,
    SPEC_GENERATOR_PROMPT,
    symbolic_verifier_node, # Need logic from this
)
from verisql.config import SQL_MODEL, SPEC_MODEL, LLM_PROVIDER, get_llm_config
from verisql.utils.z3_utils import verify_sql_against_spec
from verisql.utils.spec_utils import parse_spec_safely
from verisql.utils.diagnosis import diagnose_sql_error, check_result_quality
from verisql.utils.sql_safety import validate_read_only_sql


def _quote_sqlite_ident(name: str) -> str:
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


# ============== Database Utils ==============

class DatabaseManager:
    """Manage SQLite database connections and schema extraction"""
    
    def __init__(self):
        self.db_path: Optional[str] = None
        self.conn: Optional[sqlite3.Connection] = None
        self.schema_info: Dict[str, Any] = {}
    
    def load_database(self, file_path: str) -> Tuple[bool, str, str]:
        """
        Load a SQLite database and extract schema.
        
        Returns: (success, message, schema_display)
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
            
            schema_parts = []
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
                
                # Format for display
                col_strs = [f"  - {c['name']}: {c['type']}" + (" (PK)" if c['primary_key'] else "") 
                           for c in col_info]
                schema_parts.append(f"📊 **{table_name}**\n" + "\n".join(col_strs))
            
            schema_display = "\n\n".join(schema_parts) if schema_parts else "No tables found"
            
            # Check for external descriptions (BIRD-style)
            self._load_external_descriptions()
            
            if self.schema_info.get("descriptions"):
                schema_display += "\n\n--- \n📖 **Semantic Descriptions Loaded**"
                for table, desc_list in self.schema_info["descriptions"].items():
                    schema_display += f"\n- {table}: {len(desc_list)} columns described"

            return True, f"✅ Database loaded: {Path(file_path).name}", schema_display
            
        except Exception as e:
            return False, f"❌ Error loading database: {str(e)}", ""

    def _load_external_descriptions(self):
        """Search for database_description folder and load CSV files"""
        if not self.db_path: return
        
        db_dir = Path(self.db_path).parent
        desc_dir = db_dir / "database_description"
        
        if not desc_dir.exists():
            # Try recursive search if it's a known BIRD structure
            return

        import csv
        self.schema_info["descriptions"] = {}
        
        for csv_file in desc_dir.glob("*.csv"):
            table_name = csv_file.stem
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    self.schema_info["descriptions"][table_name] = list(reader)
            except Exception as e:
                print(f"Error loading description {csv_file}: {e}")
    
    def execute_sql(self, sql: str) -> Tuple[bool, str, list]:
        """Execute SQL and return results"""
        if not self.conn:
            return False, "No database loaded", []

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


# Global database manager
db_manager = DatabaseManager()


# ============== Agent Runner with Streaming ==============

def run_agent_with_streaming(
    query: str,
    schema_info: dict
) -> Generator[Tuple[str, str, str, str], None, None]:
    """
    Run VeriSQL agent with streaming updates for the thinking process.
    
    Yields: (thinking_log, ilr_json, sql, verification_status)
    """
    from verisql.agents.nodes import parse_json_from_markdown
    import re
    
    thinking_log = ""
    ilr_json = ""
    sql = ""
    verification_status = ""
    
    def truncate_str(s: str, max_len: int = 300) -> str:
        """Truncate long strings for display"""
        s = str(s)
        if len(s) > max_len:
            return s[:max_len] + "..."
        return s
    
    try:
        # Check API configuration
        config = get_llm_config()
        if not config["api_key"]:
            thinking_log += f"❌ Error: No API key configured for {LLM_PROVIDER}\n"
            thinking_log += "Please set the API key in .env file\n"
            yield thinking_log, ilr_json, sql, verification_status
            return
        
        # Step 1: Intent Parsing
        thinking_log += "🔍 **Step 1: Intent Parsing**\n"
        thinking_log += f"Using model: {SQL_MODEL} via {LLM_PROVIDER}\n"
        yield thinking_log, ilr_json, sql, verification_status
        
        llm = create_llm(SQL_MODEL)
        # Use raw LLM call + robust parsing instead of JsonOutputParser
        chain = INTENT_PARSER_PROMPT | llm
        
        result = chain.invoke({
            "query": query,
            "schema_info": json.dumps(schema_info, ensure_ascii=False)
        })
        
        try:
            parsed_intent = parse_json_from_markdown(result.content)
        except Exception as parse_err:
            thinking_log += f"⚠️ Intent parsing output error: {truncate_str(str(parse_err))}\n"
            thinking_log += f"Raw response (truncated): {truncate_str(result.content, 500)}\n"
            yield thinking_log, ilr_json, sql, verification_status
            return
        
        thinking_log += f"```json\n{json.dumps(parsed_intent, indent=2, ensure_ascii=False)}\n```\n\n"
        yield thinking_log, ilr_json, sql, verification_status
        
        # Step 2: AutoFormalizer
        thinking_log += "📐 **Step 2: AutoFormalizer (ILR Generation)**\n"
        thinking_log += "Converting intent to ILR (Intent Logic Representation)...\n"
        yield thinking_log, ilr_json, sql, verification_status
        
        llm2 = create_llm(SPEC_MODEL)
        chain2 = AUTO_FORMALIZER_PROMPT | llm2
        
        result2 = chain2.invoke({
            "parsed_intent": json.dumps(parsed_intent, ensure_ascii=False),
            "query": query
        })
        
        try:
            ilr_dict = parse_json_from_markdown(result2.content)
        except Exception as parse_err:
            thinking_log += f"⚠️ ILR parsing error: {truncate_str(str(parse_err))}\n"
            yield thinking_log, ilr_json, sql, verification_status
            return
        
        ilr_json = json.dumps(ilr_dict, indent=2, ensure_ascii=False)
        thinking_log += "✅ ILR generated successfully\n\n"
        yield thinking_log, ilr_json, sql, verification_status
        
        # Iterative Repair Loop
        max_iters = config.get("max_repair_iterations", 3)
        
        repair_count = 0
        repair_feedback = ""
        execution_feedback = ""
        
        while repair_count <= max_iters:
            iteration_msg = f"\n🔄 **Iteration {repair_count + 1}**\n" if repair_count > 0 else ""
            
            # Step 3A: SQL Generation (with potential feedback)
            thinking_log += f"{iteration_msg}🔧 **Step 3A: SQL Generation**\n"
            yield thinking_log, ilr_json, sql, verification_status
            
            chain3 = SQL_GENERATOR_PROMPT | llm
            
            result3 = chain3.invoke({
                "ilr": json.dumps(ilr_dict, ensure_ascii=False),
                "schema_info": json.dumps(schema_info, ensure_ascii=False),
                "dialect": "sqlite",
                "repair_feedback": repair_feedback,
                "execution_feedback": execution_feedback
            })
            
            # Robust SQL extraction
            content = result3.content
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
            
            # Display full thought process (Reasoning + SQL)
            thinking_log += f"{content}\n\n"
            yield thinking_log, ilr_json, sql, verification_status
            
            # --- Runtime Execution Step ---
            execution_ok = True
            if db_manager and db_manager.conn:
                success, msg, data = db_manager.execute_sql(sql)
                if not success:
                    # Smart Diagnosis for SQL Errors
                    diagnosis = diagnose_sql_error(msg, db_manager.schema_info)
                    diag_msg = f" ({diagnosis})" if diagnosis else ""
                    
                    thinking_log += f"⚠️ **Runtime SQL Error**: {msg}{diag_msg}\n"
                    execution_feedback = f"Runtime SQL Error: {msg}{diag_msg}"
                    execution_ok = False
                else:
                    rows = data.get("rows", [])
                    if len(rows) == 0:
                        thinking_log += f"⚠️ **Runtime Warning**: Query returned 0 rows. (Potential data mismatch?)\n"
                        execution_feedback = f"Warning: The query returned 0 rows. This might mean your filters (like strings) are incorrect (e.g., 'California' vs 'CA'). Check the descriptions."
                        execution_ok = False
                    else:
                        # Check for Duplicates
                        dup_warning = check_result_quality(rows)
                        if dup_warning:
                             thinking_log += f"⚠️ **Data Quality Warning**: {dup_warning}\n"
                             execution_feedback = dup_warning
                             execution_ok = False # Trigger repair for duplicates
                        else:
                            # Truncate results to avoid token explosion
                            # We allow up to 50 rows so the agent can see lists (e.g. "List all schools")
                            preview_limit = 50
                            preview_rows = rows[:preview_limit]
                            preview_str = "\n".join([str(r) for r in preview_rows])
                            if len(rows) > preview_limit:
                                preview_str += f"\n... ({len(rows) - preview_limit} more rows. Use COUNT(*) to check total.)"
                            
                            thinking_log += f"✅ **Runtime Check**: Captured {len(rows)} result(s).\n**Sample Data**:\n```\n{preview_str}\n```\n"
                            execution_feedback = ""
            
            if not execution_ok and repair_count < max_iters:
                thinking_log += f"🔄 Triggering repair based on execution feedback...\n"
                yield thinking_log, ilr_json, sql, verification_status
                repair_count += 1
                continue
            # ------------------------------
            
            # Step 3B: Spec Generation (only needed first time)
            if repair_count == 0:
                thinking_log += "📋 **Step 3B: Constraint Specification**\n"
                yield thinking_log, ilr_json, sql, verification_status
                
                chain4 = SPEC_GENERATOR_PROMPT | llm2
                result4 = chain4.invoke({
                    "ilr": json.dumps(ilr_dict, ensure_ascii=False),
                    "query": query,
                    "schema_info": json.dumps(schema_info, ensure_ascii=False)
                })
                
                # Use safe parsing directly
                fallback_table = list(schema_info.get("tables", {}).keys())
                fallback_table = fallback_table[0] if fallback_table else "unknown"
                constraint_spec = parse_spec_safely(result4.content, fallback_table)
                spec_dict = constraint_spec.model_dump()
                
                thinking_log += f"```json\n{json.dumps(spec_dict, indent=2, ensure_ascii=False)}\n```\n\n"
                yield thinking_log, ilr_json, sql, verification_status
            
            # Step 4: Verification
            thinking_log += "🔍 **Step 4: Symbolic Verification**\n"
            yield thinking_log, ilr_json, sql, verification_status
            
            try:
                verify_result = verify_sql_against_spec(sql, constraint_spec, schema_info)
                
                if verify_result.status == "PASS":
                    verification_status = "✅ **VERIFIED** - SQL satisfies all constraints"
                    thinking_log += "✅ Verification PASSED\n"
                    # Add breakdown
                    if hasattr(verify_result, "verification_details") and verify_result.verification_details:
                         thinking_log += "\n**Verification Steps:**\n"
                         for step, status in verify_result.verification_details.items():
                             icon = "✅" if status == "PASS" else "⚠️"
                             thinking_log += f"- {icon} {step}: {status}\n"
                    thinking_log += "\n"
                    break
                else:
                    verification_status = f"⚠️ **{verify_result.status}** - {truncate_str(verify_result.message)}"
                    thinking_log += f"⚠️ Verification: {verify_result.status}\n"
                    
                    # Show breakdown for failure too
                    if hasattr(verify_result, "verification_details") and verify_result.verification_details:
                         thinking_log += "\n**Verification Steps:**\n"
                         for step, status in verify_result.verification_details.items():
                             icon = "✅" if status == "PASS" else "❌"
                             thinking_log += f"- {icon} {step}: {truncate_str(str(status))}\n"
                             
                    if verify_result.missing_constraints:
                        thinking_log += f"\n**Violation Details:**\n"
                        for violation in verify_result.missing_constraints:
                            thinking_log += f"- {truncate_str(str(violation))}\n"
                    
                    if verify_result.counterexample:
                        thinking_log += f"\n**Counterexample (Truncated):**\n"
                        thinking_log += f"```\n{truncate_str(str(verify_result.counterexample), 200)}\n```\n"
                    
                    if repair_count < max_iters:
                        thinking_log += f"\n🛠️ **Initiating Repair Attempt {repair_count + 1}...**\n"
                        repair_feedback = f"Verification failed. Issues: {truncate_str(str(verify_result.missing_constraints), 150)}"
                        repair_count += 1
                    else:
                        thinking_log += "❌ Max repair iterations reached.\n\n"
                        break
                        
            except Exception as e:
                verification_status = f"⚠️ Verification skipped: {truncate_str(str(e))}"
                thinking_log += f"⚠️ Could not verify: {truncate_str(str(e))}\n\n"
                break
            
            yield thinking_log, ilr_json, sql, verification_status
        
        thinking_log += "✅ **Agent completed**\n"
        yield thinking_log, ilr_json, sql, verification_status
        
    except Exception as e:
        thinking_log += f"\n❌ **Error**: {truncate_str(str(e))}\n"
        yield thinking_log, ilr_json, sql, verification_status


# ============== Gradio Interface ==============

def load_database(file) -> Tuple[str, str]:
    """Handle database file upload"""
    if file is None:
        return "No file uploaded", ""
    
    success, message, schema = db_manager.load_database(file.name)
    return message, schema


def run_query(query: str):
    """Run query through VeriSQL agent"""
    if not query.strip():
        yield "Please enter a query", "", "", ""
        return
    
    schema_info = db_manager.schema_info if db_manager.schema_info else {}
    
    for thinking, ilr, sql, status in run_agent_with_streaming(query, schema_info):
        yield thinking, ilr, sql, status


def execute_sql(sql: str) -> str:
    """Execute SQL against loaded database"""
    if not sql.strip():
        return "No SQL to execute"
    
    if not db_manager.conn:
        return "Please load a database first"
    
    success, message, data = db_manager.execute_sql(sql)
    
    if success and data:
        # Format as table
        columns = data.get("columns", [])
        rows = data.get("rows", [])
        
        if columns and rows:
            result = "| " + " | ".join(columns) + " |\n"
            result += "| " + " | ".join(["---"] * len(columns)) + " |\n"
            for row in rows[:50]:  # Limit to 50 rows
                result += "| " + " | ".join(str(v) for v in row) + " |\n"
            
            if len(rows) > 50:
                result += f"\n... and {len(rows) - 50} more rows"
            
            return result
        return message
    
    return message


# Create the Gradio interface
def create_ui():
    """Create the VeriSQL Gradio interface"""
    
    with gr.Blocks(
        title="VeriSQL - Neuro-Symbolic SQL Agent"
    ) as demo:
        
        gr.Markdown("""
        # 🔍 VeriSQL - Neuro-Symbolic Runtime Verification
        
        **A verifiable agent for Text-to-SQL with formal correctness guarantees**
        
        1. Load a SQLite database
        2. Ask questions in natural language
        3. Watch the agent's thinking process
        4. Get verified SQL with formal guarantees
        """)
        
        with gr.Row():
            # Left column: Database & Query
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Database")
                
                db_file = gr.File(
                    label="Upload SQLite Database (.db, .sqlite)",
                    file_types=[".db", ".sqlite", ".sqlite3"],
                    type="filepath"
                )
                db_status = gr.Markdown("No database loaded")
                schema_display = gr.Markdown("", label="Schema")
                
                gr.Markdown("---")
                gr.Markdown("### 💬 Query")
                
                query_input = gr.Textbox(
                    label="Natural Language Question",
                    placeholder="e.g., What is the total sales of active products in Q3?",
                    lines=3
                )
                
                with gr.Row():
                    run_btn = gr.Button("🚀 Run VeriSQL", variant="primary")
                    clear_btn = gr.Button("🗑️ Clear")
            
            # Right column: Results
            with gr.Column(scale=2):
                gr.Markdown("### 🧠 Agent Thinking Process")
                
                thinking_output = gr.Markdown(
                    "Agent will show its reasoning here...",
                    label="Thinking",
                    elem_classes=["thinking-box"]
                )
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### 📐 ILR (Intent Logic Representation)")
                        ilr_output = gr.Code(
                            language="json",
                            label="ILR",
                            lines=10
                        )
                    
                    with gr.Column():
                        gr.Markdown("### 📝 Generated SQL")
                        sql_output = gr.Code(
                            language="sql",
                            label="SQL",
                            lines=10
                        )
                
                verification_output = gr.Markdown("", label="Verification Status")
                
                gr.Markdown("---")
                gr.Markdown("### ▶️ Execute SQL")
                
                execute_btn = gr.Button("Execute SQL", variant="secondary")
                execution_result = gr.Markdown("", label="Execution Result")
        
        # Event handlers
        db_file.change(
            fn=load_database,
            inputs=[db_file],
            outputs=[db_status, schema_display]
        )
        
        run_btn.click(
            fn=run_query,
            inputs=[query_input],
            outputs=[thinking_output, ilr_output, sql_output, verification_output]
        )
        
        clear_btn.click(
            fn=lambda: ("", "", "", ""),
            outputs=[thinking_output, ilr_output, sql_output, verification_output]
        )
        
        execute_btn.click(
            fn=execute_sql,
            inputs=[sql_output],
            outputs=[execution_result]
        )
        
        # Examples
        gr.Markdown("### 📚 Example Queries")
        gr.Examples(
            examples=[
                ["What are the top 5 customers by total order amount?"],
                ["Show me all orders from last quarter"],
                ["Count the number of active products by category"],
                ["What is the average order value for each customer?"],
            ],
            inputs=[query_input]
        )
    
    return demo


def main():
    """Launch the Gradio app"""
    demo = create_ui()
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        server_port=None,  # Auto-find available port
        show_error=True,
        theme=gr.themes.Soft()
    )


if __name__ == "__main__":
    main()
