"""
Smart Diagnostics for Runtime SQL Execution.

Provides heuristics to help the Agent fix SQL errors without guessing.
"""
import difflib
from typing import List, Dict, Any, Tuple, Set

def find_closest_match(word: str, candidates: List[str], cutoff: float = 0.6) -> str:
    """Find the closest matching string from candidates."""
    matches = difflib.get_close_matches(word, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def diagnose_sql_error(error_msg: str, schema_info: Dict[str, Any]) -> str:
    """
    Analyze SQL execution error and provide actionable feedback.
    
    Args:
        error_msg: Exception string (e.g., "no such column: Cit")
        schema_info: Schema dictionary
        
    Returns:
        Suggestion string or empty if no specific diagnosis.
    """
    error_msg = error_msg.lower()
    
    # CASE 1: No such column
    if "no such column" in error_msg:
        # Extract the bad column name
        # typical format: "no such column: Cit" or "no such column: table.Cit"
        try:
            bad_col = error_msg.split("no such column:")[-1].strip().split(".")[-1]
            bad_col = bad_col.strip("'").strip('"')
            
            # Collect all valid columns
            all_cols = []
            for table, cols in schema_info.get("tables", {}).items():
                for c in cols:
                    all_cols.append(c["name"])
            
            # Find match
            suggestion = find_closest_match(bad_col, all_cols)
            if suggestion:
                return f"Diagnosis: Column '{bad_col}' does not exist. Did you mean '{suggestion}'?"
        except:
            pass
            
    # CASE 2: No such table
    elif "no such table" in error_msg:
        try:
            bad_table = error_msg.split("no such table:")[-1].strip()
            all_tables = list(schema_info.get("tables", {}).keys())
            suggestion = find_closest_match(bad_table, all_tables)
            if suggestion:
                return f"Diagnosis: Table '{bad_table}' does not exist. Did you mean '{suggestion}'?"
        except:
            pass
            
    return ""

def check_result_quality(rows: List[tuple]) -> str:
    """
    Check if results look suspicious (e.g., duplicates).
    
    Returns:
        Warning message or empty string.
    """
    if not rows:
        return ""
        
    total_count = len(rows)
    
    # Check for duplicates using set (rows must be hashable tuples)
    try:
        unique_rows = set(rows)
        unique_count = len(unique_rows)
        
        # If > 20% duplicates and total count > 1
        if total_count > 1 and (total_count - unique_count) / total_count > 0.2:
            return f"Warning: High duplication detected ({total_count} rows, only {unique_count} unique). You might be missing a DISTINCT or have an incorrect JOIN."
    except:
        pass # In case rows contain unhashable types (lists)
        
    return ""
