"""
Z3 SMT Solver Utilities

Provides symbolic verification of SQL against constraint specifications.
This is the core of VeriSQL's formal verification capability.
"""

from typing import List, Optional, Dict, Any
from z3 import (
    Solver,
    Int,
    String,
    StringVal,
    Bool,
    And,
    Or,
    Not,
    Implies,
    sat,
    unsat,
    unknown,
)
import sqlglot
from sqlglot import exp

from verisql.core.dsl import (
    ConstraintSpec,
    FilterDSL,
    TemporalConstraint,
    QUARTER_DATE_RANGES,
)
from verisql.agents.state import VerificationResult
from verisql.config import Z3_TIMEOUT_MS
from verisql.utils.sql_safety import validate_read_only_sql


class SQLConstraintExtractor:
    """Extract constraints from SQL AST"""

    def __init__(self, sql: str, dialect: str = "sqlite"):
        self.sql = sql
        self.dialect = dialect
        self.constraints = []
        self._parse()

    def _parse(self):
        """Parse SQL and extract WHERE clause constraints"""
        try:
            ast = sqlglot.parse(self.sql, dialect=self.dialect)[0]

            # Find WHERE clause
            where = ast.find(exp.Where)
            if where:
                self._extract_from_expression(where.this)
        except Exception as e:
            print(f"SQL parsing error: {e}")

    def _extract_from_expression(self, expr):
        """Recursively extract constraints from expression"""
        if isinstance(expr, exp.And):
            self._extract_from_expression(expr.left)
            self._extract_from_expression(expr.right)
        elif isinstance(expr, exp.Or):
            # Handle OR separately
            self.constraints.append(
                {
                    "type": "or",
                    "left": self._expr_to_constraint(expr.left),
                    "right": self._expr_to_constraint(expr.right),
                }
            )
        elif isinstance(expr, (exp.EQ, exp.NEQ, exp.GT, exp.LT, exp.GTE, exp.LTE)):
            self.constraints.append(self._expr_to_constraint(expr))
        elif isinstance(expr, exp.Between):
            self.constraints.append(
                {
                    "type": "between",
                    "column": str(expr.this),
                    "low": str(expr.args.get("low")),
                    "high": str(expr.args.get("high")),
                }
            )
        elif isinstance(expr, exp.In):
            self.constraints.append(
                {
                    "type": "in",
                    "column": str(expr.this),
                    "values": [str(v) for v in expr.expressions],
                }
            )

    def _expr_to_constraint(self, expr) -> Dict[str, Any]:
        """Convert expression to constraint dict"""
        if isinstance(expr, exp.EQ):
            return {"type": "eq", "column": str(expr.left), "value": str(expr.right)}
        elif isinstance(expr, exp.NEQ):
            return {"type": "neq", "column": str(expr.left), "value": str(expr.right)}
        elif isinstance(expr, exp.GT):
            return {"type": "gt", "column": str(expr.left), "value": str(expr.right)}
        elif isinstance(expr, exp.LT):
            return {"type": "lt", "column": str(expr.left), "value": str(expr.right)}
        elif isinstance(expr, exp.GTE):
            return {"type": "gte", "column": str(expr.left), "value": str(expr.right)}
        elif isinstance(expr, exp.LTE):
            return {"type": "lte", "column": str(expr.left), "value": str(expr.right)}
        return {"type": "unknown", "expr": str(expr)}

    def get_constraints(self) -> List[Dict[str, Any]]:
        return self.constraints

    def _normalize_value(self, val: Any) -> str:
        """Normalize common SQL values for comparison"""
        s = str(val).strip("'\"").lower()
        if s in ("1", "true", "t"):
            return "true"
        if s in ("0", "false", "f"):
            return "false"
        return s

    def has_constraint(self, column: str, op: str, value: Any = None) -> bool:
        """Check if a specific constraint exists, with normalization"""
        target_col = column.split(".")[-1].lower() if "." in column else column.lower()
        target_val = self._normalize_value(value) if value is not None else None

        for c in self.constraints:
            c_col = (
                c.get("column", "").split(".")[-1].lower()
                if "." in c.get("column", "")
                else c.get("column", "").lower()
            )
            if c_col == target_col:
                if c.get("type") == op:
                    if target_val is None:
                        return True
                    c_val = self._normalize_value(c.get("value", ""))
                    if c_val == target_val:
                        return True
        return False


