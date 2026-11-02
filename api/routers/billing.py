"""
Clipedics – Stripe Billing Router

Plans:
  free    → 5 clips/month  — $0
  pro     → 200 clips/month — $19/month
  agency  → Unlimited       — $79/month

Endpoints:
  GET  /api/billing/plans              → list plan features
  POST /api/billing/checkout/{plan}    → create Stripe Checkout session
  POST /api/billing/portal             → Stripe customer portal (manage/cancel)
  POST /api/billing/webhook            → Stripe webhook handler
  GET  /api/billing/status             → current user plan + usage
"""
from __future__ import annotations
import os
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.database import get_session
from api.db_models import User
from api.auth import require_user

router = APIRouter()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Stripe Price IDs (set in .env after creating products in Stripe dashboard)
PRICE_IDS = {
    "pro":    os.getenv("STRIPE_PRICE_PRO", "price_pro_placeholder"),
    "agency": os.getenv("STRIPE_PRICE_AGENCY", "price_agency_placeholder"),
}

PLAN_FEATURES = {
    "free": {
        "name": "Free",
        "price_usd": 0,
        "clips_per_month": 5,
        "max_video_minutes": 30,
        "features": ["5 clips/month", "720p output", "All caption styles", "Download MP4"],
    },
    "pro": {
        "name": "Pro",
        "price_usd": 19,
        "clips_per_month": 200,
        "max_video_minutes": 120,
        "features": ["200 clips/month", "1080p output", "All caption styles", "Priority processing", "Batch export", "Social publish"],
    },
    "agency": {
        "name": "Agency",
        "price_usd": 79,
        "clips_per_month": -1,  # unlimited
        "max_video_minutes": 999,
        "features": ["Unlimited clips", "4K output", "White-label export", "API access", "Priority queue", "Dedicated support"],
    },
}


@router.get("/plans")
async def list_plans():
    """Return all plan features (public endpoint)."""
    return PLAN_FEATURES


@router.get("/status")
async def billing_status(
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    """Return current user's plan, quota used, and limits."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    limit = PLAN_FEATURES.get(user.plan, PLAN_FEATURES["free"])["clips_per_month"]
    return {
        "plan": user.plan,
        "subscription_status": user.subscription_status,
        "clips_used_this_month": user.clips_used_this_month,
        "clips_limit": limit,
        "clips_remaining": max(0, limit - user.clips_used_this_month) if limit != -1 else -1,
        "quota_reset_at": user.quota_reset_at.isoformat() if user.quota_reset_at else None,
    }


@router.post("/checkout/{plan}")
async def create_checkout(
    plan: str,
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    """Create a Stripe Checkout session for upgrading to pro/agency."""
    if plan not in PRICE_IDS:
        raise HTTPException(400, f"Unknown plan: {plan}. Choose pro or agency.")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe not configured. Set STRIPE_SECRET_KEY in .env")

    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Create or reuse Stripe customer
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": user_id},
        )
        user.stripe_customer_id = customer.id
        await db.commit()

    session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": PRICE_IDS[plan], "quantity": 1}],
        success_url=f"{FRONTEND_URL}/settings?upgraded=1",
        cancel_url=f"{FRONTEND_URL}/pricing",
        metadata={"user_id": user_id, "plan": plan},
    )
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/portal")
async def customer_portal(
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    """Open Stripe Customer Portal to manage/cancel subscription."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe not configured")

    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    user = await db.get(User, user_id)
    if not user or not user.stripe_customer_id:
        raise HTTPException(400, "No Stripe customer linked. Subscribe first.")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{FRONTEND_URL}/settings",
    )
    return {"portal_url": session.url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_session),
):
    """
    Handle Stripe webhook events:
    - checkout.session.completed  → activate subscription
    - customer.subscription.updated → sync plan changes
    - customer.subscription.deleted → downgrade to free
    - invoice.payment_failed       → mark past_due
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook secret not configured")

    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid webhook signature")

    await _handle_stripe_event(event, db)
    return {"received": True}


# ── Webhook event handlers ────────────────────────────────────────────────────

async def _handle_stripe_event(event: dict, db: AsyncSession) -> None:
    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        user_id = data.get("metadata", {}).get("user_id")
        plan = data.get("metadata", {}).get("plan", "pro")
        sub_id = data.get("subscription")
        if user_id:
            user = await db.get(User, user_id)
            if user:
                user.plan = plan
                user.stripe_subscription_id = sub_id
                user.subscription_status = "active"
                await db.commit()

    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub_id = data.get("id")
        status = data.get("status", "canceled")

        result = await db.execute(
            select(User).where(User.stripe_subscription_id == sub_id)
        )
        user = result.scalar_one_or_none()
        if user:
            if status == "canceled" or etype == "customer.subscription.deleted":
                user.plan = "free"
                user.subscription_status = "inactive"
            else:
                user.subscription_status = status
                # Sync plan from price metadata if available
                items = data.get("items", {}).get("data", [])
                if items:
                    price_id = items[0].get("price", {}).get("id", "")
                    for plan_name, pid in PRICE_IDS.items():
                        if pid == price_id:
                            user.plan = plan_name
                            break
            await db.commit()

    elif etype == "invoice.payment_failed":
        customer_id = data.get("customer")
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.subscription_status = "past_due"
            await db.commit()

