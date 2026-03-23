"""
sql_generator.py
Calls the Groq API to generate SQL from the built prompt.
Model: llama-3.3-70b-versatile (Mixtral is decommissioned)
temperature=0.0 ensures deterministic output.
"""

from groq import Groq


def get_client() -> Groq:
    # Paste your Groq API key here
    api_key = "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"
    client = Groq(api_key=api_key)
    client.api_key = api_key   # expose for semantic_interpreter
    return client


def generate_sql(prompt: str) -> str:
    """
    Sends prompt to Groq LLaMA and returns clean SQL string.
    Args:
        prompt: fully built prompt from prompt_builder
    Returns:
        SQL query string
    """
    client = get_client()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",   # Mixtral is decommissioned — use LLaMA
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a PostgreSQL SQL expert for an e-commerce platform. "
                    "Output ONLY valid SQL — no explanations, no markdown, "
                    "no code fences, no preamble. Just the raw SQL query."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0,    # Deterministic — no creativity needed
        max_tokens=1024,
    )

    raw_output = response.choices[0].message.content.strip()

    # Strip markdown fences if model accidentally adds them
    if raw_output.startswith("```"):
        lines = raw_output.split("\n")
        raw_output = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    return raw_output
