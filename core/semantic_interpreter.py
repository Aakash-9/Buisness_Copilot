"""
semantic_interpreter.py

Uses Groq LLaMA as a SEMANTIC UNDERSTANDING layer — not for SQL generation,
but purely to translate ANY natural language query into a structured
business intent that context_selector.py can work with.

This is a TWO-CALL architecture:
  Call 1 (this file) → understand what user wants → structured JSON
  Call 2 (sql_generator) → convert structured context → SQL

The first call is cheap (small prompt, small output).
The second call is the full SQL generation with all business rules injected.
"""

import json
import re
from groq import Groq


# ─────────────────────────────────────────────────────────────
# KNOWN METRICS AND TABLES — fed to the interpreter
# so it can map intent to exact system terms
# ─────────────────────────────────────────────────────────────

AVAILABLE_METRICS = [
    'gmv', 'realized_revenue', 'net_revenue', 'discount_impact',
    'avg_order_value', 'refund_amount', 'seller_settlement',
    'commission_earned', 'loss', 'total_orders', 'cancelled_orders',
    'return_rate', 'total_returns', 'exchange_count', 'delivery_performance',
    'inventory_health', 'damaged_stock', 'zero_stock', 'shipment_count',
    'payment_count', 'payment_failures', 'payment_success',
    'cancellation_rate', 'new_customers', 'seller_performance',
    'season_sales', 'inactive_sellers', 'high_risk_sellers',
    'non_returnable_products',
]

AVAILABLE_TABLES = [
    'orders', 'order_items', 'products', 'sellers', 'customers',
    'payments', 'shipments', 'warehouses', 'returns', 'refunds',
    'seller_settlements', 'inventory', 'inventory_movements',
]

AVAILABLE_SEGMENTS = [
    'category', 'sub_category', 'brand', 'seller', 'city', 'state',
    'loyalty_tier', 'age_group', 'gender', 'payment_method',
    'order_channel', 'courier_partner', 'seller_region', 'return_reason',
    'warehouse', 'month', 'week', 'day', 'order_status', 'seller_type',
    'risk_flag', 'season',
]

TIME_FILTERS = [
    'today', 'yesterday', 'this_week', 'last_7_days', 'this_month',
    'last_month', 'last_30_days', 'last_90_days', 'this_quarter',
    'last_quarter', 'this_year', 'last_year', 'all_time',
]

INTENT_TYPES = ['list', 'aggregate']


INTERPRETER_PROMPT = f"""You are a business intelligence query interpreter for an e-commerce analytics platform.

Your job: Convert ANY natural language question — including vague, informal, metaphorical, 
Hindi/Hinglish, or typo-ridden queries — into a structured JSON that identifies the business intent.

AVAILABLE METRICS: {AVAILABLE_METRICS}
AVAILABLE TABLES:  {AVAILABLE_TABLES}
AVAILABLE SEGMENTS (GROUP BY dimensions): {AVAILABLE_SEGMENTS}
TIME FILTERS: {TIME_FILTERS}
INTENT TYPES: list (show individual rows), aggregate (summary/count/sum)

BUSINESS CONTEXT:
- This is an Indian e-commerce platform (like Myntra/Flipkart/Amazon India)
- "loss" = cancelled + returned orders losing money
- "returns" = customers sending products back
- "settlement" = money paid to sellers
- COD = Cash on Delivery, Prepaid = online payment
- Couriers: BlueDart, Delhivery, Shadowfax, Ecom Express, DTDC

RESPOND ONLY WITH VALID JSON. No explanation. No markdown. No extra text.
JSON format:
{{
  "metrics": ["metric1", "metric2"],
  "tables": ["table1"],
  "segments": ["segment1"],
  "time_filter": "this_month",
  "intent": "aggregate",
  "amount_filter": null,
  "categorical_filters": {{}},
  "top_n": null,
  "confidence": "high/medium/low",
  "interpreted_as": "one sentence what you understood"
}}

Rules:
- metrics: pick 1-3 most relevant from the list, or [] if none fit
- tables: only add tables NOT already covered by the metrics
- segments: GROUP BY dimensions detected, or []
- time_filter: pick from the list, default "this_month" if not specified
- intent: "list" if user wants rows, "aggregate" if they want summary
- amount_filter: {{"column": "o.final_payable", "operator": "<", "value": 2000}} or null
- categorical_filters: {{"o.payment_mode": "Prepaid"}} or {{}}
- top_n: 5 if "top 5", null otherwise
- confidence: how sure you are about the interpretation
- interpreted_as: plain English summary of what you understood
"""


