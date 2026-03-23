"""
query_normalizer.py — synonym expansion and vague query handling
Expands informal/synonym phrases into standard terms context_selector understands.
Returns: (normalized_query: str, expansions: list of (original, expanded))
"""

SYNONYM_MAP = [
    # REVENUE
    ('how much did we earn',        'what is our revenue'),
    ('how much we earned',          'total revenue'),
    ('how much money came in',      'total revenue'),
    ('money came in',               'total revenue'),
    ('what did we make',            'total revenue'),
    ('how much we made',            'total revenue'),
    ('how much we collected',       'total revenue'),
    ('money earned',                'total revenue'),
    ('money collected',             'total revenue'),
    ('total collections',           'total revenue'),
    ('sales figures',               'total revenue'),
    ('top line',                    'total revenue'),
    ('what we earned',              'total revenue'),
    ('earnings',                    'revenue'),
    ('how much income',             'total revenue'),
    # LOSS
    ('bleeding money',              'facing losses'),
    ('losing money',                'facing losses'),
    ('lose money',                  'total loss'),
    ('how much did we lose',        'total loss'),
    ('went wrong financially',      'loss and cancellations'),
    ('numbers are down',            'revenue down losses high'),
    ('numbers down',                'total loss'),
    ('in the red',                  'facing losses'),
    ('financial loss',              'total loss'),
    ('show me loss',                'total loss'),
    # RETURNS
    ('items came back',             'total returns'),
    ('products came back',          'total returns'),
    ('sent back',                   'returned items returns'),
    ('came back',                   'returns'),
    ('items returned',              'total returns'),
    ('return count',                'total returns count'),
    ('return mila',                 'returns this month'),
    ('kitne returns',               'how many returns'),
    ('wapas aaya',                  'returns'),
    # CANCELLATIONS
    ('not fulfilled',               'cancelled orders'),
    ('did not go through',          'cancelled orders'),
    ('orders that failed',          'cancelled orders'),
    ('dropped orders',              'cancelled orders'),
    ('orders fell through',         'cancelled orders'),
    ('kitne cancel hue',            'how many orders cancelled'),
    ('cancel hue',                  'cancelled orders'),
    ('not completed orders',        'cancelled orders'),
    # REFUNDS
    ('money back',                  'total refunds'),
    ('gave money back',             'total refunds'),
    ('paise wapas',                 'refunds'),
    # DELIVERY
    ('shipment delays',             'late deliveries delivery performance'),
    ('delayed shipments',           'late deliveries delivery performance'),
    ('delivery issues',             'delivery performance'),
    ('shipping issues',             'delivery performance'),
    ('packages delayed',            'late deliveries'),
    ('not delivered',               'pending delivery shipments'),
    # PAYMENT
    ('online payment',              'prepaid payment'),
    ('digital payment',             'prepaid payment'),
    ('paid online',                 'prepaid orders'),
    ('non cod',                     'prepaid orders'),
    ('not cod',                     'prepaid orders'),
    ('cash payment',                'cod payment'),
    ('cash orders',                 'cod orders'),
    ('payment not done',            'payment failed'),
    ('transaction failed',          'payment failed'),
    # INVENTORY
    ('out of items',                'out of stock inventory'),
    ('no stock',                    'zero stock inventory'),
    ('stock finished',              'zero available inventory'),
    # SELLERS
    ('vendor',                      'seller'),
    ('vendors',                     'sellers'),
    ('merchant',                    'seller'),
    ('merchants',                   'sellers'),
    # HINDI / MIXED
    ('kitna mila',                  'total revenue'),
    ('kitna revenue',               'total revenue'),
    ('kitne orders',                'total orders'),
    ('kitna loss',                  'total loss'),
    ('loss kyun',                   'why loss'),
    ('loss ho raha',                'facing losses'),
    ('sales kya hai',               'what is revenue'),
    ('refund kitna',                'total refund amount'),
    ('kitna refund',                'total refund amount'),
    # VAGUE → STRUCTURED
    ('how are we doing',            'show revenue orders cancellations'),
    ('how is business',             'show revenue and orders'),
    ('how did we perform',          'show revenue cancellation rate return rate'),
    ('give me a summary',           'show revenue orders cancellations refunds'),
    ('show me everything',          'show revenue orders cancellations refunds'),
    ('important numbers',           'revenue orders cancellations'),
    ('whats the status',            'show orders revenue'),
    ('any problems',                'show cancellations refunds losses'),
    ('what should i look at',       'show revenue losses cancellation rate'),
]

