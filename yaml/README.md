# NL → SQL Analytics System

Production-grade Natural Language to SQL pipeline using Groq (Mixtral-8x7B) + YAML business logic.

---

## Project Structure

```
nl2sql/
├── yaml/
│   ├── metric_glossary.yaml         # Business metric definitions
│   ├── join_path_specification.yaml # Strict join rules
│   ├── sql_generation_standards.yaml# SQL output rules
│   └── time_filter_governance.yaml  # Time filter logic
│
├── core/
│   ├── context_selector.py          # Extracts relevant YAML context per query
│   ├── prompt_builder.py            # Builds structured LLM prompt
│   ├── sql_generator.py             # Calls Groq API
│   └── validator.py                 # Validates SQL before execution
│
├── main.py                          # Entry point
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Groq API key
Get your free key at: https://console.groq.com
```bash
export GROQ_API_KEY=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
```

---

## Run

### Single query
```bash
python main.py --query "Why are we facing losses this month?"
```

### Interactive REPL
```bash
python main.py --interactive
```

### Run all sample queries (demo)
```bash
python main.py --demo
```

### Default (runs first sample query)
```bash
python main.py
```

---

## How It Works

```
User Question
     ↓
context_selector.py   → reads YAMLs, extracts only what's relevant
     ↓
prompt_builder.py     → builds a tight, structured prompt
     ↓
Groq API (Mixtral)    → generates SQL (temperature=0.0)
     ↓
validator.py          → checks join rules, safety, business logic
     ↓
Clean SQL Output
```

---

## Example Queries

- "Why are we facing losses this month?"
- "What is our revenue by product category this month?"
- "Which sellers have the highest refund amount this month?"
- "Show me total orders and cancellations for the last 30 days"
- "What is the average order value by customer segment this month?"
- "Which products have the highest return rate last 90 days?"
- "Show seller settlement summary for this month"

---

## Adding New Metrics

Edit `yaml/metric_glossary.yaml`:

```yaml
your_metric:
  description: "What it measures"
  tables: [orders, order_items]
  formula_logic:
    join: "orders.order_id = order_items.order_id"
    filter: "orders.order_status = 'Delivered'"
    aggregation: "SUM(order_items.item_price)"
  type: financial
  aliases: ["keyword1", "keyword2"]   # ← keywords that trigger this metric
```

---

## Extending to Full Analytics

Next steps:

1. Add a FastAPI layer → REST API
2. Create frontend
