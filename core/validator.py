"""
validator.py
Validates generated SQL against real schema rules.
Aligned with actual database column names and status values.
"""

import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_valid: bool
    errors:   list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def __str__(self):
        if self.is_valid and not self.warnings:
            return "✅ SQL is valid."
        lines = []
        if self.is_valid:
            lines.append("✅ SQL is valid.")
        else:
            lines.append("❌ SQL validation failed:")
            for err in self.errors:
                lines.append(f"  ERROR   → {err}")
        for warn in self.warnings:
            lines.append(f"  WARNING → {warn}")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# FORBIDDEN OPERATIONS
# ─────────────────────────────────────────────

FORBIDDEN_OPERATIONS = [
    r'\bDELETE\b', r'\bUPDATE\b', r'\bINSERT\b',
    r'\bDROP\b',   r'\bTRUNCATE\b', r'\bALTER\b',
    r'\bCREATE\b', r'\bGRANT\b',    r'\bREVOKE\b',
]

# ─────────────────────────────────────────────
# JOIN ENFORCEMENT — aligned with real schema
# ─────────────────────────────────────────────

JOIN_ENFORCEMENT_RULES = [
    {
        "requires":   "refunds",
        "depends_on": "returns",
        "error": "refunds used without returns. Path must be: order_items → returns → refunds"
    },
    {
        "requires":   "sellers",
        "depends_on": "order_items",
        "error": "sellers used without order_items. Always join sellers via order_items.seller_id"
    },
    {
        "requires":   "seller_settlements",
        "depends_on": "order_items",
        "error": "seller_settlements used without order_items. Join via order_items.order_item_id"
    },
    {
        "requires":   "inventory_movements",
        "depends_on": "inventory",
        "error": "inventory_movements used without inventory. Join via inventory.inventory_id"
    },
]

# ─────────────────────────────────────────────
# WRONG COLUMN NAMES — catch LLM hallucinations
# ─────────────────────────────────────────────

WRONG_COLUMNS = [
    {
        "pattern": r'\brefunds?\.["\s]*refund_amount\b',
        "error":   "Wrong column: refunds.refund_amount does not exist. Use refunds.refunded_amount"
    },
    {
        "pattern": r'\bseller_settlements?\.["\s]*settlement_amount\b',
        "error":   "Wrong column: seller_settlements.settlement_amount does not exist. Use seller_settlements.net_payable"
    },
    {
        "pattern": r'\breturns?\.["\s]*order_id\b',
        "error":   "Wrong column: returns.order_id does not exist. returns joins via order_item_id"
    },
    {
        "pattern": r"settlement_status\s*=\s*['\"]Settled['\"]",
        "error":   "Wrong status value: 'Settled' is not valid. Use 'Paid' or 'Processed'"
    },
    {
        "pattern": r"refund_status\s*=\s*['\"]Processed['\"]",
        "error":   "Wrong status value for refunds: use 'Completed' not 'Processed'"
    },
    {
        "pattern": r'\border_items?\.["\s]*order_status\b',
        "error":   "Wrong column: order_status is on orders table, not order_items. Use o.order_status"
    },
]

# ─────────────────────────────────────────────
# PII COLUMNS — never expose these
# ─────────────────────────────────────────────

PII_COLUMNS = [
    r'\bc\.email\b', r'\bc\.phone\b', r'\bc\.address\b', r'\bc\.mobile\b',
    r'\bcustomers\.email\b', r'\bcustomers\.phone\b', r'\bcustomers\.address\b',
]

# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

def _table_present(sql: str, table: str) -> bool:
    return bool(re.search(rf'\b{re.escape(table)}\b', sql, re.IGNORECASE))


# ─────────────────────────────────────────────
# MAIN VALIDATOR
# ─────────────────────────────────────────────

def validate_sql(sql: str) -> ValidationResult:
    """
    Validates generated SQL against business rules and real schema constraints.
    """
    errors   = []
    warnings = []

    # 1. Must be a SELECT
    if not sql.strip().upper().startswith("SELECT"):
        errors.append("Query must start with SELECT. Write operations are not allowed.")

    # 2. Forbidden DML/DDL
    for pattern in FORBIDDEN_OPERATIONS:
        if re.search(pattern, sql, re.IGNORECASE):
            op = re.sub(r'\\b', '', pattern).upper()
            errors.append(f"Forbidden operation detected: {op}")

    # 3. No SELECT *
    if re.search(r'SELECT\s+\*', sql, re.IGNORECASE):
        errors.append("SELECT * is forbidden. Name columns explicitly.")

    # 4. PII exposure
    for pattern in PII_COLUMNS:
        if re.search(pattern, sql, re.IGNORECASE):
            errors.append("PII column detected. Remove customer personal data from SELECT.")
            break

    # 5. Join enforcement
    for rule in JOIN_ENFORCEMENT_RULES:
        if _table_present(sql, rule["requires"]) and not _table_present(sql, rule["depends_on"]):
            errors.append(rule["error"])

    # 6. Wrong column names / status values (schema violations)
    for check in WRONG_COLUMNS:
        if re.search(check["pattern"], sql, re.IGNORECASE):
            errors.append(check["error"])

    # 7. Warnings (non-blocking best practices)
    if not re.search(r'\bWHERE\b', sql, re.IGNORECASE):
        warnings.append("No WHERE clause. Consider adding a time filter.")

    if not re.search(r'\bORDER\s+BY\b', sql, re.IGNORECASE):
        warnings.append("No ORDER BY. Consider ordering by the main metric DESC.")

    if not re.search(r'\bLIMIT\b', sql, re.IGNORECASE):
        warnings.append("No LIMIT clause. May return very large result sets.")

    if re.search(r'\bSUM\b|\bAVG\b', sql, re.IGNORECASE) and \
       not re.search(r'\bCOALESCE\b', sql, re.IGNORECASE):
        warnings.append("SUM/AVG without COALESCE. Add COALESCE(value, 0) for null safety.")

    is_valid = len(errors) == 0
    return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
