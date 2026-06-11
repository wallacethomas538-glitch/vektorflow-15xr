import csv
from typing import Dict, List
from io import StringIO

class SocialCommerceConnector:
    def generate_tiktok_shop_csv(self, products: List[Dict]) -> str:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Product ID", "Product Name", "Price", "Stock"])
        for p in products:
            writer.writerow([p.get("sku", ""), p.get("name", ""), p.get("price", ""), p.get("stock", 100)])
        return output.getvalue()
    
    def generate_instagram_product_tags(self, products: List[Dict]) -> Dict:
        return {
            "setup_instructions": ["Connect Facebook catalog to Instagram Shopping (free)"],
            "product_list": [{"name": p.get("name")} for p in products[:5]]
        }
