"""Agent event handlers."""

import logging
from src.event_bus import get_event_bus

logger = logging.getLogger(__name__)
event_bus = get_event_bus()


async def product_sourcing_handler(event: Dict) -> None:
    data = event.get("data", {})
    product = data.get("product", "Unknown")
    logger.info(f"Product Sourcing Scout: Processing {product}")


async def ad_specialist_handler(event: Dict) -> None:
    data = event.get("data", {})
    product = data.get("product", "Unknown")
    logger.info(f"Ad Specialist: Creating ad for {product}")


async def initialize_agent_listeners():
    event_bus.subscribe("trend_detected", product_sourcing_handler)
    event_bus.subscribe("trend_detected", ad_specialist_handler)
    logger.info("Agent listeners initialized")