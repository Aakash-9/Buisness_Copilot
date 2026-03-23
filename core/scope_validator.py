"""
scope_validator.py

Checks if a user query is asking about something that exists in the dataset.
Runs BEFORE SQL generation.

If the query asks about:
  - A product category not in the dataset (e.g. electronics, door mats)
  - A metric not available (e.g. profit margin, employee data)
  - A brand/sub-category not in the data

→ Returns a helpful "not in dataset" message instead of generating wrong SQL.
"""

import yaml
import os
import re

YAML_DIR = os.path.join(os.path.dirname(__file__), '..', 'yaml')


def _load_scope() -> dict:
    path = os.path.join(YAML_DIR, 'dataset_scope.yaml')
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
# WHAT THE DATASET ACTUALLY CONTAINS
# ─────────────────────────────────────────────

# All valid product categories (exact match from DB)
VALID_CATEGORIES = {
    'topwear', 'bottomwear', 'footwear', 'accessories', 'dresses',
}

VALID_SUB_CATEGORIES = {
    'kurtas', 'sweatshirts', 'shirts', 't-shirts', 'tshirts',
    'shorts', 'jeans', 'trousers',
    'sports shoes', 'casual shoes', 'formal shoes', 'sandals',
    'belts', 'watches', 'bags', 'sunglasses',
    'bodycon dress', 'maxi dress', 'casual dress',
}

VALID_BRANDS = {
    'libas', 'allen solly', 'w', 'h&m', 'roadster', 'adidas', 'zara',
    'peter england', 'levi\'s', 'levis', 'biba', 'nike', 'puma',
    'here&now', 'titan',
}

# Things users commonly ask about that are NOT in dataset
NOT_IN_DATASET = {
    # Wrong product categories
    'electronics', 'electronic', 'mobile', 'phone', 'laptop', 'tablet',
    'computer', 'headphone', 'camera', 'tv', 'television',
    'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress',
    'home decor', 'door mat', 'doormat', 'carpet', 'curtain', 'pillow',
    'kitchen', 'utensil', 'cookware', 'appliance', 'refrigerator',
    'washing machine', 'microwave', 'mixer', 'grinder',
    'grocery', 'groceries', 'food', 'vegetable', 'fruit',
    'book', 'stationery', 'notebook',
    'toy', 'game', 'puzzle', 'sports equipment', 'cycle', 'cricket bat',
    'beauty', 'cosmetic', 'makeup', 'skincare', 'shampoo',
    'health', 'medicine', 'vitamin', 'supplement',
    'automotive', 'car', 'bike', 'vehicle',
    'garden', 'plant', 'seed', 'pot',
    'pet', 'dog food', 'cat food',
    # Metrics not in dataset
    'profit margin', 'margin', 'cost price', 'vendor cost', 'cogs',
    'employee', 'salary', 'hr', 'tax', 'gst', 'invoice',
    'market share', 'competitor', 'benchmark',
    'customer lifetime value', 'clv', 'ltv',
    'shipping cost', 'logistics cost',
    'social media', 'instagram', 'facebook', 'ads', 'marketing spend',
}


def validate_scope(query: str) -> dict:
    """
    Check if query is about something that exists in the dataset.

    Returns:
        {
          'in_scope': True/False,
          'reason': explanation if out of scope,
          'suggestion': what they can ask instead
        }
    """
    q = query.lower().strip()

    # Check for things explicitly not in dataset
    for term in NOT_IN_DATASET:
        if term in q:
            return _build_out_of_scope_response(term, q)

    # Check if asking about a specific category — validate it exists
    scope = _load_scope()
    valid_cats = [c.lower() for c in scope.get('product_categories', {}).keys()]

    # Extract what category they're asking about
    category_patterns = [
        r'revenue (?:through|from|for|of|via|in)\s+(\w[\w\s]+?)(?:\s+this|\s+last|\s+month|\s+year|$)',
        r'sales (?:of|for|in|through)\s+(\w[\w\s]+?)(?:\s+this|\s+last|\s+month|$)',
        r'orders (?:for|of|in)\s+(\w[\w\s]+?)(?:\s+this|\s+last|\s+month|$)',
        r'(\w[\w\s]+?) (?:category|products) (?:revenue|sales|orders)',
    ]

    for pattern in category_patterns:
        match = re.search(pattern, q)
        if match:
            asked_cat = match.group(1).strip().lower()
            # Check if it's a known invalid category
            for term in NOT_IN_DATASET:
                if term in asked_cat or asked_cat in term:
                    return _build_out_of_scope_response(asked_cat, q)

    return {'in_scope': True, 'reason': None, 'suggestion': None}


