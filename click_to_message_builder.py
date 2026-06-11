from typing import Dict, Optional

class ClickToMessageBuilder:
    def generate_sequence(self, product: Dict, trend: Optional[str] = None) -> Dict:
        product_name = product.get("name", "this product")
        price = product.get("price", "check price")
        
        msg1 = f"🔥 {product_name} is trending! Want the link?" if trend else f"👋 Got a question about {product_name}?"
        msg2 = f"✨ {product.get('rating', '4.5')}⭐ from {product.get('review_count', 'hundreds')}+ customers"
        msg3 = f"⏳ Only a few left at ${price}. Link when ready: [LINK]"
        
        return {
            "platforms": ["WhatsApp", "Instagram DM"],
            "sequence": [
                {"order": 1, "delay_minutes": 0, "message": msg1},
                {"order": 2, "delay_minutes": 2, "message": msg2},
                {"order": 3, "delay_minutes": 60, "message": msg3}
            ]
        }
    
    def generate_ad_copy(self, product: Dict, trend: Optional[str] = None) -> Dict:
        return {
            "headline": f"Everyone's talking about {trend or product.get('name')}",
            "description": f"DM us 'INFO' for the link",
            "cta_button": "Send Message"
        }
