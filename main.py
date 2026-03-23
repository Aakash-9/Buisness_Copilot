"""
main.py — NL → SQL System

Pipeline:
  Step 0  → LLM Normalizer    (fixes typos, Hindi, shorthand, broken grammar)
  Step 1  → Context selector  (keyword matching on clean text)
  Step 1b → Semantic fallback (if keywords still find nothing)
  Step 2  → Prompt builder
  Step 3  → SQL generator
  Step 4  → Validator

Usage:
  python main.py --query "kitne orders hue jo 2000 se kam the"
  python main.py --interactive
  python main.py --demo
"""

import sys
import argparse

sys.path.insert(0, __file__.rsplit('\\', 1)[0])
sys.path.insert(0, __file__.rsplit('/', 1)[0])

from core.context_selector     import select_context
from core.prompt_builder       import build_prompt
from core.sql_generator        import generate_sql, get_client
from core.validator            import validate_sql
from core.semantic_interpreter import interpret, merge_with_context
from core.llm_normalizer       import llm_normalize
from core.scope_validator      import validate_scope, get_dataset_summary
from core.supabase_executor    import execute_sql, _format_results
from core.insight_generator    import generate_insights, print_insights


# ─────────────────────────────────────────────
# SIGNAL CHECKS
# ─────────────────────────────────────────────

def _has_signal(context: dict) -> bool:
    return bool(context['metrics']) or \
           bool(context['needed_tables']) or \
           bool(context['filters']['all_sql_filters'])


def _is_vague(context: dict) -> bool:
    """Only truly vague when nothing at all was found."""
    return not bool(context['metrics']) and \
           not bool(context['needed_tables']) and \
           not bool(context['filters']['all_sql_filters'])


CLARIFICATION_SUGGESTIONS = [
    "  • 'show revenue this month'",
    "  • 'show cancellations and losses this month'",
    "  • 'which sellers have highest refunds'",
    "  • 'orders below 2000 with online payment'",
    "  • 'show delivery performance this month'",
]


# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