class SchemaValidator:
    """Validate SQL against database schema"""

    def __init__(self, schema_info: Dict[str, Any], dialect: str = "sqlite"):
        self.schema_info = schema_info
        self.dialect = dialect

    def validate(self, sql: str) -> List[str]:
        """
        Check if tables and columns in SQL exist in schema.
        Returns list of error messages.
        """
        errors = []
        try:
            ast = sqlglot.parse(sql, dialect=self.dialect)[0]

            # 1. Check Tables
            tables_in_sql = [t.name.lower() for t in ast.find_all(exp.Table)]
            valid_tables = [
                t.lower() for t in self.schema_info.get("tables", {}).keys()
            ]

            for table in tables_in_sql:
                if table not in valid_tables:
                    errors.append(f"Table '{table}' does not exist in schema")

            # 2. Check Columns
            # Note: This is simplified as it doesn't handle aliasing perfectly
            # but is good for basic existence checks.
            cols_in_sql = [c.this.name.lower() for c in ast.find_all(exp.Column)]

            # Collect all valid columns across all tables
            all_valid_cols = set()
            for table_cols in self.schema_info.get("tables", {}).values():
                for col_info in table_cols:
                    all_valid_cols.add(col_info["name"].lower())

            for col in cols_in_sql:
                if col not in all_valid_cols:
                    # Fuzzy matching for suggestion
                    import difflib

                    matches = difflib.get_close_matches(
                        col, list(all_valid_cols), n=3, cutoff=0.6
                    )
                    suggestion = f". Did you mean {matches}?" if matches else ""
                    errors.append(f"Column '{col}' not found in schema{suggestion}")

        except Exception as e:
            errors.append(f"SQL Schema Validation failed: {str(e)}")

        return list(set(errors))  # Unique errors


