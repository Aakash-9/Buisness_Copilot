"""
prompt_builder.py
Builds a structured, tight prompt for the LLM.
Aligned with real database schema — injects column corrections, status values,
segmentation hints, and correct join paths.
"""


def _format_metrics(metrics: list) -> str:
    if not metrics:
        return "  No specific metric detected — infer the correct aggregation from the question.\n  Use item_price from order_items or final_payable from orders as appropriate."
    lines = []
    for key, data in metrics:
        formula = data.get('formula_logic', {})
        lines.append(f"  METRIC : {key.upper()}")
        lines.append(f"    Description : {data.get('description', '')}")
        lines.append(f"    Aggregation : {formula.get('aggregation', '')}")
        lines.append(f"    Filter      : {formula.get('filter', '')}")
        if formula.get('join'):
            lines.append(f"    Join        : {formula.get('join')}")
        lines.append("")
    return "\n".join(lines)


def _format_joins(join_paths: dict) -> str:
    if not join_paths:
        return "  Core path: FROM orders o INNER JOIN order_items oi ON oi.order_id = o.order_id"
    lines = []
    for name, path in join_paths.items():
        note = f"  -- {path['note']}" if path.get('note') else ""
        lines.append(
            f"  {path['join_type']} JOIN {path['to']} {path.get('alias', {}).get(path['to'], '')} "
            f"ON {path['condition']}{note}"
        )
    return "\n".join(lines)


def _format_rules(join_rules: list) -> str:
    if not join_rules:
        return ""
    lines = ["⚠️  JOIN ENFORCEMENT (these violations will produce wrong results):"]
    for rule in join_rules:
        lines.append(f"  ✗ {rule['error']}")
    return "\n".join(lines)


def _format_column_corrections(corrections: list) -> str:
    if not corrections:
        return ""
    lines = ["⚠️  COLUMN NAME CORRECTIONS (use ONLY the correct names):"]
    for c in corrections:
        lines.append(f"  ✗ WRONG : {c['wrong']}")
        lines.append(f"  ✓ RIGHT : {c['correct']}")
    return "\n".join(lines)


def _format_sql_standards(standards: dict) -> str:
    # Only inject the most critical categories — skip status_values (handled separately)
    priority_categories = ['select', 'joins', 'column_names', 'aggregation', 'ordering', 'safety']
    lines = []
    for cat in priority_categories:
        rules = standards.get(cat, [])
        if isinstance(rules, list):
            for rule in rules:
                lines.append(f"  • [{cat.upper()}] {rule}")
    return "\n".join(lines)


def _format_status_values(standards: dict) -> str:
    status = standards.get('status_values', {})
    if not status:
        return ""
    lines = ["VALID STATUS VALUES (use only these exact strings):"]
    for col, values in status.items():
        lines.append(f"  {col}: {values}")
    return "\n".join(lines)


def _format_aliases(aliases: dict) -> str:
    return "  " + ", ".join(f"{table} → {alias}" for table, alias in aliases.items())


def _format_segmentation(segments: list) -> str:
    if not segments:
        return ""
    return f"  Detected GROUP BY dimensions: {', '.join(segments)}\n  Include these in SELECT and GROUP BY clauses."


def _format_filters(filters: dict) -> str:
    if not filters:
        return ""
    all_sql = filters.get('all_sql_filters', [])
    top_n   = filters.get('top_n', {})
    if not all_sql and not top_n:
        return ""
    lines = ["ADDITIONAL WHERE FILTERS (inject these into the WHERE clause):"]
    for sql in all_sql:
        lines.append(f"  AND {sql}")
    if top_n:
        lines.append(f"\nLIMIT OVERRIDE: Use {top_n.get('sql', 'LIMIT 20')}")
        if top_n.get('order') == 'ASC':
            lines.append("  ORDER BY metric ASC (bottom N requested)")
    return "\n".join(lines)


def _format_intent(intent: str, list_cols: list) -> str:
    if intent == 'list':
        cols = ', '.join(list_cols) if list_cols else 'o.order_id, o.order_date, o.final_payable, o.payment_mode, o.order_status'
        return f"""QUERY INTENT: LIST individual rows (NOT an aggregate query)
  - Do NOT use GROUP BY
  - Do NOT use COUNT/SUM/AVG as the main output
  - SELECT these columns: {cols}
  - Apply WHERE filters and return matching rows
  - Use ORDER BY o.order_date DESC"""
    else:
        return "QUERY INTENT: AGGREGATE / ANALYTICS — use COUNT, SUM, AVG with GROUP BY as appropriate"


