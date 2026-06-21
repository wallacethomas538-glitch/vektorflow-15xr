"""
VektorFlow 15xr - Inventory Monitoring
Monitors stock levels across all connected stores and generates alerts.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from database import (
    get_user_stores,
    save_memory,
    get_memory,
    add_task_history,
    update_task_result,
    get_user_preferences
)
from store_manager import StoreManager

logger = logging.getLogger("vektorflow")

# ============ CONFIGURATION ============
DEFAULT_LOW_STOCK_THRESHOLD = 10
DEFAULT_OVERSTOCK_THRESHOLD = 500
DEFAULT_ALERT_COOLDOWN_HOURS = 24

# ============ INVENTORY MONITOR ============

class InventoryMonitor:
    """
    Monitors inventory across all connected stores.
    Generates alerts for low stock, out of stock, and overstock.
    """
    
    def __init__(self, email: str):
        """
        Initialize the inventory monitor for a user.
        
        Args:
            email: User email
        """
        self.email = email
        self.store_manager = StoreManager(email)
        self.low_threshold = DEFAULT_LOW_STOCK_THRESHOLD
        self.overstock_threshold = DEFAULT_OVERSTOCK_THRESHOLD
        self.alert_cooldown = DEFAULT_ALERT_COOLDOWN_HOURS
        self._load_preferences()
    
    def _load_preferences(self):
        """Load user preferences for thresholds."""
        try:
            prefs = get_user_preferences(self.email) or {}
            self.low_threshold = prefs.get("low_stock_threshold", DEFAULT_LOW_STOCK_THRESHOLD)
            self.overstock_threshold = prefs.get("overstock_threshold", DEFAULT_OVERSTOCK_THRESHOLD)
            self.alert_cooldown = prefs.get("alert_cooldown_hours", DEFAULT_ALERT_COOLDOWN_HOURS)
        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")
    
    async def check_all_stores(self) -> Dict[str, Any]:
        """
        Check inventory across all connected stores.
        
        Returns:
            Dict with inventory data and alerts
        """
        try:
            # Get inventory from all stores
            inventory_result = await self.store_manager.get_inventory()
            if not inventory_result.get("success"):
                return {
                    "success": False,
                    "error": inventory_result.get("error", "Failed to get inventory")
                }
            
            inventory = inventory_result.get("inventory", {})
            
            # Check each store for alerts
            all_alerts = []
            for platform, items in inventory.items():
                alerts = self._check_items(items, platform)
                all_alerts.extend(alerts)
            
            # Save alerts to memory
            if all_alerts:
                await self._save_alerts(all_alerts)
            
            # Add task to history
            task_id = add_task_history(
                email=self.email,
                agent_name="inventory_monitor",
                task=f"Checked inventory across {len(inventory)} stores",
                status="completed" if not all_alerts else "pending"
            )
            update_task_result(
                task_id=task_id,
                result=json.dumps({
                    "stores": list(inventory.keys()),
                    "alerts": len(all_alerts),
                    "timestamp": datetime.utcnow().isoformat()
                }),
                status="completed"
            )
            
            return {
                "success": True,
                "inventory": inventory,
                "alerts": all_alerts,
                "alert_count": len(all_alerts),
                "task_id": task_id
            }
            
        except Exception as e:
            logger.error(f"Inventory check failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _check_items(self, items: List[Dict], platform: str) -> List[Dict]:
        """
        Check a list of items for inventory alerts.
        
        Args:
            items: List of inventory items
            platform: Platform name
        
        Returns:
            List of alerts
        """
        alerts = []
        
        for item in items:
            quantity = item.get("quantity", 0)
            product_title = item.get("title", "Unknown Product")
            sku = item.get("sku", "N/A")
            product_id = item.get("product_id") or item.get("id", "N/A")
            
            # Check for low stock
            if 0 < quantity <= self.low_threshold:
                alerts.append({
                    "type": "low_stock",
                    "severity": "warning",
                    "platform": platform,
                    "product": product_title,
                    "sku": sku,
                    "product_id": product_id,
                    "quantity": quantity,
                    "threshold": self.low_threshold,
                    "message": f"Low stock: {product_title} has only {quantity} units left."
                })
            
            # Check for out of stock
            elif quantity == 0:
                alerts.append({
                    "type": "out_of_stock",
                    "severity": "critical",
                    "platform": platform,
                    "product": product_title,
                    "sku": sku,
                    "product_id": product_id,
                    "quantity": 0,
                    "threshold": 0,
                    "message": f"OUT OF STOCK: {product_title} is completely sold out."
                })
            
            # Check for overstock
            elif quantity >= self.overstock_threshold:
                alerts.append({
                    "type": "overstock",
                    "severity": "info",
                    "platform": platform,
                    "product": product_title,
                    "sku": sku,
                    "product_id": product_id,
                    "quantity": quantity,
                    "threshold": self.overstock_threshold,
                    "message": f"Overstock: {product_title} has {quantity} units in stock. Consider running a promotion."
                })
        
        return alerts
    
    async def _save_alerts(self, alerts: List[Dict]):
        """
        Save alerts to memory and send notifications.
        
        Args:
            alerts: List of alerts
        """
        # Save to memory
        memory_key = f"inventory_alerts_{datetime.utcnow().strftime('%Y%m%d')}"
        existing_alerts = get_memory(self.email, memory_key)
        if existing_alerts:
            try:
                existing = json.loads(existing_alerts)
                alerts = existing + alerts
            except:
                pass
        
        save_memory(self.email, memory_key, json.dumps(alerts))
        
        # Log each alert
        for alert in alerts:
            logger.info(f"Inventory Alert [{alert['severity']}]: {alert['message']}")
    
    async def get_alert_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current inventory alerts.
        
        Returns:
            Dict with alert summary
        """
        try:
            # Check all stores
            result = await self.check_all_stores()
            if not result.get("success"):
                return {"success": False, "error": result.get("error")}
            
            alerts = result.get("alerts", [])
            
            # Count by type
            counts = {}
            severity_counts = {}
            for alert in alerts:
                alert_type = alert.get("type", "unknown")
                counts[alert_type] = counts.get(alert_type, 0) + 1
                severity = alert.get("severity", "info")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            return {
                "success": True,
                "total_alerts": len(alerts),
                "by_type": counts,
                "by_severity": severity_counts,
                "alerts": alerts
            }
            
        except Exception as e:
            logger.error(f"Alert summary failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_reorder_recommendations(self) -> Dict[str, Any]:
        """
        Generate reorder recommendations for low stock items.
        
        Returns:
            Dict with reorder suggestions
        """
        try:
            # Check all stores
            result = await self.check_all_stores()
            if not result.get("success"):
                return {"success": False, "error": result.get("error")}
            
            inventory = result.get("inventory", {})
            
            recommendations = {}
            for platform, items in inventory.items():
                low_items = [
                    item for item in items
                    if item.get("quantity", 0) <= self.low_threshold and item.get("quantity", 0) > 0
                ]
                
                if low_items:
                    # Calculate reorder quantities
                    reorders = []
                    for item in low_items:
                        current_qty = item.get("quantity", 0)
                        # Reorder to reach 3x threshold
                        reorder_qty = max((self.low_threshold * 3) - current_qty, self.low_threshold)
                        reorders.append({
                            "product": item.get("title", "Unknown"),
                            "sku": item.get("sku", "N/A"),
                            "current_quantity": current_qty,
                            "recommended_reorder": reorder_qty,
                            "supplier": item.get("supplier", "Unknown")
                        })
                    recommendations[platform] = reorders
            
            # Save to memory
            save_memory(
                self.email,
                f"reorder_recommendations_{datetime.utcnow().strftime('%Y%m%d')}",
                json.dumps(recommendations)
            )
            
            return {
                "success": True,
                "recommendations": recommendations
            }
            
        except Exception as e:
            logger.error(f"Reorder recommendations failed: {e}")
            return {"success": False, "error": str(e)}

# ============ CONVENIENCE FUNCTIONS ============

async def check_inventory(email: str) -> Dict[str, Any]:
    """
    Convenience function to check inventory for a user.
    
    Args:
        email: User email
    
    Returns:
        Inventory check result
    """
    monitor = InventoryMonitor(email)
    return await monitor.check_all_stores()

async def get_inventory_alerts(email: str) -> Dict[str, Any]:
    """
    Convenience function to get inventory alerts for a user.
    
    Args:
        email: User email
    
    Returns:
        Alert summary
    """
    monitor = InventoryMonitor(email)
    return await monitor.get_alert_summary()

async def get_reorder_recommendations(email: str) -> Dict[str, Any]:
    """
    Convenience function to get reorder recommendations.
    
    Args:
        email: User email
    
    Returns:
        Reorder recommendations
    """
    monitor = InventoryMonitor(email)
    return await monitor.generate_reorder_recommendations()

# ============ COMPATIBILITY WITH VEKTOR_AGENT ============

async def handle_inventory_check(email: str, message: str, user_keys: Dict) -> Dict[str, Any]:
    """
    Handle inventory check requests from vektor_agent.py.
    
    Args:
        email: User email
        message: User instruction
        user_keys: User's API keys
    
    Returns:
        Formatted response for vektor_agent
    """
    try:
        # Extract platform if specified
        platform = None
        for p in ["shopify", "woocommerce", "cj"]:
            if p in message.lower():
                platform = p
                break
        
        monitor = InventoryMonitor(email)
        
        # Check inventory
        result = await monitor.check_all_stores()
        if not result.get("success"):
            return {
                "success": False,
                "response": f"Failed to check inventory: {result.get('error', 'Unknown error')}",
                "action": "error"
            }
        
        inventory = result.get("inventory", {})
        alerts = result.get("alerts", [])
        
        # Filter by platform if specified
        if platform:
            inventory = {platform: inventory.get(platform, [])}
            alerts = [a for a in alerts if a.get("platform") == platform]
        
        # Build response
        total_items = sum(len(items) for items in inventory.values())
        response = f"📦 Inventory Check Complete\n\n"
        response += f"Total items: {total_items}\n"
        response += f"Alerts: {len(alerts)}\n\n"
        
        if alerts:
            response += "⚠️ Alerts:\n"
            for alert in alerts[:5]:  # Show first 5 alerts
                response += f"  • {alert.get('message')}\n"
            if len(alerts) > 5:
                response += f"  ... and {len(alerts) - 5} more\n"
        else:
            response += "✅ All inventory levels are healthy.\n"
        
        return {
            "success": True,
            "response": response,
            "data": {
                "inventory": inventory,
                "alerts": alerts,
                "alert_count": len(alerts),
                "platform": platform or "all"
            },
            "action": "display_inventory"
        }
        
    except Exception as e:
        logger.error(f"Inventory check handler error: {e}")
        return {
            "success": False,
            "response": f"Failed to check inventory: {str(e)}",
            "action": "error"
        }

# ============ INITIALIZATION ============

print("✅ Inventory Monitor module loaded successfully")
print("   Features: multi-store monitoring, alerts, reorder recommendations")