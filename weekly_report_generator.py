from datetime import datetime
from trend_to_catalog_mapper import TrendToCatalogMapper
from click_to_message_builder import ClickToMessageBuilder
from typing import List, Dict

class WeeklyReportGenerator:
    def __init__(self, product_catalog: List[Dict]):
        self.trend_mapper = TrendToCatalogMapper(product_catalog)
        self.message_builder = ClickToMessageBuilder()
        self.catalog = product_catalog
    
    def generate_full_report(self) -> str:
        trend_results = self.trend_mapper.run_weekly()
        report = []
        report.append("# 📊 VektorFlow 15xr - Weekly Report")
        report.append(f"**Generated:** {datetime.now().strftime('%B %d, %Y')}")
        report.append("")
        report.append("## 🔥 Trending Products Matched to You")
        for match in trend_results.get("matches", [])[:3]:
            report.append(f"- {match['product']} → {match['campaign_angle']}")
        
        if self.catalog:
            campaign = self.message_builder.generate_sequence(self.catalog[0], "trending")
            report.append("")
            report.append("## 📱 Ready-to-Use DM Sequence")
            for msg in campaign["sequence"]:
                report.append(f"**Message {msg['order']}:** {msg['message']}")
        
        return "\n".join(report)
    
    def close(self):
        self.trend_mapper.close()
