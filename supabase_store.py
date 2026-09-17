import os
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _headers(prefer: str | None = None):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _request(method: str, table: str, *, params=None, json=None, prefer=None):
    if not configured():
        return None
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        with httpx.Client(timeout=15) as client:
            response = client.request(method, url, params=params, json=json, headers=_headers(prefer))
            response.raise_for_status()
            if not response.content:
                return []
            return response.json()
    except httpx.HTTPError as exc:
        print(f"Supabase {table} error: {exc}")
        return None


def ensure_user(user):
    payload = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return _request("POST", "telegram_users", json=payload, prefer="resolution=merge-duplicates,return=minimal")


def create_task(telegram_id, data, fallback):
    title = data.get("title") or data.get("task") or fallback
    payload = {
        "telegram_id": telegram_id,
        "title": title,
        "description": data.get("description"),
        "deadline": data.get("deadline"),
        "priority": data.get("priority", "medium"),
        "status": data.get("status", "pending"),
    }
    result = _request("POST", "tasks", json=payload, prefer="return=representation")
    return result[0]["id"] if result else None


def create_transaction(telegram_id, transaction_type, data):
    raw = data.get("amount") or data.get("nominal")
    if raw is None:
        return None
    try:
        amount = float(str(raw).replace(".", "").replace(",", ""))
    except ValueError:
        return None
    payload = {
        "telegram_id": telegram_id,
        "type": transaction_type,
        "amount": amount,
        "category": data.get("category", "Lainnya"),
        "description": data.get("description") or data.get("note"),
    }
    result = _request("POST", "transactions", json=payload, prefer="return=representation")
    return result[0]["id"] if result else None


def create_goal(telegram_id, data):
    title = data.get("title") or data.get("goal")
    if not title:
        return None
    target = data.get("target_amount") or data.get("target")
    try:
        target = float(target) if target is not None else None
    except (ValueError, TypeError):
        target = None
    payload = {
        "telegram_id": telegram_id,
        "title": title,
        "target_amount": target,
        "current_amount": float(data.get("current_amount", data.get("saved_amount", 0)) or 0),
        "deadline": data.get("deadline"),
    }
    result = _request("POST", "goals", json=payload, prefer="return=representation")
    return result[0]["id"] if result else None


def list_tasks(telegram_id):
    return _request("GET", "tasks", params={
        "telegram_id": f"eq.{telegram_id}",
        "status": "neq.done",
        "order": "created_at.desc",
        "limit": "10",
    }) or []


def list_transactions(telegram_id, limit=5):
    return _request("GET", "transactions", params={
        "telegram_id": f"eq.{telegram_id}",
        "order": "occurred_at.desc",
        "limit": str(limit),
    }) or []


def list_goals(telegram_id):
    return _request("GET", "goals", params={
        "telegram_id": f"eq.{telegram_id}",
        "status": "eq.active",
        "order": "created_at.desc",
        "limit": "10",
    }) or []


def totals(telegram_id):
    rows = _request("GET", "transactions", params={
        "telegram_id": f"eq.{telegram_id}",
        "select": "type,amount",
    }) or []
    income = sum(float(r["amount"]) for r in rows if r.get("type") == "income")
    expense = sum(float(r["amount"]) for r in rows if r.get("type") == "expense")
    return income, expense
