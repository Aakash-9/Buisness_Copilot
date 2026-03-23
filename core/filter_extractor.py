"""
filter_extractor.py
Extracts WHERE-clause filters from natural language queries.
Handles: amount ranges, payment methods, order status, seller filters,
         product filters, customer filters — all mapped to real schema columns.
"""

import re


# ─────────────────────────────────────────────
# AMOUNT / NUMERIC FILTER PATTERNS
# ─────────────────────────────────────────────

AMOUNT_PATTERNS = [
    # Handle k shorthand: 2k=2000, 5k=5000, 10k=10000
    (r'\b(below|under|less than|lesser than|<)\s*₹?\s*(\d+\.?\d*)k\b', 'lt_k'),
    (r'\b(above|over|more than|greater than|exceeds|>)\s*₹?\s*(\d+\.?\d*)k\b', 'gt_k'),
    (r'\bbetween\s*₹?\s*(\d+\.?\d*)k\s*and\s*₹?\s*(\d+\.?\d*)k\b', 'between_k'),
    # Regular numbers
    (r'\b(below|under|less than|lesser than|<)\s*₹?\s*(\d+)', 'lt'),
    (r'\b(above|over|more than|greater than|exceeds|>)\s*₹?\s*(\d+)', 'gt'),
    (r'\bbetween\s*₹?\s*(\d+)\s*and\s*₹?\s*(\d+)', 'between'),
    (r'\b(exactly|equal to|=)\s*₹?\s*(\d+)', 'eq'),
    (r'₹?\s*(\d+)\s*to\s*₹?\s*(\d+)', 'between'),
]

# Which column to apply amount filter on
AMOUNT_COLUMN_KEYWORDS = {
    'o.final_payable':   ['final payable', 'final amount', 'order amount', 'order value',
                          'order total', 'rupees', 'rs', '₹', 'amount', 'total amount',
                          'below', 'above', 'under', 'over', 'less than', 'more than',
                          'between', 'greater than'],
    'oi.item_price':     ['item price', 'product price', 'item amount', 'item value'],
    'o.discount_amount': ['discount amount', 'discount below', 'discount above'],
    'pay.paid_amount':   ['paid amount', 'payment amount'],
    'p.mrp':             ['mrp', 'maximum retail price'],
    'p.selling_price':   ['selling price', 'product selling price'],
}


# ─────────────────────────────────────────────
# CATEGORICAL FILTER PATTERNS
# ─────────────────────────────────────────────

