import stripe
import os
from fastapi import APIRouter, HTTPException, Request
from database import get_db, get_user

router = APIRouter(prefix="/payment", tags=["payment"])

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

@router.post("/create-checkout")
def create_checkout(email: str, success_url: str, cancel_url: str):
    if not stripe.api_key:
        raise HTTPException(400, "Stripe not configured")
    
    user = get_user(email)
    if not user:
        raise HTTPException(404, "User not found")
    
    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=email,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "VektorFlow 15xr Pro"},
                    "unit_amount": 4900,  # $49.00
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"email": email}
        )
        return {"checkout_url": checkout_session.url}
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/webhook")
async def webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except:
        raise HTTPException(400, "Invalid webhook")
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session["metadata"]["email"]
        
        # Upgrade user to paid tier
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tier = 'pro', trial_expires = datetime('now', '+365 days') WHERE email = ?", (email,))
        conn.commit()
        conn.close()
    
    return {"status": "success"}
