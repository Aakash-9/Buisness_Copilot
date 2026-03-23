"""
context_selector.py
Selects only the relevant YAML sections based on the user query.
Aligned with real database schema.
"""

import yaml
import os
import re
from core.filter_extractor import extract_filters
from core.intent_detector  import detect_intent, get_list_columns

YAML_DIR = os.path.join(os.path.dirname(__file__), '..', 'yaml')


def _load_yaml(filename: str) -> dict:
    path = os.path.join(YAML_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _detect_metrics(query: str, glossary: dict) -> list:
    """Match query keywords to metric aliases. Longer alias match wins (avoids false positives)."""
    query_lower = query.lower()
    matched = []
    for metric_key, metric_data in glossary.get('metrics', {}).items():
        aliases = metric_data.get('aliases', [])
        if any(alias in query_lower for alias in aliases):
            matched.append((metric_key, metric_data))
    return matched


def _detect_time_filter(query: str, time_cfg: dict) -> str:
    """
    Match query to a time filter SQL snippet.
    Sorts by longest keyword first to avoid 'this month' matching before 'last month'.
    """
    query_lower = query.lower()
    filters = time_cfg.get('time_filters', {})

    # Sort by longest keyword descending — most specific match wins
    sorted_filters = sorted(
        filters.items(),
        key=lambda x: max((len(kw) for kw in x[1].get('keywords', [])), default=0),
        reverse=True
    )

    for filter_key, filter_data in sorted_filters:
        keywords = filter_data.get('keywords', [])
        if any(kw in query_lower for kw in keywords):
            return filter_data['sql']

    return time_cfg.get('default_fallback', {}).get('sql',
           "o.order_date >= date_trunc('month', current_date)")


def _detect_time_column(query: str, time_cfg: dict) -> str:
    """
    Detect if a non-orders time column should be used.
    E.g. refund queries → rf.refund_date, shipment queries → sh.shipped_date
    """
    query_lower = query.lower()
    alt_columns = time_cfg.get('alternate_time_columns', {})

    column_keywords = {
        'shipments':           ['delivery performance', 'courier performance', 'shipped date',
                                'delivery date', 'on time delivery'],
        'refunds':             ['refund date', 'when refunded', 'refund this month'],
        'returns':             ['return date', 'when returned', 'returns this month',
                                'no of returns this month', 'how many returns',
                                'total returns this month', 'number of returns'],
        'payments':            ['payment date', 'when paid', 'payment failure',
                                'failed payment', 'payment this month'],
        'seller_settlements':  ['settlement date', 'when settled', 'settlement this month'],
        'inventory_movements': ['movement date', 'stock movement'],
    }

    for table, keywords in column_keywords.items():
        if any(kw in query_lower for kw in keywords):
            if table in alt_columns:
                return alt_columns[table]

    return time_cfg.get('default_time_column', 'o.order_date')


def _detect_tables(query: str, join_cfg: dict) -> tuple:
    """
    Detect which tables are needed based on query keywords.
    Aligned with real schema tables.
    """
    query_lower = query.lower()

    # Keywords aligned with real schema and common business questions
    table_keywords = {
        'sellers':              ['seller', 'vendor', 'seller rating', 'commission rate',
                                 'seller region', 'seller type', 'risk flag',
                                 'inactive seller', 'active seller', 'is_active'],
        'products':             ['product', 'category', 'sub_category', 'sub category',
                                 'brand', 'season', 'size', 'color', 'mrp',
                                 'selling price', 'returnable', 'non returnable',
                                 'is_returnable', 'top products', 'which product',
                                 'by season', 'season wise', 'seasonal'],
        'customers':            ['customer', 'buyer', 'user', 'loyalty', 'loyalty tier',
                                 'age group', 'city', 'state', 'gender', 'segment',
                                 'new customer', 'repeat customer', 'new customers',
                                 'new signups'],
        'shipments':            ['shipment', 'shipping', 'delivery', 'shipped',
                                 'courier', 'in transit', 'out for delivery',
                                 'promised delivery', 'actual delivery', 'late delivery',
                                 'bluedart', 'delhivery', 'shadowfax', 'ecom express', 'dtdc',
                                 'delivery success', 'delivery rate'],
        'warehouses':           ['warehouse', 'wh', 'stock location'],
        'returns':              ['return', 'returned', 'exchange', 'return reason',
                                 'return rate', 'return status', 'pickup', 'no of returns',
                                 'number of returns', 'how many returns', 'total returns'],
        'refunds':              ['refund', 'refunded', 'money back', 'refund method',
                                 'total refunds', 'refund amount', 'total refund amount'],
        'seller_settlements':   ['settlement', 'payout', 'seller payment', 'net payable',
                                 'commission amount', 'gross amount', 'on hold'],
        'inventory':            ['inventory', 'stock', 'available qty', 'available stock',
                                 'damaged stock', 'reserved', 'damaged', 'low stock',
                                 'out of stock', 'stock level', 'zero stock',
                                 'zero available', 'damaged goods', 'inbound stock'],
        'inventory_movements':  ['inventory movement', 'stock movement', 'inbound', 'outbound',
                                 'movement type', 'inbound stock movements'],
        'payments':             ['payment', 'paid', 'gateway', 'upi', 'cod', 'wallet',
                                 'net banking', 'credit card', 'payment method',
                                 'payment status', 'failed payment', 'payment failure',
                                 'payment failed', 'payment success', 'phonepay', 'razorpay',
                                 'paytm', 'stripe', 'payu', 'which gateway', 'payment count',
                                 'how many payments', 'payments completed', 'failed upi',
                                 'upi payments', 'payments above', 'payments below'],
    }

    needed_tables = set()
    for table, keywords in table_keywords.items():
        if any(kw in query_lower for kw in keywords):
            needed_tables.add(table)

    # Auto-add dependency tables based on schema rules
    # If refunds needed → must have returns
    if 'refunds' in needed_tables:
        needed_tables.add('returns')
    # If returns needed → must have order_items (join key is order_item_id)
    if 'returns' in needed_tables:
        needed_tables.add('order_items')
    # If seller_settlements needed → must have order_items
    if 'seller_settlements' in needed_tables:
        needed_tables.add('order_items')
    # If warehouses needed and shipments context → add shipments
    if 'warehouses' in needed_tables and 'inventory' not in needed_tables:
        needed_tables.add('shipments')
    # If inventory_movements needed → must have inventory
    if 'inventory_movements' in needed_tables:
        needed_tables.add('inventory')

    # Collect relevant join paths
    relevant_joins = {}
    core_paths = join_cfg.get('core_paths', {})
    for path_name, path_data in core_paths.items():
        if path_data.get('to') in needed_tables or path_data.get('from') in needed_tables:
            relevant_joins[path_name] = path_data

    # Collect enforcement rules for needed tables
    relevant_rules = []
    for rule in join_cfg.get('enforcement_rules', []):
        if rule.get('pattern') in needed_tables:
            relevant_rules.append(rule)

    # Always include column corrections in context — critical for LLM accuracy
    column_corrections = join_cfg.get('column_corrections', [])

    return relevant_joins, relevant_rules, needed_tables, column_corrections


def _detect_segmentation(query: str) -> list:
    """
    Detect GROUP BY dimensions from the query.
    Maps to real schema columns.
    """
    query_lower = query.lower()
    segments = []

    segmentation_map = {
        'category':       ['by category', 'per category', 'category wise', 'category-wise',
                           'each category', 'product category'],
        'sub_category':   ['by sub category', 'sub category wise', 'subcategory', 'sub-category'],
        'brand':          ['by brand', 'per brand', 'brand wise', 'brands by', 'top brands',
                           'each brand'],
        'seller':         ['by seller', 'per seller', 'seller wise', 'seller-wise',
                           'each seller', 'top sellers', 'which seller'],
        'customer':       ['by customer', 'per customer'],
        'city':           ['by city', 'per city', 'city wise', 'which city', 'each city',
                           'highest city', 'top city', 'cities'],
        'state':          ['by state', 'per state', 'state wise', 'which state', 'each state'],
        'loyalty_tier':   ['loyalty tier', 'by loyalty', 'loyalty segment', 'loyalty level'],
        'age_group':      ['age group', 'by age', 'age wise'],
        'gender':         ['by gender', 'gender wise', 'male vs female'],
        'payment_method': ['by payment method', 'per payment method', 'payment method wise',
                           'payment method breakdown', 'each payment method',
                           'by payment', 'by payment mode', 'payment mode wise',
                           'upi vs cod', 'cod vs prepaid', 'which payment method'],
        'order_channel':  ['by channel', 'channel wise', 'order channel', 'app vs website',
                           'mobile vs web', 'channel breakdown'],
        'courier_partner':['by courier', 'courier wise', 'courier partner', 'which courier',
                           'each courier', 'courier breakdown', 'courier performance',
                           'courier comparison', 'compare couriers'],
        'seller_region':  ['by region', 'region wise', 'seller region', 'which region'],
        'return_reason':  ['return reason', 'why returned', 'reason for return', 'return reasons'],
        'warehouse':      ['by warehouse', 'warehouse wise', 'which warehouse', 'each warehouse'],
        'month':          ['by month', 'monthly trend', 'month over month', 'month wise',
                           'monthly breakdown', 'trend this year', 'monthly revenue',
                           'monthly orders', 'each month', 'per month'],
        'week':           ['by week', 'weekly trend', 'week over week', 'weekly breakdown',
                           'weekly order', 'weekly revenue', 'weekly count', 'per week',
                           'each week', 'week wise'],
        'day':            ['by day', 'daily trend', 'day over day', 'daily breakdown',
                           'daily order', 'daily revenue', 'daily count', 'per day',
                           'each day', 'day wise', 'daily cancellation'],
        'order_status':   ['by status', 'status wise', 'each status', 'order status breakdown'],
        'seller_type':    ['seller type', 'by seller type', 'individual vs brand'],
        'return_type':    ['return type', 'return vs exchange', 'exchange vs return'],
        'risk_flag':      ['risk flag', 'high risk', 'risky sellers'],
        'is_active':      ['active sellers', 'inactive sellers', 'active vs inactive'],
        'product':        ['by product', 'per product', 'product wise', 'which products',
                           'each product', 'top products', 'product breakdown'],
        'warehouse':      ['by warehouse', 'warehouse wise', 'which warehouse',
                           'each warehouse', 'per warehouse', 'warehouse breakdown',
                           'damaged inventory by', 'stock by warehouse', 'inventory by'],
    }

    for segment, keywords in segmentation_map.items():
        if any(kw in query_lower for kw in keywords):
            segments.append(segment)

    return segments


def select_context(user_query: str) -> dict:
    """
    Main function: returns structured context dict for prompt builder.
    """
    glossary = _load_yaml('metric_glossary.yaml')
    join_cfg = _load_yaml('join_path_specification.yaml')
    sql_std  = _load_yaml('sql_generation_standards.yaml')
    time_cfg = _load_yaml('time_filter_governance.yaml')

    matched_metrics  = _detect_metrics(user_query, glossary)
    time_filter_sql  = _detect_time_filter(user_query, time_cfg)
    time_column      = _detect_time_column(user_query, time_cfg)
    segmentation     = _detect_segmentation(user_query)
    filters          = extract_filters(user_query)
    intent           = detect_intent(user_query)

    relevant_joins, enf_rules, needed_tables, col_corrections = _detect_tables(
        user_query, join_cfg
    )

    # FIX 1: Remove warehouses+shipments if query is purely about orders/payments
    # (auto-dependency was too aggressive)
    order_only_tables = {'payments', 'customers', 'products', 'sellers',
                         'returns', 'refunds', 'seller_settlements', 'inventory',
                         'inventory_movements'}
    delivery_keywords = ['delivery', 'shipment', 'shipped', 'courier', 'warehouse',
                         'in transit', 'out for delivery', 'bluedart', 'delhivery']
    query_lower = user_query.lower()
    has_delivery_intent = any(kw in query_lower for kw in delivery_keywords)
    if not has_delivery_intent and needed_tables <= order_only_tables | {'warehouses', 'shipments'}:
        needed_tables.discard('warehouses')
        needed_tables.discard('shipments')
        relevant_joins = {k: v for k, v in relevant_joins.items()
                         if v.get('to') not in ('warehouses', 'shipments')
                         and v.get('from') not in ('warehouses', 'shipments')}

    # AUTO-ADD customers when age filter is detected
    if filters.get('needs_customers'):
        needed_tables.add('customers')
        core_paths = join_cfg.get('core_paths', {})
        if 'customer_to_order' in core_paths:
            relevant_joins['customer_to_order'] = core_paths['customer_to_order']

    # FIX 2: For LIST intent — suppress aggregate metrics and segmentation
    # User wants rows, not GROUP BY summaries
    if intent == 'list':
        matched_metrics = []   # no metric needed for listing rows
        segmentation    = []   # no GROUP BY for listing rows
        list_cols       = get_list_columns(list(needed_tables), filters)
    else:
        list_cols = []

    # FIX 3: payment_mode filter already handles "online/prepaid"
    # Remove payments table and payment_method segmentation when:
    # - payment_mode filter already covers it (o.payment_mode = 'Prepaid')
    # - user is NOT asking for a breakdown BY payment method
    filters_sql = filters.get('all_sql_filters', [])
    has_payment_mode_filter   = any('payment_mode' in f for f in filters_sql)
    has_payment_method_filter = any('pay.payment_method' in f for f in filters_sql)

    # "by payment method" or "payment method breakdown" = they want grouping
    # "payment method was online" = they're using it as a filter — NOT a grouping
    wants_payment_breakdown = any(kw in query_lower for kw in [
        'by payment method', 'payment method breakdown', 'which payment method',
        'payment method wise', 'per payment method', 'by gateway',
        'upi vs cod', 'cod vs prepaid', 'each payment method',
        'by payment mode', 'payment mode wise', 'by payment',
    ])

    # Only keep payments table / segment if they explicitly want a payment breakdown
    # OR if they're filtering by specific payment_method values (UPI, credit card etc.)
    needs_payment_method = any(kw in query_lower for kw in [
        'upi', 'credit card', 'wallet', 'net banking', 'gateway',
        'payment status', 'paid amount', 'failed payment', 'payment failure',
    ])

    if has_payment_mode_filter and not has_payment_method_filter \
       and not wants_payment_breakdown and not needs_payment_method:
        needed_tables.discard('payments')
        relevant_joins = {k: v for k, v in relevant_joins.items()
                         if v.get('to') != 'payments' and v.get('from') != 'payments'}
        segmentation = [s for s in segmentation if s != 'payment_method']

    return {
        'intent':             intent,
        'metrics':            matched_metrics,
        'list_columns':       list_cols,
        'time_filter':        time_filter_sql,
        'time_column':        time_column,
        'join_paths':         relevant_joins,
        'join_rules':         enf_rules,
        'column_corrections': col_corrections,
        'sql_standards':      sql_std.get('rules', {}),
        'status_values':      sql_std.get('rules', {}).get('status_values', {}),
        'table_aliases':      join_cfg.get('table_aliases', {}),
        'needed_tables':      list(needed_tables),
        'segmentation':       segmentation,
        'filters':            filters,
        'output_format':      sql_std.get('output_format', []),
    }