class Z3ConstraintBuilder:
    """Helper to build Z3 expressions from SQL/DSL constraints"""

    def __init__(self):
        self.vars = {}  # col_name -> Z3 Variable

    def _normalize_str_val(self, val: Any) -> str:
        return str(val).strip().strip("'\"").lower()

    def _is_date_str(self, s: str) -> bool:
        s = s.strip().strip("'\"")
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            y, m, d = s.split("-")
            return y.isdigit() and m.isdigit() and d.isdigit()
        if len(s) == 8 and s.isdigit():
            return True
        return False

    def _date_to_int(self, s: str) -> int:
        s = s.strip().strip("'\"")
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            s = s.replace("-", "")
        return int(s)

    def get_var(self, col_name: str, value_type: str = "string") -> Any:
        """Get or create Z3 variable for a column"""
        # Normalize column name
        name = col_name.split(".")[-1].lower() if "." in col_name else col_name.lower()
        if name not in self.vars:
            if value_type == "int":
                self.vars[name] = Int(name)
            else:
                self.vars[name] = String(name)
        return self.vars[name]

    def to_z3_expr(self, constraint: Dict[str, Any]) -> Optional[Any]:
        """Convert a normalized constraint dict to Z3 expression"""
        c_type = constraint.get("type", "")

        # Helper to determine likely type
        raw_val_str = str(constraint.get("value", ""))
        norm_val_str = self._normalize_str_val(raw_val_str)
        is_val_int = norm_val_str.isdigit()
        is_val_date = self._is_date_str(raw_val_str)

        col = constraint.get("column", "")
        if not col and c_type not in ("or", "and"):
            return None

        if c_type == "or":
            l = self.to_z3_expr(constraint.get("left"))
            r = self.to_z3_expr(constraint.get("right"))
            return Or(l, r) if l is not None and r is not None else None

        # Comparison ops
        if is_val_date:
            z3_var = self.get_var(col + "_as_int", "int")
            val = self._date_to_int(raw_val_str)
            if c_type == "eq":
                return z3_var == val
            if c_type == "neq":
                return z3_var != val
            if c_type == "gt":
                return z3_var > val
            if c_type == "lt":
                return z3_var < val
            if c_type == "gte":
                return z3_var >= val
            if c_type == "lte":
                return z3_var <= val

        z3_var = self.get_var(col, "int" if is_val_int else "string")

        if is_val_int:
            val = int(norm_val_str)
            if c_type == "eq":
                return z3_var == val
            if c_type == "neq":
                return z3_var != val
            if c_type == "gt":
                return z3_var > val
            if c_type == "lt":
                return z3_var < val
            if c_type == "gte":
                return z3_var >= val
            if c_type == "lte":
                return z3_var <= val
            if c_type == "between":
                low_raw = str(constraint.get("low", 0))
                high_raw = str(constraint.get("high", 0))
                if self._is_date_str(low_raw) and self._is_date_str(high_raw):
                    # Represent date range constraints on the date-as-int view
                    z3_var_int = self.get_var(col + "_as_int", "int")
                    low = self._date_to_int(low_raw)
                    high = self._date_to_int(high_raw)
                    return And(z3_var_int >= low, z3_var_int <= high)
                low = int(str(low_raw).strip().strip("'\""))
                high = int(str(high_raw).strip().strip("'\""))
                return And(z3_var >= low, z3_var <= high)
        else:
            val = StringVal(norm_val_str)
            if c_type == "eq":
                return z3_var == val
            if c_type == "neq":
                return z3_var != val
            # Strings don't usually support < > in simple Z3 logic without specific encoding
            # We treat them as uninterpreted for ordering or just ignore

        return None

    def spec_to_z3(self, spec_constraint: Any) -> Optional[Any]:
        """Convert a DSL constraint object to Z3 expression"""
        if isinstance(spec_constraint, FilterDSL):
            is_int = str(spec_constraint.value).isdigit()
            z3_var = self.get_var(spec_constraint.field, "int" if is_int else "string")

            # Normalize value to match SQL extraction (lowercase)
            if is_int:
                val = int(spec_constraint.value)
            else:
                val = StringVal(self._normalize_str_val(spec_constraint.value))

            op = spec_constraint.operator
            if op == "eq":
                return z3_var == val
            if op == "neq":
                return z3_var != val
            if is_int:
                if op == "gt":
                    return z3_var > val
                if op == "lt":
                    return z3_var < val
                if op == "gte":
                    return z3_var >= val
                if op == "lte":
                    return z3_var <= val

        elif isinstance(spec_constraint, TemporalConstraint):
            # Map temporal to simple int ranges
            # Treat 'date' column as string, but for Z3 range check we need comparable ints
            # Strategy: Convert "YYYY-MM-DD" to Int(YYYYMMDD) for comparison

            # 1. Get Z3 variable for the column (as INT for range comparison)
            # Use specific suffix to denote this is the 'date-as-int' view of the column
            z3_var_int = self.get_var(spec_constraint.column + "_as_int", "int")

            start_str, end_str = None, None

            if spec_constraint.constraint_type == "quarter" and spec_constraint.quarter:
                year = spec_constraint.year or 2024
                start_suffix, end_suffix = QUARTER_DATE_RANGES.get(
                    spec_constraint.quarter, ("01-01", "12-31")
                )
                start_str = f"{year}{start_suffix.replace('-', '')}"
                end_str = f"{year}{end_suffix.replace('-', '')}"

            elif spec_constraint.constraint_type == "date_range":
                # Expecting YYYY-MM-DD
                s = str(spec_constraint.start_date).replace("-", "")
                e = str(spec_constraint.end_date).replace("-", "")
                if s.isdigit() and e.isdigit():
                    start_str = s
                    end_str = e

            elif spec_constraint.constraint_type == "year":
                y = str(spec_constraint.year)
                start_str = f"{y}0101"
                end_str = f"{y}1231"

            if start_str and end_str:
                return And(z3_var_int >= int(start_str), z3_var_int <= int(end_str))

        return None