def build_prompt(user_query: str, context: dict) -> str:
    """
    Builds the final LLM prompt string.
    Args:
        user_query : raw natural language question
        context    : structured dict from context_selector.select_context()
    Returns:
        Full prompt string ready to send to Groq
    """
    metrics_block      = _format_metrics(context.get('metrics', []))
    joins_block        = _format_joins(context.get('join_paths', {}))
    rules_block        = _format_rules(context.get('join_rules', []))
    corrections_block  = _format_column_corrections(context.get('column_corrections', []))
    standards_block    = _format_sql_standards(context.get('sql_standards', {}))
    status_block       = _format_status_values(context.get('sql_standards', {}))
    aliases_block      = _format_aliases(context.get('table_aliases', {}))
    time_filter        = context.get('time_filter', "o.order_date >= date_trunc('month', current_date)")
    time_column        = context.get('time_column', 'o.order_date')
    output_rules       = "\n".join(f"  • {r}" for r in context.get('output_format', []))
    segmentation_block = _format_segmentation(context.get('segmentation', []))
    filters_block      = _format_filters(context.get('filters', {}))
    intent_block       = _format_intent(context.get('intent', 'aggregate'), context.get('list_columns', []))

    prompt = f"""You are an expert PostgreSQL SQL generator for an e-commerce analytics platform.
You MUST follow every rule below with zero deviation. Never guess column names.

════════════════════════════════════════════════════
DATABASE TABLES:
  orders, order_items, products, sellers, customers,
  payments, shipments, warehouses, returns, refunds,
  seller_settlements, inventory, inventory_movements

KEY COLUMN FACTS:
  orders        : order_id, customer_id, order_date, order_status, payment_mode,
                  total_amount, discount_amount, final_payable, order_channel
  order_items   : order_item_id, order_id, product_id, seller_id, quantity, item_price, item_status
  customers     : customer_id, signup_date, city, state, gender, age_group, loyalty_tier
  products      : product_id, seller_id, brand, category, sub_category, size, color,
                  mrp, selling_price, season, is_returnable
  sellers       : seller_id, seller_name, seller_type, onboarding_date, seller_rating,
                  seller_region, commission_rate, risk_flag, is_active
  payments      : payment_id, order_id, payment_method, payment_status, payment_date, paid_amount, gateway
  shipments     : shipment_id, order_id, warehouse_id, courier_partner, shipped_date,
                  promised_delivery_date, actual_delivery_date, delivery_status
  warehouses    : warehouse_id
  returns       : return_id, order_item_id, return_date, return_reason, return_type,
                  return_status, pickup_date, refund_amount
  refunds       : refund_id, return_id, refund_method, refund_status, refund_date, refunded_amount
  seller_settlements : settlement_id, seller_id, order_item_id, gross_amount,
                       commission_amount, net_payable, settlement_date, settlement_status
  inventory     : inventory_id, product_id, seller_id, warehouse_id,
                  available_qty, reserved_qty, damaged_qty, last_updated
  inventory_movements : movement_id, inventory_id, movement_type, quantity, reference_id, movement_date
════════════════════════════════════════════════════

TABLE ALIASES (always use these):
{aliases_block}

════════════════════════════════════════════════════
{intent_block}

════════════════════════════════════════════════════
METRIC DEFINITION:
{metrics_block}
════════════════════════════════════════════════════

JOIN PATHS TO USE:
{joins_block}

{rules_block}

════════════════════════════════════════════════════
{corrections_block}

════════════════════════════════════════════════════
{status_block}

════════════════════════════════════════════════════
TIME FILTER:
  Apply: WHERE {time_filter}
  Time column for this query: {time_column}

════════════════════════════════════════════════════
{filters_block if filters_block else "No additional filters detected."}

════════════════════════════════════════════════════
SEGMENTATION / GROUP BY:
{segmentation_block if segmentation_block else "  No specific grouping detected — aggregate at total level unless question implies breakdown."}

════════════════════════════════════════════════════
SQL STANDARDS (mandatory):
{standards_block}

════════════════════════════════════════════════════
OUTPUT FORMAT:
{output_rules}

════════════════════════════════════════════════════
USER QUESTION:
  {user_query}

════════════════════════════════════════════════════
Generate the PostgreSQL SQL query now:"""

    return prompt
