"""Pydantic schemas."""

from datetime import datetime
from typing import Optional, Any, List, Dict
from pydantic import BaseModel, Field


class FinancialMetrics(BaseModel):
    total_revenue: float = 0.0
    platform_commission: float = 0.0
    ad_spend: float = 0.0
    logistics_cost: float = 0.0
    net_profit: float = 0.0
    roi_percentage: float = 0.0
    reporting_date: datetime = Field(default_factory=datetime.utcnow)


class InventorySnapshot(BaseModel):
    sku: str = ""
    quantity_available: int = 0
    quantity_reserved: int = 0
    quantity_sellable: int = 0
    reorder_threshold: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    google_merchant_synced: bool = False


class ProductOpportunity(BaseModel):
    product_name: str = ""
    trend_score: float = 0.0
    viral_velocity: float = 0.0
    estimated_demand: int = 0
    margin_target: float = 0.0
    sourcing_vendors: List[str] = []
    recommended_sku: Optional[str] = None
    discovery_timestamp: datetime = Field(default_factory=datetime.utcnow)


class CreativeAsset(BaseModel):
    ad_hook: str = ""
    retention_copyline: str = ""
    visual_prompt: str = ""
    cta_overlay: str = ""
    target_duration_seconds: int = 15
    platform: str = "tiktok"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TikTokWebhookPayload(BaseModel):
    order_id: str = ""
    customer_id: str = ""
    order_amount: float = 0.0
    currency: str = "USD"
    items: List[Dict[str, Any]] = []
    created_time: datetime = Field(default_factory=datetime.utcnow)
    event_timestamp: datetime = Field(default_factory=datetime.utcnow)