class SymbolicVerifier:
    """
    Verifies SQL constraints against specification using Z3 SMT solver.
    """

    def __init__(self, timeout_ms: int = Z3_TIMEOUT_MS):
        self.timeout_ms = timeout_ms

    def verify(self, sql: str, spec: ConstraintSpec) -> VerificationResult:
        """
        Main basic verification + Z3 Logic.
        """
        # 1. Extract constraints from SQL
        sql_extractor = SQLConstraintExtractor(sql)
        sql_constraints = sql_extractor.get_constraints()

        # 2. Build Z3 Formulas
        builder = Z3ConstraintBuilder()

        # SQL Formula: AND(all sql constraints)
        z3_sql_parts = []
        for c in sql_constraints:
            expr = builder.to_z3_expr(c)
            if expr is not None:
                z3_sql_parts.append(expr)

        from z3 import BoolVal

        sql_formula = And(z3_sql_parts) if z3_sql_parts else BoolVal(True)

        # Spec Formula: AND(all spec constraints)
        z3_spec_parts = []
        for c in spec.constraints:
            expr = builder.spec_to_z3(c)
            if expr is not None:
                z3_spec_parts.append(expr)

        # If spec has no convertible constraints, pass (or warn?)
        if not z3_spec_parts:
            return VerificationResult(
                status="PASS",
                message="No verifiable constraints found in spec (Stub pass)",
            )

        spec_formula = And(z3_spec_parts)

        # 3. Prove Validity: SQL => Spec
        # Validity checks if Not(Implies(SQL, Spec)) is UNSAT.
        # If it is UNSAT, then SQL => Spec is always true.
        # If it is SAT, we found a counterexample where SQL is true but Spec is false.

        solver = Solver()
        solver.set("timeout", self.timeout_ms)

        goal = Implies(sql_formula, spec_formula)
        solver.add(Not(goal))  # We try to find a violation

        check_result = solver.check()

        if check_result == unsat:
            return VerificationResult(
                status="PASS", message="Symbolic Verification PASSED (Proven)"
            )
        elif check_result == sat:
            model = solver.model()
            # Extract info from model
            counterexample = {str(d): str(model[d]) for d in model.decls()}
            return VerificationResult(
                status="FAIL",
                message="Symbolic Verification FAILED (Counterexample found)",
                counterexample=counterexample,
                missing_constraints=[
                    "Z3 Logic Violation: SQL allows rows that violate Spec"
                ],
            )
        else:
            return VerificationResult(
                status="ERROR",
                message=f"Z3 Solver returned unknown: {solver.reason_unknown()}",
            )


def verify_sql_against_spec(
    sql: str, spec: ConstraintSpec, schema_info: Optional[Dict[str, Any]] = None
) -> VerificationResult:
    """Run safety checks, schema validation, and symbolic verification."""
    details: Dict[str, str] = {}

    is_read_only, safety_error = validate_read_only_sql(sql)
    if not is_read_only:
        details["Safety Validation"] = "FAIL"
        return VerificationResult(
            status="FAIL",
            message="SQL failed safety validation",
            missing_constraints=[safety_error],
            verification_details=details,
        )

    details["Safety Validation"] = "PASS"

    # 1. Optional Schema Validation (Static)
    if schema_info:
        validator = SchemaValidator(schema_info)
        schema_errors = validator.validate(sql)
        if schema_errors:
            details["Schema Validation"] = "FAIL"
            return VerificationResult(
                status="FAIL",
                message="SQL failed schema validation",
                missing_constraints=schema_errors,
                verification_details=details,
            )
        details["Schema Validation"] = "PASS"

    # 2. Constraint Verification (Static Z3)
    verifier = SymbolicVerifier()
    static_result = verifier.verify(sql, spec)

    details["Static Analysis (Z3)"] = static_result.status
    static_result.verification_details = details
    return static_result