def run_pipeline(user_query: str, verbose: bool = True) -> dict:
    """Full NL → SQL pipeline."""

    if verbose:
        print(f"\n{'═'*62}")
        print(f"  QUERY : {user_query}")
        print(f"{'═'*62}")

    # Get API key once — used by both normalizer and SQL generator
    try:
        api_key = get_client().api_key
    except Exception as e:
        print(f"\n  ✗ Cannot get API key: {e}")
        return {'query': user_query, 'sql': None, 'valid': False,
                'errors': [str(e)], 'warnings': [], 'context': {}}

    # ── STEP 0: LLM Normalization ────────────────────────────
    # Fix typos, Hindi, shorthand, broken grammar — before any Python processing
    if verbose:
        print(f"\n  [0/4] Normalizing query...")

    norm = llm_normalize(user_query, api_key)
    clean_query = norm['normalized']

    if verbose:
        if norm['was_changed']:
            print(f"        Original   : {user_query}")
            print(f"        Normalized : {clean_query}")
        else:
            print(f"        No changes needed")

    # ── STEP 0b: Scope check ─────────────────────────────────
    # Check if asking about something not in the dataset
    scope_check = validate_scope(clean_query)
    if not scope_check['in_scope']:
        print(f"\n  ⚠️  This is outside our dataset scope.")
        print(f"\n  Reason     : {scope_check['reason']}")
        print(f"\n  What we have: {scope_check['suggestion']}")
        print(f"\n  Tip: Type 'what data do we have' to see full dataset summary.")
        return {'query': user_query, 'sql': None, 'valid': False,
                'errors': ['Out of dataset scope'], 'warnings': [],
                'context': {}, 'out_of_scope': True}

    # Handle "what data do we have" type queries
    info_patterns = [
        'what data do we have', 'what categories', 'what products',
        'what is in dataset', 'what can i ask', 'what do you know',
        'show me data categories', 'dataset summary', 'what brands',
        'what is available', 'what data is available',
    ]
    if any(p in clean_query.lower() for p in info_patterns):
        print(get_dataset_summary())
        return {'query': user_query, 'sql': None, 'valid': True,
                'errors': [], 'warnings': [], 'context': {},
                'info_response': True}

    # ── STEP 1: Keyword context selection ───────────────────
    context = select_context(clean_query)

    if verbose:
        kw_found = _has_signal(context)
        layer_msg = '✅ found signal' if kw_found else '⚠️  weak signal — activating semantic layer'
        print(f"\n  [1/4] Keyword layer {layer_msg}")

    # ── STEP 1b: Semantic fallback ───────────────────────────
    used_semantic = False
    if not _has_signal(context):
        if verbose:
            print(f"        Calling semantic interpreter...")
        try:
            interpretation = interpret(clean_query, api_key)
            context = merge_with_context(interpretation, context)
            used_semantic = True
            if verbose:
                print(f"        Understood as: {interpretation.get('interpreted_as')}")
                print(f"        Confidence   : {interpretation.get('confidence')}")
        except Exception as e:
            if verbose:
                print(f"        Semantic error: {e}")

    # ── Still nothing → clarify ──────────────────────────────
    if _is_vague(context):
        print(f"\n  ⚠️  Could not understand this query.")
        print(f"  Please try being more specific. Examples:")
        for s in CLARIFICATION_SUGGESTIONS:
            print(s)
        return {'query': user_query, 'sql': None, 'valid': False,
                'errors': ['Query too vague'], 'warnings': [], 'context': context}

    if verbose:
        layer = '(semantic+keyword)' if used_semantic else '(keyword)'
        print(f"\n  [1/4] Context ready {layer}")
        print(f"        Intent       : {context['intent'].upper()}")
        print(f"        Metrics      : {[m[0] for m in context['metrics']] or 'LLM infers'}")
        print(f"        Time filter  : {context['time_filter']}")
        print(f"        Tables       : {context['needed_tables'] or 'core only'}")
        if context['segmentation']:
            print(f"        Segments     : {context['segmentation']}")
        if context['filters']['all_sql_filters']:
            print(f"        Filters      : {context['filters']['all_sql_filters']}")

    # ── STEP 2: Build prompt ─────────────────────────────────
    prompt = build_prompt(clean_query, context)
    if verbose:
        print(f"\n  [2/4] Prompt built ({len(prompt)} chars)")

    # ── STEP 3: Generate SQL ─────────────────────────────────
    if verbose:
        print(f"\n  [3/4] Calling Groq API (LLaMA-3.3-70B)...")
    sql = generate_sql(prompt)

    if verbose:
        print(f"\n  [4/4] SQL Generated:")
        print(f"\n{'─'*62}")
        print(sql)
        print(f"{'─'*62}")

    # ── STEP 4: Validate ─────────────────────────────────────
    result = validate_sql(sql)
    if verbose:
        print(f"\n  Validation: {result}")

    # ── STEP 5: Execute on Supabase ──────────────────────────
    exec_result = {'success': False, 'rows': [], 'rowcount': 0}
    if result.is_valid:
        if verbose:
            print(f"\n  [5/5] Executing on Supabase...")
        try:
            exec_result = execute_sql(sql)
            if not exec_result['success'] and verbose:
                print(f"\n  ❌ Execution error: {exec_result['error']}")
        except Exception as e:
            if verbose:
                print(f"\n  ❌ Supabase error: {e}")

    # ── STEP 6: Generate business insights ───────────────────
    if exec_result.get('success'):
        if verbose:
            print(f"\n  [6/6] Generating business insights...")
        try:
            insights = generate_insights(user_query, sql, exec_result, api_key)
            print_insights(user_query, exec_result, insights)
        except Exception as e:
            if verbose:
                print(f"\n  ⚠️  Insight error: {e}")
                print(_format_results(exec_result))
                print(f"\n  ❌ Supabase connection error: {e}")
                print(f"     → Check credentials in core/supabase_executor.py")
        print()
    else:
        exec_result = {'success': False, 'rows': [], 'rowcount': 0}

    return {
        'query':          user_query,
        'normalized':     clean_query,
        'sql':            sql,
        'valid':          result.is_valid,
        'errors':         result.errors,
        'warnings':       result.warnings,
        'used_semantic':  used_semantic,
        'context':        context,
        'result':         exec_result if result.is_valid else None,
    }


# ─────────────────────────────────────────────
# SAMPLE QUERIES — tests every layer
# ─────────────────────────────────────────────

SAMPLE_QUERIES = [
    # Clean
    "why are we facing losses this month",
    # Typos
    "show revenu by categry last mnth",
    # Shorthand + casual
    "gimme orders under 2k paid online",
    # Hindi
    "kitne orders hue jo 2000 se kam the aur online payment tha",
    # Broken grammar + typo
    "show oder which are les than 2000 and payd onlin",
    # Mixed
    "bro show me top 5 sellers by slaes is mahine",
    # Complex
    "cod orders above 1000 that got cancelled this month",
]


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NL → SQL System")
    parser.add_argument('--query',       type=str,  help='Run a single query')
    parser.add_argument('--interactive', action='store_true', help='Interactive REPL')
    parser.add_argument('--demo',        action='store_true', help='Run sample queries')
    args = parser.parse_args()

    if args.query:
        run_pipeline(args.query)

    elif args.interactive:
        print("\n  NL → SQL System  |  Type 'exit' to quit\n")
        while True:
            try:
                query = input("  Ask a business question: ").strip()
                if query.lower() in ('exit', 'quit', 'q'):
                    break
                if query:
                    run_pipeline(query)
            except KeyboardInterrupt:
                break
        print("\n  Bye!\n")

    elif args.demo:
        for q in SAMPLE_QUERIES:
            try:
                run_pipeline(q)
            except Exception as e:
                print(f"  ✗ {q}\n    {e}\n")
    else:
        run_pipeline(SAMPLE_QUERIES[0])


if __name__ == "__main__":
    main()
