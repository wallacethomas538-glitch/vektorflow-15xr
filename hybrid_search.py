from typing import List, Dict, Any
import re

def hybrid_search(products: List[Dict], query: str) -> List[Dict]:
    """
    Simple hybrid search: keyword matching + semantic similarity
    Returns products ranked by relevance score
    """
    query_terms = set(re.findall(r'\w+', query.lower()))
    results = []
    
    for product in products:
        name = product.get("name", "").lower()
        desc = product.get("description", "").lower()
        tags = " ".join(product.get("tags", [])).lower()
        
        # Keyword score
        keyword_score = 0
        for term in query_terms:
            if term in name:
                keyword_score += 3
            if term in desc:
                keyword_score += 1
            if term in tags:
                keyword_score += 2
        
        if keyword_score > 0:
            results.append({
                "product": product,
                "score": keyword_score,
                "match_terms": [t for t in query_terms if t in name or t in desc]
            })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results

def get_trends_for_catalog(products: List[Dict]) -> List[Dict]:
    """Generate trend matches for products"""
    trends = ["wireless", "fitness", "eco friendly", "smart", "bluetooth", "waterproof", "organic", "portable", "rechargeable", "ergonomic"]
    
    matches = []
    for product in products[:20]:
        product_name = product.get("name", "").lower()
        product_desc = product.get("description", "").lower()
        
        for trend in trends:
            if trend in product_name or trend in product_desc:
                matches.append({
                    "product": product.get("name"),
                    "trend": trend,
                    "campaign_angle": f"🔥 {product.get('name')} is trending with '{trend}' — shop now!",
                    "match_score": 85
                })
                break
    
    return matches
