"""
Payment integration for subscription management
"""

import stripe
import os
from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime
from database import get_subscription, update_subscription, cancel_subscription
from auth import get_current_user

router = APIRouter(prefix="/payment", tags=["payment"])

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

PLANS = {
    "starter": {"price_id": "price_starter_monthly", "amount": 49, "interval": "month"},
    "pro": {"price_id": "price_pro_monthly", "amount": 149, "interval": "month"},
    "enterprise": {"price_id": "price_enterprise_monthly", "amount": 499, "interval": "month"}
}

@router.post("/create-checkout")
async def create_checkout(plan: str, email: str = Depends(get_current_user)):
    if plan not in PLANS:
        raise HTTPException(400, "Invalid plan")
    
    if not stripe.api_key:
        raise HTTPException(400, "Stripe not configured")
    
    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=email,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"VektorFlow 15xr - {plan.title()} Plan"},
                    "unit_amount": PLANS[plan]["amount"] * 100,
                    "recurring": {"interval": PLANS[plan]["interval"]}
                },
                "quantity": 1
            }],
            mode="subscription",
            success_url=f"{os.environ.get('APP_URL', 'https://vektorflow-15xr.onrender.com')}/dashboard?success=true",
            cancel_url=f"{os.environ.get('APP_URL', 'https://vektorflow-15xr.onrender.com')}/dashboard?canceled=true",
            metadata={"email": email, "plan": plan}
        )
        return {"checkout_url": checkout_session.url}
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    
    if not webhook_secret or not stripe.api_key:
        return {"status": "webhook not configured"}
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        raise HTTPException(400, "Invalid webhook")
    
    if event["type"] == "customer.subscription.created" or event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        customer_email = subscription.get("customer_email")
        if customer_email:
            update_subscription(
                email=customer_email,
                stripe_subscription_id=subscription["id"],
                plan=subscription["items"]["data"][0]["price"]["nickname"] if subscription["items"]["data"] else "pro",
                current_period_end=datetime.fromtimestamp(subscription["current_period_end"])
            )
    
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_email = subscription.get("customer_email")
        if customer_email:
            cancel_subscription(customer_email)
    
    return {"status": "ok"}