CATEGORICAL_FILTERS = {

    # Payment method — maps to orders.payment_mode (COD/Prepaid) or payments.payment_method
    'payment_mode': {
        'column': 'o.payment_mode',
        'patterns': {
            'COD':      ['cod', 'cash on delivery', 'cash'],
            'Prepaid':  ['prepaid', 'online', 'digital', 'online payment',
                         'paid online', 'non cod', 'not cod'],
        }
    },

    'payment_method': {
        'column': 'pay.payment_method',
        'patterns': {
            'UPI':          ['upi', 'gpay', 'phonepe', 'paytm upi'],
            'Credit Card':  ['credit card', 'credit'],
            'Wallet':       ['wallet', 'paytm wallet'],
            'Net Banking':  ['net banking', 'netbanking', 'neft'],
            'COD':          ['cod payment', 'cash payment'],
        }
    },

    # Order status
    'order_status': {
        'column': 'o.order_status',
        'patterns': {
            'Delivered':  ['delivered', 'completed order', 'successful order'],
            'Cancelled':  ['cancelled', 'canceled'],
            'Shipped':    ['shipped', 'in transit order'],
            'Returned':   ['returned order'],
        }
    },

    # Order channel
    'order_channel': {
        'column': 'o.order_channel',
        'patterns': {
            'App':          ['app', 'mobile app', 'application'],
            'Website':      ['website', 'web', 'desktop'],
            'Mobile Web':   ['mobile web', 'mobile website'],
        }
    },

    # Delivery status
    'delivery_status': {
        'column': 'sh.delivery_status',
        'patterns': {
            'Delivered':        ['delivered shipment', 'delivery completed'],
            'In Transit':       ['in transit', 'on the way', 'not delivered yet'],
            'Out for Delivery': ['out for delivery'],
        }
    },

    # Return type
    'return_type': {
        'column': 'r.return_type',
        'patterns': {
            'Return':   ['return only', 'only returns', 'return type'],
            'Exchange': ['exchange', 'exchange only'],
        }
    },

    # Return status
    'return_status': {
        'column': 'r.return_status',
        'patterns': {
            'Completed':  ['completed return', 'return completed'],
            'Rejected':   ['rejected return', 'return rejected'],
            'Picked Up':  ['picked up', 'pickup done'],
            'Initiated':  ['initiated return', 'return initiated'],
        }
    },

    # Seller type
    'seller_type': {
        'column': 's.seller_type',
        'patterns': {
            'Individual':        ['individual seller', 'individual'],
            'Authorized Reseller': ['authorized reseller', 'reseller'],
            'Brand Official':    ['brand official', 'brand seller', 'official brand'],
        }
    },

    # Risk flag
    'risk_flag': {
        'column': 's.risk_flag',
        'patterns': {
            'High':   ['high risk', 'risky'],
            'Medium': ['medium risk'],
            'Low':    ['low risk'],
        }
    },

    # Product returnable
    'is_returnable': {
        'column': 'p.is_returnable',
        'patterns': {
            'FALSE': ['non returnable', 'non-returnable', 'not returnable',
                      'cannot be returned', 'no return', 'not eligible for return'],
            'TRUE':  ['returnable product', 'can be returned', 'return eligible',
                      'eligible for return'],
        }
    },

    # Seller active
    'is_active': {
        'column': 's.is_active',
        'patterns': {
            'FALSE': ['inactive seller', 'inactive sellers', 'not active', 'show inactive',
                      'sellers inactive'],
            'TRUE':  ['active sellers only', 'only active sellers', 'active seller list'],
        }
    },

    # Payment status
    'payment_status': {
        'column': 'pay.payment_status',
        'patterns': {
            'Completed': ['payment success', 'successful payment', 'payment completed'],
            'Failed':    ['payment failed', 'failed payment', 'payment failure',
                         'unsuccessful payment'],
        }
    },

    # Refund status
    'refund_status': {
        'column': 'rf.refund_status',
        'patterns': {
            'Completed':  ['refund completed', 'refund done', 'refund processed'],
            'Failed':     ['refund failed', 'failed refund'],
            'Processing': ['refund processing', 'pending refund'],
        }
    },

    # Settlement status
    'settlement_status': {
        'column': 'ss.settlement_status',
        'patterns': {
            'Paid':      ['settlement paid', 'paid settlement'],
            'Pending':   ['pending settlement', 'settlement pending', 'unsettled'],
            'On Hold':   ['on hold', 'settlement on hold', 'held settlement'],
            'Processed': ['settlement processed'],
        }
    },

    # Courier
    'courier_partner': {
        'column': 'sh.courier_partner',
        'patterns': {
            'BlueDart':    ['bluedart', 'blue dart'],
            'Delhivery':   ['delhivery'],
            'Shadowfax':   ['shadowfax'],
            'Ecom Express':['ecom express', 'ecomexpress'],
            'DTDC':        ['dtdc'],
        }
    },

    # Seller region
    'seller_region': {
        'column': 's.seller_region',
        'patterns': {
            'North':    ['north region', 'north sellers'],
            'South':    ['south region', 'south sellers'],
            'East':     ['east region', 'east sellers'],
            'West':     ['west region', 'west sellers'],
            'Pan-India':['pan india', 'pan-india', 'all india'],
        }
    },
}


# ─────────────────────────────────────────────
# TOP N PATTERN
# ─────────────────────────────────────────────