CLARIFICATION_TRIGGERS = [
    'all data', 'full report', 'help me', 'i dont know',
]

CLARIFICATION_SUGGESTIONS = [
    'show revenue this month',
    'show losses this month',
    'show cancelled orders this month',
    'show return rate by category',
    'show delivery performance this month',
    'show payment failures this month',
    'show inventory stock levels',
]

def normalize_query(query: str) -> tuple:
    """Returns (normalized_query, expansions_list)"""
    normalized = query.lower().strip()
    expansions = []
    # Longest phrase first — avoids partial replacements
    for synonym, standard in sorted(SYNONYM_MAP, key=lambda x: -len(x[0])):
        if synonym in normalized:
            normalized = normalized.replace(synonym, standard)
            expansions.append((synonym, standard))
    return normalized, expansions

def needs_clarification(query: str) -> bool:
    q = query.lower().strip()
    return any(t in q for t in CLARIFICATION_TRIGGERS)

def get_clarification_message() -> str:
    msg = "\n  Your question is quite broad. Try being more specific:\n"
    for s in CLARIFICATION_SUGGESTIONS:
        msg += f'    → "{s}"\n'
    return msg


# Spell correction — edit distance based, no external libs
SPELL_VOCAB = {
    'revenue','sales','income','earnings','losses','orders','cancellation',
    'cancelled','cancellations','returns','refund','refunds','refunded',
    'payment','payments','settlement','shipment','shipments','shipped',
    'inventory','warehouse','products','sellers','customers','category',
    'delivery','delivered','discount','commission','figures','summary',
    'performance','percentage','average','highest','lowest','monthly',
    'weekly','details','status','active','inactive','pending','completed',
    'rejected','settled','transfer','channel','gateway','failures',
}
NEVER_CORRECT = {
    'are','the','did','not','was','has','had','how','why','who','what',
    'when','where','this','that','they','were','with','from','much',
    'many','make','came','come','give','show','tell','find','get','down',
    'into','over','some','more','less','most','last','next','just','back',
    'than','then','them','been','being','doing','going','our','out','top',
    'low','high','new','all','any','its','money','earn','loss','rate',
    'list','best','days','day','week','year','month','time','date','price',
    'send','sent','want','work','made','lose','lost','fail','failed','wrong',
    'app','cod','upi','gmv','aov','mrp','hue','aaye','kitna','kitne','cancel',
}

def _edist(a, b):
    if a == b: return 0
    if abs(len(a)-len(b)) > 2: return 99
    prev = list(range(len(b)+1))
    for i,c1 in enumerate(a):
        curr = [i+1]
        for j,c2 in enumerate(b):
            curr.append(min(prev[j+1]+1, curr[j]+1, prev[j]+(0 if c1==c2 else 1)))
        prev = curr
    return prev[len(b)]

def _fix_word(w):
    lw = w.lower()
    if lw in NEVER_CORRECT or len(lw) < 5 or lw in SPELL_VOCAB:
        return w
    best, bd = w, 99
    for v in SPELL_VOCAB:
        d = _edist(lw, v)
        if d < bd and d <= 2:
            best, bd = v, d
    return best if bd <= 2 else w

def correct_spelling(query: str) -> tuple:
    """Returns (corrected_query, list_of_changes)"""
    words  = query.split()
    result = []
    changes = []
    for word in words:
        fixed = _fix_word(word)
        if fixed != word:
            changes.append(f'"{word}" → "{fixed}"')
        result.append(fixed)
    return ' '.join(result), changes


def normalize_query_full(query: str) -> dict:
    """
    Full normalization: spell + synonyms + clarification check.
    Returns dict for main.py compatibility.
    """
    original = query
    all_changes = []

    # Step 1: spell correction
    spell_fixed, spell_changes = correct_spelling(query)
    all_changes += [f'[SPELL] {c}' for c in spell_changes]

    # Step 2: synonym expansion
    expanded, syn_changes = normalize_query(spell_fixed)
    all_changes += [f'[SYNONYM] {s} → {t}' for s, t in syn_changes]

    return {
        'original':                  original,
        'normalized':                expanded,
        'changes':                   all_changes,
        'was_changed':               bool(all_changes),
        'needs_clarification':       needs_clarification(expanded),
        'clarification_suggestions': CLARIFICATION_SUGGESTIONS,
    }
