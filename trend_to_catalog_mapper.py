import json
import requests
from typing import List, Dict, Any
from memory_fabric import MemoryFabric

class TrendToCatalogMapper:
    def __init__(self, product_catalog: List[Dict] = None):
        self.memory = MemoryFabric()
        self.catalog = product_catalog or []
    
    def fetch_trends_free(self) -> List[Dict]:
        trends = []
        try:
            rss_url = "https://ecomhunt.com/feed"
            response = requests.get(rss_url, timeout=10)
            import re
            products = re.findall(r'<title>(.*?)</title>', response.text)
            for p in products[1:6]:
                trends.append({"source": "ecomhunt", "product": p, "confidence": 0.7})
        except:
            pass
        
        trending_categories = ["wireless earbuds", "fitness trackers", "home office", "pet accessories", "skincare tools"]
        for cat in trending_categories:
            trends.append({"source": "category_trend", "product": cat, "confidence": 0.5})
        
        return trends
    
    def match_to_catalog(self, trend: str) -> List[Dict]:
        if not self.catalog:
            return []
        matches = []
        trend_words = trend.lower().split()
        for product in self.catalog:
            product_name = product.get("name", "").lower()
            score = sum(3 for word in trend_words if word in product_name)
            if score > 0:
                matches.append({"product": product, "match_score": score, "trend_keyword": trend})
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches[:3]
    
    def run_weekly(self) -> Dict:
        trends = self.fetch_trends_free()
        results = []
        for trend_item in trends:
            trend_name = trend_item.get("product", "")
            matches = self.match_to_catalog(trend_name)
            for match in matches:
                results.append({
                    "trend": trend_name,
                    "product": match["product"].get("name"),
                    "match_score": match["match_score"],
                    "campaign_angle": f"🔥 {match['product'].get('name')} is blowing up with '{trend_name}' - shop now!"
                })
        return {"status": "success", "matches": results, "count": len(results)}
    
    def close(self):
        self.memory.close()