def _build_out_of_scope_response(term: str, query: str) -> dict:
    """Build a helpful out-of-scope response."""

    scope = _load_scope()
    valid_cats = list(scope.get('product_categories', {}).keys())
    valid_brands = []
    for cat_data in scope.get('product_categories', {}).values():
        valid_brands.extend(cat_data.get('brands', []))

    # Identify what type of thing they asked about
    product_terms = {
        'electronics', 'mobile', 'phone', 'laptop', 'tablet', 'computer',
        'furniture', 'sofa', 'home decor', 'door mat', 'doormat', 'carpet',
        'kitchen', 'appliance', 'grocery', 'book', 'toy', 'beauty', 'health',
        'automotive', 'garden', 'pet',
    }
    metric_terms = {
        'profit margin', 'margin', 'cost price', 'employee', 'salary',
        'tax', 'market share', 'competitor', 'shipping cost', 'social media',
    }

    if any(t in term for t in metric_terms):
        reason = f"'{term}' is not tracked in this dataset. No cost price, employee, tax, or marketing data is available."
        suggestion = f"Available financial metrics: revenue, GMV, refunds, settlements, discounts, losses (from cancellations/returns)"
    else:
        reason = f"'{term}' is not a product category in this dataset."
        suggestion = (
            f"This is a fashion e-commerce dataset. Available categories: "
            f"{', '.join(valid_cats)}.\n"
            f"  Available brands: {', '.join(sorted(set(valid_brands))[:10])}...\n"
            f"  Sub-categories include: Kurtas, T-Shirts, Jeans, Shorts, Sports Shoes, "
            f"Belts, Watches, Bags, Sunglasses, Bodycon Dress etc."
        )

    return {
        'in_scope': False,
        'reason': reason,
        'suggestion': suggestion,
    }


def get_dataset_summary() -> str:
    """Returns a human-readable summary of what's in the dataset."""
    return """
This is a FASHION E-COMMERCE dataset (similar to Myntra/Ajio).

PRODUCT CATEGORIES:
  • Topwear      → Kurtas, Sweatshirts, Shirts, T-Shirts
  • Bottomwear   → Shorts, Jeans, Trousers
  • Footwear     → Sports Shoes, Casual Shoes, Formal Shoes, Sandals
  • Accessories  → Belts, Watches, Bags, Sunglasses
  • Dresses      → Bodycon Dress, Maxi Dress, Casual Dress

BRANDS: Libas, Allen Solly, W, H&M, Roadster, Adidas, Zara, Levi's,
        Peter England, Biba, Nike, Puma, HERE&NOW, Titan + more

CUSTOMERS: Cities across India (Mumbai, Delhi, Bangalore, Hyderabad...)
           Age groups: 18-24, 25-34, 35-44, 45-54, 55+
           Loyalty tiers: Bronze, Silver, Gold, Platinum

SELLERS: Individual, Authorized Reseller, Brand Official
         Regions: North, South, East, West, Pan-India

PAYMENTS: COD, Credit Card, UPI, Wallet, Net Banking
          Gateways: PhonePe, PayU, Stripe, Razorpay, Paytm, COD

DELIVERY: BlueDart, Delhivery, Shadowfax, Ecom Express, DTDC

NOT IN DATASET: Electronics, Furniture, Home Decor, Groceries, Books,
                Toys, Beauty, Healthcare, Automotive, Door Mats,
                Profit margins, Employee data, Tax data, Marketing spend
"""
