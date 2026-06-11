import json
from typing import Dict, List

class AICitationOptimizer:
    def __init__(self):
        pass
    
    def calculate_citation_score(self, product: Dict) -> Dict:
        score = 0
        reasons = []
        
        description = product.get("description", "").lower()
        claim_keywords = ["waterproof", "battery", "weight", "dimensions", "material", "guarantee"]
        claims_found = [kw for kw in claim_keywords if kw in description]
        score += len(claims_found) * 10
        
        reviews = product.get("review_count", 0)
        if reviews > 100:
            score += 30
            reasons.append(f"Strong signal: {reviews} reviews")
        elif reviews > 20:
            score += 15
        
        rating = product.get("rating", 0)
        if rating >= 4.5:
            score += 20
        
        score = min(score, 100)
        
        return {
            "score": score,
            "grade": "A" if score >= 80 else "B" if score >= 60 else "C",
            "recommendations": [
                "Add schema.org Product markup",
                "Get 20+ customer reviews",
                "List specific product dimensions/features"
            ]
        }
