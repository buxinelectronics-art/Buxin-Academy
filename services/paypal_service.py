"""PayPal Checkout — create & capture orders (USD)."""
import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)


class PayPalError(Exception):
    pass


def _api_base() -> str:
    mode = (current_app.config.get("PAYPAL_MODE") or "sandbox").lower()
    if mode == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def is_configured() -> bool:
    return bool(
        current_app.config.get("PAYPAL_CLIENT_ID")
        and current_app.config.get("PAYPAL_CLIENT_SECRET")
    )


def _access_token() -> str:
    if not is_configured():
        raise PayPalError("PayPal is not configured on the server")
    url = f"{_api_base()}/v1/oauth2/token"
    try:
        resp = requests.post(
            url,
            auth=(
                current_app.config["PAYPAL_CLIENT_ID"],
                current_app.config["PAYPAL_CLIENT_SECRET"],
            ),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise PayPalError(f"Could not reach PayPal: {exc}") from exc
    if resp.status_code >= 400:
        logger.error("PayPal token error %s: %s", resp.status_code, resp.text[:500])
        raise PayPalError("PayPal authentication failed")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise PayPalError("PayPal authentication failed")
    return token


def _api_request(method: str, path: str, *, json_body=None) -> dict:
    token = _access_token()
    url = f"{_api_base()}{path}"
    try:
        resp = requests.request(
            method,
            url,
            json=json_body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=45,
        )
    except requests.RequestException as exc:
        raise PayPalError(f"Could not reach PayPal: {exc}") from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400:
        msg = data.get("message") or data.get("error_description") or resp.text[:300]
        logger.error("PayPal API %s %s -> %s", method, path, msg)
        raise PayPalError(msg or "PayPal request failed")
    return data


def create_order(amount_usd: float, reference: str) -> dict:
    """Create a PayPal order for capture after buyer approval."""
    amount_usd = max(float(amount_usd), 0.01)
    value = f"{amount_usd:.2f}"
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference,
                "description": "Buxin Academy subscription",
                "amount": {
                    "currency_code": "USD",
                    "value": value,
                },
            }
        ],
        "application_context": {
            "brand_name": "Buxin Academy",
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",
        },
    }
    data = _api_request("POST", "/v2/checkout/orders", json_body=payload)
    order_id = data.get("id")
    if not order_id:
        raise PayPalError("PayPal did not return an order id")
    return {"order_id": order_id, "status": data.get("status")}


def capture_order(order_id: str) -> dict:
    """Capture funds after buyer approves in PayPal checkout."""
    if not order_id:
        raise PayPalError("Missing PayPal order id")
    return _api_request("POST", f"/v2/checkout/orders/{order_id}/capture")


def get_order(order_id: str) -> dict:
    return _api_request("GET", f"/v2/checkout/orders/{order_id}")


def extract_capture_amount_usd(capture_payload: dict) -> float | None:
    try:
        units = capture_payload.get("purchase_units") or []
        if not units:
            return None
        captures = (units[0].get("payments") or {}).get("captures") or []
        if not captures:
            return None
        amount = captures[0].get("amount") or {}
        if (amount.get("currency_code") or "").upper() != "USD":
            return None
        return float(amount.get("value"))
    except (TypeError, ValueError, IndexError):
        return None