def _extract_top_n(query: str) -> dict:
    """Extract LIMIT N from 'top 5', 'top 10', 'bottom 5' etc."""
    query_lower = query.lower()

    top_match = re.search(r'\btop\s+(\d+)\b', query_lower)
    bottom_match = re.search(r'\bbottom\s+(\d+)\b', query_lower)
    first_match = re.search(r'\bfirst\s+(\d+)\b', query_lower)

    if top_match:
        return {'type': 'top', 'n': int(top_match.group(1)), 'sql': f'LIMIT {top_match.group(1)}'}
    if bottom_match:
        return {'type': 'bottom', 'n': int(bottom_match.group(1)),
                'order': 'ASC', 'sql': f'LIMIT {bottom_match.group(1)}'}
    if first_match:
        return {'type': 'first', 'n': int(first_match.group(1)), 'sql': f'LIMIT {first_match.group(1)}'}

    return {}


# ─────────────────────────────────────────────
# AMOUNT FILTER EXTRACTOR
# ─────────────────────────────────────────────

def _extract_amount_filters(query: str) -> list:
    """Extract numeric/amount filters and map to correct column."""
    query_lower = query.lower()
    filters = []

    # Detect which amount column applies
    amount_col = 'o.final_payable'  # default
    for col, keywords in AMOUNT_COLUMN_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            amount_col = col
            break

    for pattern, op in AMOUNT_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            # Handle k shorthand — convert 2k→2000, 5k→5000
            if op == 'between_k':
                lo = int(float(match.group(1)) * 1000)
                hi = int(float(match.group(2)) * 1000)
                filters.append({
                    'column': amount_col, 'operator': 'BETWEEN',
                    'value': f'{lo} AND {hi}',
                    'sql': f'{amount_col} BETWEEN {lo} AND {hi}'
                })
            elif op == 'lt_k':
                val = int(float(match.group(2)) * 1000)
                filters.append({
                    'column': amount_col, 'operator': '<',
                    'value': str(val), 'sql': f'{amount_col} < {val}'
                })
            elif op == 'gt_k':
                val = int(float(match.group(2)) * 1000)
                filters.append({
                    'column': amount_col, 'operator': '>',
                    'value': str(val), 'sql': f'{amount_col} > {val}'
                })
            elif op == 'between':
                lo, hi = match.group(1), match.group(2)
                filters.append({
                    'column': amount_col, 'operator': 'BETWEEN',
                    'value': f'{lo} AND {hi}',
                    'sql': f'{amount_col} BETWEEN {lo} AND {hi}'
                })
            elif op == 'lt':
                val = match.group(2)
                filters.append({
                    'column': amount_col, 'operator': '<',
                    'value': val, 'sql': f'{amount_col} < {val}'
                })
            elif op == 'gt':
                val = match.group(2)
                filters.append({
                    'column': amount_col, 'operator': '>',
                    'value': val, 'sql': f'{amount_col} > {val}'
                })
            elif op == 'eq':
                val = match.group(2)
                filters.append({
                    'column': amount_col, 'operator': '=',
                    'value': val, 'sql': f'{amount_col} = {val}'
                })
            break  # one amount filter per query

    return filters


# ─────────────────────────────────────────────
# CATEGORICAL FILTER EXTRACTOR
# ─────────────────────────────────────────────

def _extract_categorical_filters(query: str) -> list:
    """Extract categorical WHERE conditions from query."""
    query_lower = query.lower()
    filters = []

    for filter_name, config in CATEGORICAL_FILTERS.items():
        col = config['column']
        for value, keywords in config['patterns'].items():
            if any(kw in query_lower for kw in keywords):
                if value in ('TRUE', 'FALSE'):
                    filters.append({
                        'column': col,
                        'operator': '=',
                        'value': value,
                        'sql': f'{col} = {value}'
                    })
                else:
                    filters.append({
                        'column': col,
                        'operator': '=',
                        'value': f"'{value}'",
                        'sql': f"{col} = '{value}'"
                    })
                break  # one match per filter category

    return filters


