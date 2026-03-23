"""
query_preprocessor.py

Two jobs before the query hits context_selector:
1. SPELL CORRECTION  — fixes common typos using edit-distance (no external libs)
2. ALIAS EXPANSION   — maps synonyms/phrases → canonical business terms

Both run in <1ms. Zero external dependencies.
"""

import re


# ─────────────────────────────────────────────────────────────
# 1. SPELL CORRECTOR
# Pure Python edit-distance against a business vocabulary.
# Only corrects words that are clearly wrong (distance=1 or 2).
# ─────────────────────────────────────────────────────────────

BUSINESS_VOCAB = [
    # Core business terms
    'revenue', 'sales', 'orders', 'order', 'products', 'product',
    'sellers', 'seller', 'customers', 'customer', 'payments', 'payment',
    'returns', 'return', 'refunds', 'refund', 'shipments', 'shipment',
    'inventory', 'warehouse', 'warehouses', 'settlement', 'settlements',
    'cancellations', 'cancellation', 'cancelled', 'delivered', 'delivery',
    'category', 'categories', 'brand', 'brands', 'region', 'regions',
    'losses', 'loss', 'profit', 'discount', 'discounts', 'commission',
    # Actions / question words
    'show', 'tell', 'list', 'find', 'give', 'display', 'fetch', 'get',
    'what', 'which', 'where', 'when', 'how', 'why', 'who', 'total',
    'count', 'average', 'summary', 'report', 'compare', 'top', 'bottom',
    # Time words
    'today', 'yesterday', 'weekly', 'monthly', 'daily', 'month',
    'week', 'year', 'quarter',
    # Attributes
    'status', 'details', 'information', 'data', 'figures', 'numbers',
    'amount', 'value', 'price', 'rate', 'percentage', 'ratio',
    'highest', 'lowest', 'maximum', 'minimum', 'failed', 'successful',
    'active', 'inactive', 'pending', 'completed', 'rejected',
    # Table-related
    'payments', 'couriers', 'courier', 'damages', 'damaged',
    'movements', 'movement', 'inbound', 'outbound',
]

VOCAB_SET = set(BUSINESS_VOCAB)


def _edit_distance(s1: str, s2: str) -> int:
    """Fast edit distance — only computes up to distance 3 then stops."""
    if abs(len(s1) - len(s2)) > 3:
        return 99
    m, n = len(s1), len(s2)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if s1[i-1] == s2[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j-1])
            prev = temp
        if min(dp) > 2:
            return 99
    return dp[n]


# Words to NEVER correct — common English words that look similar to business terms
PROTECTED_WORDS = {
    'money', 'came', 'come', 'make', 'made', 'earn', 'earned', 'earn',
    'down', 'went', 'gone', 'going', 'doing', 'done', 'give', 'gave',
    'take', 'took', 'have', 'been', 'were', 'they', 'them', 'then',
    'when', 'what', 'that', 'this', 'with', 'from', 'into', 'upon',
    'over', 'under', 'much', 'many', 'more', 'most', 'some', 'such',
    'also', 'back', 'well', 'just', 'even', 'only', 'both', 'each',
    'same', 'than', 'then', 'once', 'here', 'there', 'where', 'while',
    'about', 'above', 'below', 'after', 'before', 'since', 'until',
    'again', 'place', 'right', 'still', 'could', 'would', 'should',
    'might', 'shall', 'will', 'been', 'very', 'good', 'high', 'show',
    'tell', 'find', 'lost', 'loss', 'sent', 'send', 'went', 'year',
    'know', 'need', 'want', 'feel', 'look', 'seem', 'keep', 'hold',
    'week', 'last', 'next', 'past', 'late', 'early', 'today', 'rate',
    'paid', 'fail', 'fell', 'fall', 'rise', 'rose', 'drop', 'grew',
    'grow', 'sold', 'sell', 'less', 'zero', 'free', 'full', 'open',
    'type', 'kind', 'list', 'data', 'info', 'city', 'area', 'zone',
    'code', 'note', 'date', 'time', 'days', 'item', 'unit', 'line',
    'page', 'file', 'case', 'plan', 'said', 'says', 'gets', 'puts',
}


