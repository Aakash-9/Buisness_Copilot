"""
supabase_executor.py
Connects to Supabase via REST API (HTTPS port 443).
Works on ALL networks — no firewall issues.
"""

import urllib.request
import json


# ─────────────────────────────────────────────
# PASTE YOUR CREDENTIALS HERE
# ─────────────────────────────────────────────

SUPABASE_URL = "https://mxxqykzsqjvchvxfeaud.supabase.co"
SUPABASE_KEY = "sb_publishable_N7Ri6rsHXBg-A8XFhhanEQ_8Y5Vt3Dp"


# ─────────────────────────────────────────────
# SAFETY
# ─────────────────────────────────────────────

FORBIDDEN = ['delete', 'update', 'insert', 'drop', 'truncate', 'alter', 'create']

def _is_safe(sql: str) -> bool:
    sql_lower = sql.strip().lower()
    if not sql_lower.startswith('select'):
        return False
    for word in FORBIDDEN:
        if f' {word} ' in f' {sql_lower} ':
            return False
    return True


# ─────────────────────────────────────────────
# MAIN EXECUTOR
# ─────────────────────────────────────────────

def execute_sql(sql: str, limit: int = 100) -> dict:

    if not _is_safe(sql):
        return {'success': False, 'rows': [], 'columns': [], 'rowcount': 0,
                'error': 'Only SELECT queries are allowed.'}

    sql_clean = sql.strip().rstrip(';')
    if 'limit' not in sql_clean.lower():
        sql_clean += f' LIMIT {limit}'

    # ── PRIMARY: call execute_query RPC (the function you created in Supabase)
    endpoint = f"{SUPABASE_URL}/rest/v1/rpc/execute_query"
    payload  = json.dumps({"query": sql_clean}).encode('utf-8')

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            'Content-Type':  'application/json',
            'apikey':        SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode('utf-8'))

        # execute_query returns JSON array
        if isinstance(body, list):
            # Each item may itself be a JSON string — unwrap if needed
            rows = []
            for item in body:
                if isinstance(item, dict):
                    rows.append(item)
                elif isinstance(item, str):
                    try:
                        rows.append(json.loads(item))
                    except Exception:
                        rows.append({'value': item})
                else:
                    rows.append({'value': str(item)})

            columns = list(rows[0].keys()) if rows else []
            return {'success': True, 'rows': rows, 'columns': columns,
                    'rowcount': len(rows), 'error': None}

        # Sometimes returns a single JSON object with rows inside
        if isinstance(body, dict):
            rows = body.get('rows', [])
            columns = list(rows[0].keys()) if rows else []
            return {'success': True, 'rows': rows, 'columns': columns,
                    'rowcount': len(rows), 'error': None}

        return {'success': False, 'rows': [], 'columns': [], 'rowcount': 0,
                'error': f'Unexpected response: {str(body)[:200]}'}

    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8')
        return {'success': False, 'rows': [], 'columns': [], 'rowcount': 0,
                'error': f'HTTP {e.code}: {err[:300]}'}

    except Exception as ex:
        return {'success': False, 'rows': [], 'columns': [], 'rowcount': 0,
                'error': str(ex)}


# ─────────────────────────────────────────────
# FORMAT RESULTS AS TABLE
# ─────────────────────────────────────────────

def _format_results(result: dict, max_rows: int = 20) -> str:

    if not result['success']:
        return f"\n  ❌ {result['error']}"

    if result['rowcount'] == 0:
        return "\n  No results found."

    rows    = result['rows'][:max_rows]
    columns = result['columns']

    widths = {col: len(str(col)) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col, ''))))

    sep   = '  +' + '+'.join('-' * (widths[c] + 2) for c in columns) + '+'
    head  = '  |' + '|'.join(f' {c:<{widths[c]}} ' for c in columns) + '|'
    lines = [sep, head, sep]

    for row in rows:
        line = '  |' + '|'.join(f' {str(row.get(c,"")):<{widths[c]}} ' for c in columns) + '|'
        lines.append(line)
    lines.append(sep)

    summary = f"\n  {result['rowcount']} row(s) returned"
    if result['rowcount'] > max_rows:
        summary += f" (showing first {max_rows})"

    return '\n'.join(lines) + summary