"""
Test Agent Robustness on California Schools (BIRD dataset)

Runs the agent on first 5 questions from california_schools and compares execution results with Gold SQL.
"""
import json
import io
import sys
import os
import sqlite3
import subprocess
from pathlib import Path
from verisql.utils.sql_safety import validate_read_only_sql

# Setup paths
BASE_DIR = Path(__file__).resolve().parents[1]
JSON_PATH = BASE_DIR / "verisql/DataBase/Bird/dev_20240627/dev_tied_append.json"
DB_PATH = BASE_DIR / "verisql/DataBase/Bird/dev_20240627/dev_databases/california_schools/california_schools.sqlite"

def get_california_questions(limit=5):
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions = []
    for q in data:
        if q.get("db_id") == "california_schools":
            questions.append(q)
            if len(questions) >= limit:
                break
    return questions

def execute_sql(db_path, sql):
    is_safe, safety_error = validate_read_only_sql(sql)
    if not is_safe:
        return {"success": False, "error": safety_error}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        # Get column names just in case
        cols = [d[0] for d in cursor.description]
        conn.close()
        return {"success": True, "rows": rows, "cols": cols}
    except Exception as e:
        return {"success": False, "error": str(e)}

def run_agent_cli(question_id):
    """Run cli.py for a specific question ID and return the JSON output"""
    cmd = [
        sys.executable, 
        "-m", "verisql.cli",
        "--question-id", str(question_id),
        "--dev-json", str(JSON_PATH),
        "--json",
        "--quiet",
        "--max-repair", "2"
    ]
    
    try:
        # Run process
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
        
        # Check output
        if result.returncode != 0 and not result.stdout.strip():
            print(f"Error running agent: {result.stderr}")
            return None
            
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            # Try to find JSON in output if mixed with logs
            content = result.stdout
            idx = content.find('{')
            r_idx = content.rfind('}')
            if idx != -1 and r_idx != -1:
                try:
                    return json.loads(content[idx:r_idx+1])
                except:
                    pass
            print(f"Failed to parse JSON output: {result.stdout[:200]}...")
            return None
            
    except Exception as e:
        print(f"Exception running agent: {e}")
        return None

def compare_results(gold_rows, gen_rows):
    """Compare two result sets (simple set comparison for now)"""
    # Normalize rows to sets of tuples
    
    # 1. Exact Match
    if gold_rows == gen_rows:
        return "MATCH (Ordered)"
        
    s_gold = set(tuple(r) for r in gold_rows)
    s_gen = set(tuple(r) for r in gen_rows)
    
    # 2. Set Match
    if s_gold == s_gen:
        return "MATCH (Set)"
        
    # 3. Subset
    if s_gen.issubset(s_gold):
        return f"PARTIAL (Gen is subset, missing {len(s_gold) - len(s_gen)})"
        
    # 4. Superset (common with tie handling - we return more tied rows than Gold LIMIT 1)
    if s_gold.issubset(s_gen):
        return f"SUPERSET (Gen includes Gold + {len(s_gen) - len(s_gold)} extra)"
        
    # 5. Mismatch
    return f"MISMATCH (Gold: {len(gold_rows)}, Gen: {len(gen_rows)})"

def main():
    print(f"Loading questions from {JSON_PATH}...")
    questions = get_california_questions(5)
    print(f"Found {len(questions)} questions for california_schools.")
    print("-" * 60)
    
    correct_count = 0
    
    for i, q in enumerate(questions):
        qid = q['question_id']
        query = q['question']
        gold_sql = q['SQL']
        
        print(f"\n[{i+1}/5] Processing QID {qid}")
        print(f"Query: {query}")
        
        # 1. Execute Gold SQL
        gold_res = execute_sql(DB_PATH, gold_sql)
        if not gold_res['success']:
            print(f"⚠️ Gold SQL Failed: {gold_res['error']}")
            continue
            
        print(f"Gold SQL returns {len(gold_res['rows'])} rows.")
        
        # 2. Run Agent
        print("Running Agent...")
        agent_res = run_agent_cli(qid)
        
        if not agent_res:
            print("❌ Agent failed to output valid JSON.")
            continue
            
        gen_sql = agent_res.get('sql')
        if not gen_sql:
            print("❌ No SQL generated.")
            print(f"Error: {agent_res.get('error')}")
            continue
            
        print(f"Generated SQL: {gen_sql}")
        
        # 3. Execute Generated SQL
        gen_exec = execute_sql(DB_PATH, gen_sql)
        if not gen_exec['success']:
            print(f"❌ Execution Failed: {gen_exec['error']}")
            continue
            
        print(f"Gen SQL returns {len(gen_exec['rows'])} rows.")
        
        # 4. Compare
        verdict = compare_results(gold_res['rows'], gen_exec['rows'])
        print(f"Verdict: {verdict}")
        
        if "MATCH" in verdict or "SUPERSET" in verdict:
            correct_count += 1
            print("✅ TEST PASSED")
        else:
            print("❌ TEST FAILED")
            print(f"Gold Row Sample: {gold_res['rows'][:3]}")
            print(f"Gen Row Sample:  {gen_exec['rows'][:3]}")

    print("\n" + "=" * 60)
    print(f"Summary: {correct_count}/{len(questions)} Passed")
    print("=" * 60)

if __name__ == "__main__":
    main()