def _correct_word(word: str) -> str:
    """Correct a single word if it's clearly a typo. Leave it alone otherwise."""
    w = word.lower()

    # Already correct
    if w in VOCAB_SET:
        return word

    # Protected common English words — never touch these
    if w in PROTECTED_WORDS:
        return word

    # Too short to correct safely
    if len(w) <= 3:
        return word

    # Numbers / punctuation — skip
    if not w.isalpha():
        return word

    # Find closest vocab word
    best_word = None
    best_dist = 99

    for vocab_word in BUSINESS_VOCAB:
        if abs(len(vocab_word) - len(w)) > 2:
            continue
        d = _edit_distance(w, vocab_word)
        if d < best_dist:
            best_dist = d
            best_word = vocab_word

    # Only correct distance=1 (one letter different) — distance 2 causes false positives
    if best_dist <= 1 and best_word:
        return best_word

    return word


def spell_correct(query: str) -> str:
    """
    Corrects obvious typos in the query.
    Preserves numbers, punctuation, and correctly-spelled words.
    """
    words = query.split()
    corrected = [_correct_word(w) for w in words]
    result = ' '.join(corrected)
    return result


# ─────────────────────────────────────────────────────────────
# 2. ALIAS EXPANDER
# Maps informal/synonym phrases → canonical terms the
# context_selector and metric_glossary can match.
# ─────────────────────────────────────────────────────────────

# Order matters — longer phrases checked first to avoid partial matches
ALIAS_MAP = [

    # ── REVENUE synonyms ──────────────────────────────────────
    ('how much did we earn',        'what is our revenue'),
    ('how much we earned',          'what is our revenue'),
    ('how much money came in',      'what is our revenue'),
    ('money came in',               'revenue'),
    ('what did we make this month', 'what is our revenue this month'),
    ('what did we make',            'what is our revenue'),
    ('how much we made',            'what is our revenue'),
    ('how much we collected',       'what is our revenue'),
    ('money collected',             'revenue'),
    ('money earned',                'revenue'),
    ('total earnings',              'total revenue'),
    ('our earnings',                'our revenue'),
    ('sales figures',               'revenue'),
    ('business income',             'revenue'),
    ('how much money',              'how much revenue'),
    ('kitna mila',                  'revenue'),
    ('kitna aaya',                  'revenue'),
    ('kitni kamai',                 'revenue'),
    ('kamai kitni',                 'revenue'),

    # ── LOSS synonyms ─────────────────────────────────────────
    ('bleeding money',              'facing losses'),
    ('where are we losing',         'what are our losses'),
    ('how much did we lose',        'what are our losses'),
    ('show me loss',                'what are our losses'),
    ('what went wrong financially', 'what are our losses'),
    ('why are numbers down',        'why are we facing losses'),
    ('numbers are down',            'losses this month'),
    ('financial problems',          'losses'),
    ('loss ho raha',                'facing losses'),    # Hindi
    ('nuksaan',                     'losses'),           # Hindi: loss
    ('ghata',                       'losses'),           # Hindi: deficit

    # ── CANCELLATION synonyms ─────────────────────────────────
    ('orders that failed',          'cancelled orders'),
    ('orders not fulfilled',        'cancelled orders'),
    ('orders that did not go',      'cancelled orders'),
    ('did not go through',          'cancelled'),
    ('unfulfilled orders',          'cancelled orders'),
    ('dropped orders',              'cancelled orders'),
    ('kitne cancel hue',            'how many cancelled orders'),  # Hindi
    ('cancel ho gaye',              'cancelled orders'),           # Hindi
    ('orders cancel',               'cancelled orders'),

    # ── RETURNS synonyms ─────────────────────────────────────
    ('items came back',             'returns'),
    ('products came back',          'returns'),
    ('products sent back',          'returns'),
    ('items sent back',             'returns'),
    ('items returned',              'total returns'),
    ('came back',                   'returned'),
    ('return mila',                 'total returns'),    # Hindi
    ('kitne returns aaye',          'how many returns'), # Hindi
    ('wapas aaye',                  'returns'),          # Hindi: came back
    ('return count',                'number of returns'),

    # ── REFUNDS synonyms ──────────────────────────────────────
    ('money refunded',              'total refund amount'),
    ('money given back',            'total refund amount'),
    ('refunded to customers',       'total refund amount'),
    ('paise wapas',                 'refunds'),          # Hindi: money back

    # ── INVENTORY synonyms ────────────────────────────────────
    ('inventori',                   'inventory'),        # typo expansion
    ('stock status',                'inventory health'),
    ('stock levels',                'inventory'),
    ('how much stock',              'inventory'),
    ('products available',          'available inventory'),
    ('out of stock',                'zero stock inventory'),
    ('stock khatam',                'out of stock inventory'),  # Hindi

    # ── VAGUE → SPECIFIC ──────────────────────────────────────
    ('how are we doing',            'show revenue cancellations returns this month'),
    ('how is business',             'show revenue orders cancellations this month'),
    ('give me a summary',           'show revenue orders cancellations losses this month'),
    ('show me everything',          'show revenue orders cancellations returns refunds'),
    ('business summary',            'revenue orders cancellations'),
    ('whats the status',            'show orders revenue this month'),
    ('how did we perform',          'show revenue orders cancellations this month'),
    ('any problems',                'show losses cancellations returns this month'),
    ('what should i look at',       'show revenue losses cancellations this month'),
    ('important numbers',           'revenue orders cancellations losses this month'),
    ('kya chal raha hai',           'show orders revenue this month'),  # Hindi: what's happening

    # ── PAYMENT synonyms ─────────────────────────────────────
    ('online payment',              'prepaid payment'),
    ('digital payment',             'prepaid payment'),
    ('paid online',                 'prepaid'),
    ('cash on delivery',            'cod'),
    ('payment problems',            'payment failures'),
    ('payment issue',               'payment failures'),
    ('payment fail',                'payment failures'),
    ('payment nahi hua',            'payment failures'),    # Hindi

    # ── DELIVERY synonyms ─────────────────────────────────────
    ('late deliveries',             'delayed shipments'),
    ('delayed orders',              'delayed shipments'),
    ('not delivered',               'in transit shipments'),
    ('stuck orders',                'in transit shipments'),
    ('delivery problems',           'delayed shipments'),
    ('delivery issue',              'delivery performance'),

    # ── SELLER synonyms ───────────────────────────────────────
    ('vendor performance',          'seller performance'),
    ('vendor revenue',              'seller revenue'),
    ('risky vendors',               'high risk sellers'),
    ('bad sellers',                 'high risk sellers'),
    ('seller nahi chal raha',       'inactive sellers'),   # Hindi

    # ── GENERIC CLEANUP ───────────────────────────────────────
    ('the revenue',                 'revenue'),
    ('the sales',                  'revenue'),
    ('slaes',                       'sales'),
    ('slae',                        'sale'),
    ('tell me about',               'show'),
    ('can you show',                'show'),
    ('i want to see',               'show'),
    ('please show',                 'show'),
    ('what are the',                'show'),
    ('give me the',                 'show'),
]