# ─────────────────────────────────────────────
# MAIN EXTRACTOR
# ─────────────────────────────────────────────

def extract_filters(query: str) -> dict:
    """
    Main entry point. Returns all detected filters for the query.
    Age filters take priority — if age filter detected with a number,
    suppress amount filter using that same number to avoid double-detection.
    """
    amount_filters      = _extract_amount_filters(query)
    categorical_filters = _extract_categorical_filters(query)
    age_filters         = _extract_age_filter(query)
    top_n               = _extract_top_n(query)

    # Suppress amount filters whose value looks like an age (< 120)
    # when an age filter was also detected for the same number
    if age_filters:
        age_values = set()
        for af in age_filters:
            # Extract numeric value from age filter sql
            import re as _re
            nums = _re_findall(r'\d+', af['sql'])
            age_values.update(int(n) for n in nums if int(n) < 120)

        # Remove amount filters that match those values
        amount_filters = [
            af for af in amount_filters
            if not any(str(v) == str(af.get('value', '')) for v in age_values)
        ]

    all_sql = [f['sql'] for f in amount_filters + categorical_filters + age_filters]

    return {
        'amount_filters':      amount_filters,
        'categorical_filters': categorical_filters,
        'age_filters':         age_filters,
        'top_n':               top_n,
        'all_sql_filters':     all_sql,
        'needs_customers':     len(age_filters) > 0,
    }


def _re_findall(pattern, string):
    import re as _re
    return _re.findall(pattern, string)


# ─────────────────────────────────────────────
# AGE GROUP FILTER — special handler
# age_group is text ranges (18-24, 25-34, etc.)
# "below 30" = 18-24, 25-34
# "above 30" = 25-34, 35-44, 45-54, 55+
# ─────────────────────────────────────────────

AGE_GROUPS = ['18-24', '25-34', '35-44', '45-54', '55+']

AGE_PATTERNS = [
    (r'\bage(?:d)?\s*(?:is\s*)?(?:below|under|less than|<)\s*(\d+)', 'lt'),
    (r'\bage(?:d)?\s*(?:is\s*)?(?:above|over|more than|greater than|>)\s*(\d+)', 'gt'),
    (r'\bage(?:d)?\s*(?:is\s*)?between\s*(\d+)\s*and\s*(\d+)', 'between'),
    (r'\baged?\s+between\s*(\d+)\s*and\s*(\d+)', 'between'),
    (r'\bpeople\s+aged?\s*(?:below|under|less than)\s*(\d+)', 'lt'),
    (r'\bpeople\s+aged?\s*(?:above|over|more than)\s*(\d+)', 'gt'),
    (r'\bbuyers?\s+(?:under|below)\s*(\d+)', 'lt'),
    (r'\bbuyers?\s+(?:over|above)\s*(\d+)', 'gt'),
    (r'\bcustomers?\s+(?:under|below|less than)\s*(\d+)', 'lt'),
    (r'\bcustomers?\s+(?:over|above|more than)\s*(\d+)', 'gt'),
    (r'\bcustomers?\s+aged?\s*(?:below|under)\s*(\d+)', 'lt'),
    (r'\bcustomers?\s+aged?\s*(?:above|over)\s*(\d+)', 'gt'),
    (r'\bunder\s*(\d+)\s*years?\s*(?:old|age)', 'lt'),
    (r'\bover\s*(\d+)\s*years?\s*(?:old|age)', 'gt'),
    (r'\bbelow\s*(\d+)\s*years?\s*(?:old|age)', 'lt'),
    (r'\babove\s*(\d+)\s*years?\s*(?:old|age)', 'gt'),
    # "young customers" = below 25
    (r'\byoung\s+customers?', 'young'),
    (r'\byouth\s+customers?', 'young'),
    # Direct age group mention: "age group 18-24"
    (r'\bage\s+group\s+(18-24|25-34|35-44|45-54|55\+)', 'exact'),
    (r'\bage\s+bracket\s+(18-24|25-34|35-44|45-54|55\+)', 'exact'),
    # Hindi age patterns
    (r'\b(\d+)\s*se\s*kam\s*(?:umar|age|aayu)', 'lt'),
    (r'\b(\d+)\s*se\s*zyada\s*(?:umar|age|aayu)', 'gt'),
]

