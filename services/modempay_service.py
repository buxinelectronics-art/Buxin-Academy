"""Modem Pay API — https://docs.modempay.com/documentation/payments/overview"""

import hashlib
import hmac
import json
import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

API_BASE = "https://api.modempay.com/v1"


class ModemPayError(Exception):
    pass


def is_configured() -> bool:
    cfg = current_app.config
    return bool(cfg.get("MODEMPAY_SECRET_KEY") and cfg.get("MODEMPAY_PUBLIC_KEY"))


def _headers():
    return {
        "Authorization": f"Bearer {current_app.config['MODEMPAY_SECRET_KEY']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "BuxinAcademy/1.0",
    }


def _parse_json_response(resp: requests.Response) -> dict:
    text = (resp.text or "").strip()
    if not text:
        return {}
    try:
        return resp.json()
    except ValueError:
        snippet = text[:200].replace("\n", " ")
        logger.error("Modem Pay non-JSON response %s: %s", resp.status_code, snippet)
        if resp.status_code == 403:
            raise ModemPayError(
                "Modem Pay API blocked this server (403). "
                "Use Wave/AfriMoney checkout in the browser, or contact Modem Pay to whitelist your backend."
            )
        raise ModemPayError(
            f"Modem Pay returned an invalid response (HTTP {resp.status_code})"
        )


def create_payment_intent(
    amount: int,
    *,
    currency: str = "GMD",
    title: str = "",
    description: str = "",
    metadata: dict | None = None,
    callback_url: str | None = None,
    return_url: str | None = None,
    cancel_url: str | None = None,
    customer_email: str | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
) -> dict:
    payload = {
        "data": {
            "amount": int(amount),
            "currency": currency,
            "from_sdk": True,
            "metadata": metadata or {},
        }
    }
    if title:
        payload["data"]["title"] = title
    if description:
        payload["data"]["description"] = description
    if callback_url:
        payload["data"]["callback_url"] = callback_url
    if return_url:
        payload["data"]["return_url"] = return_url
    if cancel_url:
        payload["data"]["cancel_url"] = cancel_url
    if customer_email:
        payload["data"]["customer_email"] = customer_email
    if customer_name:
        payload["data"]["customer_name"] = customer_name
    if customer_phone:
        payload["data"]["customer_phone"] = customer_phone

    resp = requests.post(
        f"{API_BASE}/payments",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    body = _parse_json_response(resp)
    if not resp.ok:
        logger.error("Modem Pay intent failed: %s %s", resp.status_code, body)
        msg = body.get("message") or body.get("error")
        if isinstance(msg, dict):
            msg = msg.get("message") or str(msg)
        raise ModemPayError(msg or f"Modem Pay error ({resp.status_code})")
    return body.get("data") or body


def retrieve_transaction(transaction_id: str) -> dict:
    resp = requests.get(
        f"{API_BASE}/transactions/{transaction_id}",
        headers=_headers(),
        timeout=30,
    )
    body = _parse_json_response(resp)
    if not resp.ok:
        logger.error("Modem Pay transaction fetch failed: %s", body)
        raise ModemPayError(body.get("message") or "Could not verify payment")
    return body.get("data") or body


def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    if not signature:
        return False
    secret = (
        current_app.config.get("MODEMPAY_WEBHOOK_SECRET")
        or current_app.config.get("MODEMPAY_SECRET_KEY")
        or ""
    )
    if not secret:
        return False
    computed = hmac.new(secret.encode(), payload_bytes, hashlib.sha512).hexdigest()
    if len(computed) != len(signature):
        return False
    return hmac.compare_digest(computed, signature)


def parse_webhook_event(payload_bytes: bytes, signature: str) -> dict | None:
    if not verify_webhook_signature(payload_bytes, signature):
        return None
    try:
        return json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        return None
