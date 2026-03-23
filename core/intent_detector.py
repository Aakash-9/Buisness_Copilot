"""
intent_detector.py
Detects the INTENT of the user query — LIST rows vs AGGREGATE/summarize.
This is the missing piece that was causing wrong SQL generation.

LIST   → SELECT individual rows (order_id, date, amount...)  — no GROUP BY
AGGREGATE → COUNT, SUM, AVG, GROUP BY — summary/analytics queries
FILTER → LIST with specific WHERE conditions (subset of rows)
"""

LIST_KEYWORDS = [
    'show me', 'tell me', 'list', 'give me', 'display',
    'find', 'get', 'fetch', 'which orders', 'what orders',
    'orders that', 'orders which', 'orders where', 'orders with',
    'orders having', 'all orders', 'orders whose',
    'show orders', 'tell orders', 'find orders',
]

AGGREGATE_KEYWORDS = [
    'total', 'count', 'how many', 'sum', 'average', 'avg',
    'top', 'bottom', 'highest', 'lowest', 'most', 'least',
    'best', 'worst', 'maximum', 'minimum', 'breakdown',
    'summary', 'report', 'analysis', 'trend', 'compare',
    'by category', 'by seller', 'by city', 'by state',
    'by month', 'by week', 'by channel', 'by region',
    'rate', 'percentage', '%', 'ratio', 'performance',
    'revenue', 'sales', 'gmv', 'loss', 'profit',
    'why are we', 'what is our', 'how much', 'how is',
]


def detect_intent(query: str) -> str:
    """
    Returns: 'list', 'aggregate', or 'filter'
    
    'list'      → User wants individual rows — SELECT specific columns, no GROUP BY
    'aggregate' → User wants summary/analytics — COUNT/SUM/AVG with GROUP BY
    'filter'    → User wants filtered rows (subset) — similar to list but with conditions
    """
    query_lower = query.lower()

    agg_score  = sum(1 for kw in AGGREGATE_KEYWORDS if kw in query_lower)
    list_score = sum(1 for kw in LIST_KEYWORDS      if kw in query_lower)

    # Strong aggregate signals override list keywords
    if agg_score > list_score:
        return 'aggregate'

    # Explicit list/show/tell keywords → list intent
    if list_score > 0:
        return 'list'

    # Has filter conditions but no grouping → filter/list
    return 'aggregate'  # default to aggregate for analytics system


def get_list_columns(needed_tables: list, filters: dict) -> list:
    """
    For LIST queries, return sensible default SELECT columns.
    Based on which tables are involved.
    """
    cols = ['o.order_id', 'o.order_date', 'o.order_status',
            'o.final_payable', 'o.payment_mode', 'o.order_channel']

    if 'customers' in needed_tables:
        cols += ['c.city', 'c.state']

    if 'payments' in needed_tables:
        cols += ['pay.payment_method', 'pay.payment_status']

    if 'shipments' in needed_tables:
        cols += ['sh.delivery_status', 'sh.courier_partner']

    if 'products' in needed_tables:
        cols += ['p.brand', 'p.category', 'p.sub_category']

    if 'sellers' in needed_tables:
        cols += ['s.seller_name', 's.seller_region']

    if 'returns' in needed_tables:
        cols += ['r.return_reason', 'r.return_status', 'r.return_type']

    return cols
