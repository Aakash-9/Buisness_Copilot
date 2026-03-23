"""
llm_normalizer.py

Uses LLaMA as a UNIVERSAL LANGUAGE NORMALIZER — the single fix for:
- Typos of any kind       (payd, onlin, oder, revenu)
- Shorthand              (2k = 2000, pmt = payment, amt = amount)
- Hindi/Hinglish         (se kam = below, dikha = show, wale = ones)
- Broken grammar         (order which are less = orders below)
- Mixed languages        (show me wale orders jo 2000 se kam ho)
- Casual speech          (bro, gimme, da, wit, nd, ya)
- Any language variation

It converts ANY query → clean, standard English
that your Python pipeline can parse reliably.

This runs BEFORE context_selector — one cheap LLM call
that makes ALL downstream processing robust.
"""

import re
from groq import Groq


NORMALIZER_SYSTEM_PROMPT = """You are a query normalizer for an Indian e-commerce analytics system.

Your ONLY job: Convert any messy, informal, or broken query into clean standard English.

Rules:
- Fix ALL spelling mistakes
- Expand shorthand: 2k→2000, pmt→payment, amt→amount, qty→quantity, inv→inventory, rev→revenue, ord→order, cust→customer, prod→product, cat→category, deliv→delivery, refnd→refund, sttlmt→settlement
- Translate Hindi/Hinglish to English:
  se kam / neeche = below/less than
  se zyada / upar = above/more than
  dikha / dikhao = show
  kitne / kitna = how many / how much
  wale / wali = ones/which are
  jo / jinka / jinki = which/whose
  aur = and
  ya = or
  sab = all
  kuch = some
  hue / ho = were/are
  chahiye = I want/give me
  mein / is mahine = this month
  pichle = last
  aaj = today
  kal = yesterday
- Fix grammar: "order which are less" → "orders below"
- Keep all numbers exactly as-is
- Keep business terms: orders, revenue, sellers, returns, refunds, payments, inventory, shipments, customers, products, category, brand, delivery, settlement, cancellation, warehouse
- Keep filter terms: below, above, between, less than, more than, prepaid, cod, online, delivered, cancelled, returned, shipped
- Output ONLY the normalized English query — nothing else, no explanation

Examples:
Input: ordr below 2000 onlin pay
Output: orders below 2000 online payment

Input: kuch orders dikha jo 2000 se kam ho
Output: show orders which are below 2000

Input: show me da orders wit online paymt n below 2k
Output: show orders with online payment and below 2000

Input: payd onlin ordr les than 2000
Output: paid online orders less than 2000

Input: kitne order hue jinki value 2000 se kam thi
Output: how many orders whose value was below 2000

Input: 2000 se neeche wale orders chahiye online payment ke
Output: show orders below 2000 with online payment

Input: bro gimme orders under 2k paid online
Output: show orders under 2000 paid online

Input: revenu by categry last mnth
Output: revenue by category last month

Input: top sellrs by slaes
Output: top sellers by sales

Input: refuds is mahine ke
Output: refunds this month"""


def llm_normalize(query: str, api_key: str) -> dict:
    """
    Normalizes any messy query to clean English using LLaMA.
    
    Returns:
        {
          'original':    original query,
          'normalized':  clean English version,
          'was_changed': bool
        }
    """
    client = Groq(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": NORMALIZER_SYSTEM_PROMPT},
                {"role": "user",   "content": query}
            ],
            temperature=0.0,
            max_tokens=100,   # Short output — just the normalized query
        )

        normalized = response.choices[0].message.content.strip()

        # Strip any quotes the model might add
        normalized = normalized.strip('"\'')

        # Strip any preamble like "Normalized:" or "Output:"
        for prefix in ['normalized:', 'output:', 'result:', 'english:']:
            if normalized.lower().startswith(prefix):
                normalized = normalized[len(prefix):].strip()

        was_changed = normalized.lower() != query.lower().strip()

        return {
            'original':    query,
            'normalized':  normalized,
            'was_changed': was_changed,
        }

    except Exception as e:
        # On any error, return original unchanged — never block the pipeline
        return {
            'original':    query,
            'normalized':  query,
            'was_changed': False,
            'error':       str(e),
        }