def interpret(user_query: str, api_key: str) -> dict:
    """
    Uses Groq LLaMA to semantically interpret the user query.
    Returns a structured dict that context_selector can use directly.
    
    Args:
        user_query: raw natural language from user
        api_key: Groq API key
    Returns:
        Structured interpretation dict
    """
    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": INTERPRETER_PROMPT},
            {"role": "user",   "content": f"Interpret this query: {user_query}"}
        ],
        temperature=0.0,
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    raw = re.sub(r'```json|```', '', raw).strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback — extract JSON from response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            result = {
                'metrics': [], 'tables': [], 'segments': [],
                'time_filter': 'this_month', 'intent': 'aggregate',
                'amount_filter': None, 'categorical_filters': {},
                'top_n': None, 'confidence': 'low',
                'interpreted_as': 'Could not interpret query'
            }

    return result


def merge_with_context(interpretation: dict, keyword_context: dict) -> dict:
    """
    Merges semantic interpretation with keyword-based context.
    Semantic wins on metrics/segments (better NLU).
    Keyword wins on exact filters (more precise pattern matching).
    """
    from core.context_selector import _load_yaml

    glossary = _load_yaml('metric_glossary.yaml')
    all_metrics = glossary.get('metrics', {})

    # Build metric objects from interpreted metric names
    semantic_metrics = []
    for m_name in interpretation.get('metrics', []):
        if m_name in all_metrics:
            semantic_metrics.append((m_name, all_metrics[m_name]))

    # Merge: use semantic metrics if keyword found none
    final_metrics = keyword_context['metrics'] if keyword_context['metrics'] else semantic_metrics

    # Merge segments
    sem_segs  = interpretation.get('segments', [])
    kw_segs   = keyword_context.get('segmentation', [])
    final_segs = list(dict.fromkeys(kw_segs + sem_segs))  # dedup, preserve order

    # Merge tables
    sem_tables = set(interpretation.get('tables', []))
    kw_tables  = set(keyword_context.get('needed_tables', []))
    final_tables = list(kw_tables | sem_tables)

    # Time filter — keyword is more precise (has exact SQL), keep it
    # but use semantic if keyword gave default
    time_filter = keyword_context['time_filter']

    # Intent — semantic understanding is better here
    final_intent = interpretation.get('intent', keyword_context.get('intent', 'aggregate'))

    # Amount filter from semantic
    amt = interpretation.get('amount_filter')
    extra_filters = []
    if amt:
        col = amt.get('column', 'o.final_payable')
        op  = amt.get('operator', '<')
        val = amt.get('value', '')
        extra_filters.append(f"{col} {op} {val}")

    # Categorical filters from semantic
    for col, val in interpretation.get('categorical_filters', {}).items():
        extra_filters.append(f"{col} = '{val}'")

    # Merge with existing keyword filters (keyword filters are more precise)
    existing_filters = keyword_context['filters']['all_sql_filters']
    all_filter_sqls  = list(dict.fromkeys(existing_filters + extra_filters))

    merged = dict(keyword_context)
    merged['metrics']     = final_metrics
    merged['segmentation']= final_segs
    merged['needed_tables']= final_tables
    merged['intent']      = final_intent
    merged['filters']     = {
        **keyword_context['filters'],
        'all_sql_filters': all_filter_sqls,
        'top_n': keyword_context['filters'].get('top_n') or
                 ({'sql': f"LIMIT {interpretation['top_n']}"} if interpretation.get('top_n') else {})
    }
    merged['semantic_interpretation'] = interpretation.get('interpreted_as', '')
    merged['semantic_confidence']     = interpretation.get('confidence', 'low')

    return merged
