"""
spell_corrector.py — pure Python, zero external dependencies
Fixes common typos using direct lookup + Levenshtein distance.
Returns: (corrected_query: str, corrections: list of (orig, fixed))
"""

DOMAIN_VOCAB = {
    'revenue':       ['revenu','reveneu','reveue','rvenue','revnue'],
    'sales':         ['slaes','saels','sleas','sals'],
    'orders':        ['oder','odres','ordes','rders','oders','ordrs'],
    'order':         ['oder','odre','orde'],
    'sellers':       ['sellrs','selrs','sllers','selers'],
    'seller':        ['sellr','selr','seler'],
    'products':      ['produts','producs','prodcts','prducts'],
    'product':       ['produt','produc','prodct'],
    'customers':     ['custmers','cusomers','customes'],
    'customer':      ['custmer','cusomer','custome'],
    'payments':      ['paymnts','paymet','paymets','paymnt'],
    'payment':       ['paymet','paymnt','paiment'],
    'shipments':     ['shipmnt','shipmets','shipmnts'],
    'shipment':      ['shipmnt','shipmet'],
    'returns':       ['retuns','retrns','rturns','retunrs'],
    'return':        ['retun','retrn','rturn'],
    'refunds':       ['refuds','refnds'],
    'refund':        ['refud','refnd'],
    'inventory':     ['inventori','inventoy','inventry','inventary'],
    'warehouse':     ['wearhouse','warhouse','warehose','warehuse'],
    'warehouses':    ['wearhouses','warhouses'],
    'category':      ['categry','catagory','categori','catgory','caegory'],
    'cancellation':  ['cancelation','cancelltion'],
    'cancelled':     ['canceld','cancled'],
    'delivery':      ['delivry','dlivery','delivey','delvery'],
    'deliveries':    ['delivries','deliveries'],
    'settlement':    ['settlemnt','settelment','settlment'],
    'commission':    ['comission','commision'],
    'discount':      ['discont','discout','disount','discunt'],
    'performance':   ['performnce','preformance','performace'],
    'failures':      ['failurs','faliures','failres','failuers'],
    'failure':       ['failur','faliure','failre'],
    'status':        ['staus','statsu','satatus'],
    'summary':       ['sumary','summry','summay'],
    'inactive':      ['inactve','inactiv'],
    'details':       ['detals','detials','detais'],
    'region':        ['regin','regoin','reigon'],
    'damaged':       ['damged','damagd'],
    'available':     ['avialable','availble','availale'],
    'courier':       ['courir','couier','curier'],
    'exchange':      ['exchage','exchnge','exchane'],
    'loyalty':       ['loyaty','loyatly','loytaly'],
    'losses':        ['losss','lossess','lsses'],
    'delays':        ['delayes','delyas','delas'],
    'delayed':       ['delyed','delayyed'],
    'month':         [],   # never correct 'month' — prevent month→monthly
    'this':          [],   # never correct short common words
    'show':          [],
    'top':           [],
}

# Build fast lookup: typo → correct
TYPO_MAP = {typo: correct for correct, typos in DOMAIN_VOCAB.items() for typo in typos}

# Words to never touch (too short or too common)
SKIP_WORDS = {'a','an','the','is','are','was','were','be','been','to','of',
              'in','on','at','by','for','with','from','this','that','our',
              'we','me','my','us','it','its','how','why','what','which',
              'show','give','tell','get','find','list','top','all','and',
              'or','not','no','do','did','does','have','has','had',
              'month','week','year','day','today','yesterday','ago',
              'money','much','many','some','any','came','went','got',
              'high','low','big','small','good','bad','best','worst'}

def _levenshtein(s1, s2):
    if s1 == s2: return 0
    if len(s1) < len(s2): return _levenshtein(s2, s1)
    if not s2: return len(s1)
    prev = list(range(len(s2)+1))
    for c1 in s1:
        curr = [prev[0]+1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j+1]+1, curr[j]+1, prev[j]+(c1!=c2)))
        prev = curr
    return prev[-1]

def correct_query(query: str) -> tuple:
    words = query.split()
    corrected_words = []
    corrections = []
    for word in words:
        clean = word.strip('.,?!;:').lower()
        suffix = word[len(clean):]
        if clean in SKIP_WORDS or len(clean) <= 3:
            corrected_words.append(word)
            continue
        # Direct lookup
        if clean in TYPO_MAP:
            fixed = TYPO_MAP[clean]
            corrections.append((clean, fixed))
            corrected_words.append(fixed + suffix)
            continue
        # Fuzzy match — only for words not in vocab
        if clean not in DOMAIN_VOCAB:
            best, best_d = clean, 3
            for correct in DOMAIN_VOCAB:
                if abs(len(correct)-len(clean)) > 2: continue
                d = _levenshtein(clean, correct)
                if d < best_d:
                    best_d, best = d, correct
            if best != clean:
                corrections.append((clean, best))
                corrected_words.append(best + suffix)
                continue
        corrected_words.append(word)
    return ' '.join(corrected_words), corrections
