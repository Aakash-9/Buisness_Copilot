"""
insight_generator.py

Takes the user query + SQL results and generates:
1. A business insight summary (plain English answer)
2. Probable reasons / analysis
3. Follow-up questions the user might want to ask next
"""

import json
import re
from groq import Groq


INSIGHT_SYSTEM_PROMPT = """You are a senior business analyst for an Indian fashion e-commerce company (like Myntra/Ajio).

You receive:
- A business question the user asked
- The SQL query that was run
- The actual data results from the database

Your job is to:
1. Answer the question in plain simple English using the actual numbers
2. Give 2-3 probable business reasons / analysis for what the data shows
3. Suggest 3 follow-up questions the user should ask next

Rules:
- Be specific — use the actual numbers from the results
- Be concise — no long paragraphs
- Think like a business analyst, not a programmer
- If result is 0 or empty, explain why that might be and what to check
- Use Indian business context (rupees, Indian cities, fashion categories)
- Format your response EXACTLY as JSON like this:

{
  "summary": "Direct answer to the question in 1-2 sentences with actual numbers",
  "insights": [
    "Insight 1 with specific numbers",
    "Insight 2 with specific numbers", 
    "Insight 3 with specific numbers"
  ],
  "followup_questions": [
    "Follow up question 1?",
    "Follow up question 2?",
    "Follow up question 3?"
  ]
}

Return ONLY the JSON. No markdown, no explanation, no extra text."""


def generate_insights(user_query: str, sql: str, result: dict, api_key: str) -> dict:
    """
    Generate business insights from query results.
    
    Args:
        user_query : original question
        sql        : the SQL that was executed
        result     : dict with 'rows', 'columns', 'rowcount'
        api_key    : Groq API key
    
    Returns:
        {
          'summary':            str,
          'insights':           list,
          'followup_questions': list,
          'error':              str or None
        }
    """

    # Format results for the LLM
    rows     = result.get('rows', [])
    rowcount = result.get('rowcount', 0)

    if rowcount == 0:
        result_text = "Query returned 0 rows / no data found."
    elif rowcount <= 20:
        result_text = f"Query returned {rowcount} row(s):\n{json.dumps(rows, indent=2, default=str)}"
    else:
        result_text = f"Query returned {rowcount} rows. First 20:\n{json.dumps(rows[:20], indent=2, default=str)}"

    prompt = f"""User asked: "{user_query}"

SQL executed:
{sql}

Results from database:
{result_text}

Generate business insights as JSON."""

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.3,
            max_tokens=600,
        )

        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'```json|```', '', raw).strip()

        parsed = json.loads(raw)

        return {
            'summary':            parsed.get('summary', ''),
            'insights':           parsed.get('insights', []),
            'followup_questions': parsed.get('followup_questions', []),
            'error':              None
        }

    except json.JSONDecodeError:
        # Extract what we can from raw text
        return {
            'summary':            raw[:300] if raw else 'Could not parse insight.',
            'insights':           [],
            'followup_questions': [],
            'error':              'JSON parse error'
        }
    except Exception as e:
        return {
            'summary':            '',
            'insights':           [],
            'followup_questions': [],
            'error':              str(e)
        }


def print_insights(user_query: str, result: dict, insights: dict):
    """Print formatted insights to terminal."""

    print(f"\n{'═'*62}")
    print(f"  BUSINESS INSIGHT")
    print(f"{'═'*62}")

    # Summary
    if insights.get('summary'):
        print(f"\n  {insights['summary']}")

    # Data table
    if result.get('rowcount', 0) > 0:
        from core.supabase_executor import _format_results
        print(_format_results(result))

    # Probable reasons
    if insights.get('insights'):
        print(f"\n  PROBABLE REASONS / ANALYSIS:")
        for i, insight in enumerate(insights['insights'], 1):
            print(f"  {i}. {insight}")

    # Follow-up questions
    if insights.get('followup_questions'):
        print(f"\n  YOU MIGHT ALSO WANT TO ASK:")
        for q in insights['followup_questions']:
            print(f"  → {q}")

    print(f"\n{'─'*62}\n")