AGE_GROUP_MAP = {
    # upper bound → which groups are BELOW it
    24: ['18-24'],
    25: ['18-24'],          # below 25 = only 18-24
    29: ['18-24'],
    30: ['18-24', '25-34'], # below 30 = 18-24 and 25-34
    34: ['18-24', '25-34'],
    35: ['18-24', '25-34'],
    44: ['18-24', '25-34', '35-44'],
    45: ['18-24', '25-34', '35-44'],
    54: ['18-24', '25-34', '35-44', '45-54'],
    55: ['18-24', '25-34', '35-44', '45-54'],
    100: ['18-24', '25-34', '35-44', '45-54', '55+'],
}

AGE_GROUP_MAP_ABOVE = {
    # lower bound → which groups are above it
    18: ['18-24', '25-34', '35-44', '45-54', '55+'],
    24: ['25-34', '35-44', '45-54', '55+'],
    25: ['25-34', '35-44', '45-54', '55+'],
    30: ['25-34', '35-44', '45-54', '55+'],
    34: ['35-44', '45-54', '55+'],
    35: ['35-44', '45-54', '55+'],
    44: ['45-54', '55+'],
    45: ['45-54', '55+'],
    54: ['55+'],
    55: ['55+'],
}


def _extract_age_filter(query: str) -> list:
    """
    Extract age filter and convert to age_group IN (...) SQL.
    customers.age_group is text (18-24, 25-34, etc.) not numeric.
    """
    query_lower = query.lower()
    filters = []

    for pattern, op in AGE_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            if op == 'young':
                # "young customers" = 18-24 only
                filters.append({
                    'column': 'c.age_group', 'operator': 'IN',
                    'value': "('18-24')", 'sql': "c.age_group IN ('18-24')"
                })

            elif op == 'exact':
                group = match.group(1)
                filters.append({
                    'column': 'c.age_group', 'operator': '=',
                    'value': f"'{group}'", 'sql': f"c.age_group = '{group}'"
                })

            else:
                val = int(match.group(1))

                if op == 'lt':
                    groups = None
                    for boundary in sorted(AGE_GROUP_MAP.keys()):
                        if val <= boundary:
                            groups = AGE_GROUP_MAP[boundary]
                            break
                    if not groups:
                        groups = AGE_GROUPS
                    quoted = ', '.join(f"'{g}'" for g in groups)
                    filters.append({
                        'column': 'c.age_group', 'operator': 'IN',
                        'value': f'({quoted})', 'sql': f"c.age_group IN ({quoted})"
                    })

                elif op == 'gt':
                    groups = None
                    for boundary in sorted(AGE_GROUP_MAP_ABOVE.keys()):
                        if val <= boundary:
                            groups = AGE_GROUP_MAP_ABOVE[boundary]
                            break
                    if not groups:
                        groups = ['55+']
                    quoted = ', '.join(f"'{g}'" for g in groups)
                    filters.append({
                        'column': 'c.age_group', 'operator': 'IN',
                        'value': f'({quoted})', 'sql': f"c.age_group IN ({quoted})"
                    })

                elif op == 'between':
                    lo = int(match.group(1))
                    hi = int(match.group(2))
                    groups = [g for g in AGE_GROUPS
                             if any(int(p) >= lo and int(p) <= hi
                                    for p in g.replace('+','').split('-'))]
                    if not groups:
                        groups = ['25-34']
                    quoted = ', '.join(f"'{g}'" for g in groups)
                    filters.append({
                        'column': 'c.age_group', 'operator': 'IN',
                        'value': f'({quoted})', 'sql': f"c.age_group IN ({quoted})"
                    })
            break

    return filters
