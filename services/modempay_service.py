"""Modem Pay — checkout redirect (same as Buxin Store) + optional API verify/webhook."""

import hashlib
import hmac
import json
import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from flask import current_app

logger = logging.getLogger(__name__)

API_BASE = "https://api.modempay.com/v1"
CHECKOUT_PAY_URL = "https://checkout.modempay.com/api/pay"


class ModemPayError(Exception):
    pass


def is_configured() -> bool:
    """Checkout link only needs the public key (same as Buxin Store)."""
    key = (current_app.config.get("MODEMPAY_PUBLIC_KEY") or "").strip()
    return bool(key) and not key.lower().startswith("your_")


def _normalize_gm_phone(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return "+2200000000"
    if digits.startswith("220"):
        return f"+{digits}"
    if len(digits) == 7:
        return f"+220{digits}"
    if phone and str(phone).strip().startswith("+"):
        return str(phone).strip()
    return f"+{digits}"


def _append_params(url: str, params: dict) -> str:
    try:
        parsed = urlparse(url)
        existing = parse_qs(parsed.query)
        for key, value in params.items():
            if value is None or value == "":
                continue
            existing[key] = [str(value)]
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                urlencode(existing, doseq=True),
                parsed.fragment,
            )
        )
    except Exception:
        sep = "&" if "?" in url else "?"
        kv = "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
        return f"{url}{sep}{kv}" if kv else url


def create_checkout_payment_link(
    amount: int,
    *,
    reference: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str | None = None,
    return_url: str,
    cancel_url: str,
    metadata: dict | None = None,
) -> dict:
    """
    Create a hosted Modem Pay checkout URL (Buxin Store method).
    POST https://checkout.modempay.com/api/pay — form-data + public_key only.
    """
    public_key = (current_app.config.get("MODEMPAY_PUBLIC_KEY") or "").strip()
    if not public_key:
        raise ModemPayError("Modem Pay public key is not configured")

    meta = metadata or {}
    form_payload: dict = {
        "public_key": public_key,
        "amount": int(amount),
        "currency": "GMD",
        "customer_name": customer_name or "Student",
        "customer_email": customer_email or "student@example.com",
        "customer_phone": _normalize_gm_phone(customer_phone),
        "return_url": return_url,
        "cancel_url": cancel_url,
    }
    for key, value in meta.items():
        if value is not None and value != "":
            form_payload[f"metadata[{key}]"] = str(value)

    logger.info(
        "Modem Pay checkout: amount=%s reference=%s return=%s",
        form_payload["amount"],
        reference,
        return_url[:80],
    )

    try:
        resp = requests.post(CHECKOUT_PAY_URL, data=form_payload, timeout=30)
    except requests.RequestException as exc:
        raise ModemPayError(f"Could not reach Modem Pay checkout: {exc}") from exc

    text = resp.text or ""
    if resp.status_code == 200 and "__NEXT_DATA__" in text:
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            text,
            re.S,
        )
        if match:
            try:
                next_data = json.loads(match.group(1))
                query = next_data.get("query") or {}
                props = next_data.get("props", {}).get("pageProps", {}) or {}
                intent_id = query.get("intent") or props.get("intent")
                token = query.get("token") or props.get("token")
                if intent_id and token:
                    payment_url = f"https://checkout.modempay.com/{intent_id}?token={token}"
                    return {
                        "payment_url": payment_url,
                        "intent_id": intent_id,
                        "reference": reference,
                    }
            except json.JSONDecodeError:
                pass

    error_message = "Failed to create Modem Pay checkout link"
    try:
        err_body = json.loads(text)
        if isinstance(err_body, dict):
            error_message = err_body.get("message") or err_body.get("error") or error_message
    except (json.JSONDecodeError, ValueError):
        if text:
            error_message = text[:200]

    logger.error(
        "Modem Pay checkout failed status=%s message=%s preview=%s",
        resp.status_code,
        error_message,
        text[:300],
    )
    raise ModemPayError(error_message)


def _headers():
    secret = current_app.config.get("MODEMPAY_SECRET_KEY") or ""
    return {
        "Authorization": f"Bearer {secret}",
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
            raise ModemPayError("Modem Pay API blocked this server (403).")
        raise ModemPayError(
            f"Modem Pay returned an invalid response (HTTP {resp.status_code})"
        )


def retrieve_transaction(transaction_id: str) -> dict:
    if not current_app.config.get("MODEMPAY_SECRET_KEY"):
        raise ModemPayError("Modem Pay secret key not configured for verification")
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