def expand_aliases(query: str) -> str:
    """
    Replaces known synonym phrases with canonical terms.
    Sorts by phrase length descending — longest match wins.
    Uses word-boundary check to prevent partial word corruption.
    """
    result = query.lower().strip()

    sorted_aliases = sorted(ALIAS_MAP, key=lambda x: len(x[0]), reverse=True)

    for phrase, replacement in sorted_aliases:
        # Only replace if phrase appears as a standalone sequence
        # (not as part of a larger word like 'cancellations' matching 'cancel')
        if phrase in result:
            # Check it's not a substring of a larger word
            idx = result.find(phrase)
            before = result[idx-1] if idx > 0 else ' '
            after  = result[idx+len(phrase)] if idx+len(phrase) < len(result) else ' '
            if (before == ' ' or idx == 0) and (after == ' ' or idx+len(phrase) == len(result)):
                result = result[:idx] + replacement + result[idx+len(phrase):]

    return result


# ─────────────────────────────────────────────────────────────
# 3. MAIN PREPROCESSOR — runs both steps
# ─────────────────────────────────────────────────────────────

def preprocess(query: str) -> dict:
    """
    Full preprocessing pipeline:
    1. Spell correct
    2. Alias expand

    Returns dict with original and all intermediate forms.
    """
    original        = query.strip()
    spell_fixed     = spell_correct(original)
    alias_expanded  = expand_aliases(spell_fixed)

    changed = alias_expanded != original.lower().strip()

    return {
        'original':       original,
        'spell_fixed':    spell_fixed,
        'final':          alias_expanded,
        'was_modified':   changed,
    }
