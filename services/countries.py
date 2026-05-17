"""Country, currency, and payment method configuration."""

COUNTRIES = {
    "GM": {
        "name": "The Gambia",
        "flag": "🇬🇲",
        "currency": "GMD",
        "symbol": "D",
        "rate": 72.5,
        "payment_methods": [
            "Mobile Wallet",
            "Bank Transfer",
            "Western Union / MoneyGram / Ria",
        ],
    },
    "NG": {
        "name": "Nigeria",
        "flag": "🇳🇬",
        "currency": "NGN",
        "symbol": "₦",
        "rate": 1500.0,
        "payment_methods": [
            "Bank Transfer",
            "Opay",
            "PalmPay",
            "Kuda",
            "Visa",
            "Mastercard",
        ],
    },
    "SN": {
        "name": "Senegal",
        "flag": "🇸🇳",
        "currency": "XOF",
        "symbol": "CFA",
        "rate": 600.0,
        "payment_methods": ["Wave", "Orange Money", "Bank Transfer", "Western Union"],
    },
    "GH": {
        "name": "Ghana",
        "flag": "🇬🇭",
        "currency": "GHS",
        "symbol": "GH₵",
        "rate": 15.5,
        "payment_methods": ["MTN MoMo", "Vodafone Cash", "Bank Transfer", "Visa", "Mastercard"],
    },
    "KE": {
        "name": "Kenya",
        "flag": "🇰🇪",
        "currency": "KES",
        "symbol": "KSh",
        "rate": 130.0,
        "payment_methods": ["M-Pesa", "Bank Transfer", "Visa", "Mastercard"],
    },
    "UG": {
        "name": "Uganda",
        "flag": "🇺🇬",
        "currency": "UGX",
        "symbol": "USh",
        "rate": 3700.0,
        "payment_methods": ["MTN MoMo", "Airtel Money", "Bank Transfer"],
    },
    "TZ": {
        "name": "Tanzania",
        "flag": "🇹🇿",
        "currency": "TZS",
        "symbol": "TSh",
        "rate": 2600.0,
        "payment_methods": ["M-Pesa", "Tigo Pesa", "Airtel Money", "Bank Transfer"],
    },
    "SL": {
        "name": "Sierra Leone",
        "flag": "🇸🇱",
        "currency": "SLL",
        "symbol": "Le",
        "rate": 22000.0,
        "payment_methods": ["Orange Money", "Bank Transfer", "Western Union"],
    },
    "GN": {
        "name": "Guinea",
        "flag": "🇬🇳",
        "currency": "GNF",
        "symbol": "FG",
        "rate": 8600.0,
        "payment_methods": ["Orange Money", "MTN MoMo", "Bank Transfer"],
    },
    "CI": {
        "name": "Côte d'Ivoire",
        "flag": "🇨🇮",
        "currency": "XOF",
        "symbol": "CFA",
        "rate": 600.0,
        "payment_methods": ["Orange Money", "MTN MoMo", "Wave", "Bank Transfer"],
    },
    "ZA": {
        "name": "South Africa",
        "flag": "🇿🇦",
        "currency": "ZAR",
        "symbol": "R",
        "rate": 18.5,
        "payment_methods": ["EFT", "SnapScan", "Visa", "Mastercard", "Bank Transfer"],
    },
    "OTHER": {
        "name": "Other country",
        "flag": "🌍",
        "currency": "USD",
        "symbol": "$",
        "rate": 1.0,
        "payment_methods": [
            "Bank Transfer",
            "Visa",
            "Mastercard",
            "Western Union / MoneyGram / Ria",
        ],
    },
}


def get_country(code: str):
    key = (code or "").upper()
    if key == "OTHER":
        return COUNTRIES["OTHER"]
    return COUNTRIES.get(key)


def list_countries():
    return [
        {
            "code": code,
            "name": data["name"],
            "flag": data["flag"],
            "currency": data["currency"],
            "symbol": data["symbol"],
        }
        for code, data in COUNTRIES.items()
    ]


def convert_price(usd_amount: float, country_code: str) -> dict:
    country = get_country(country_code)
    if not country:
        return {
            "usd": usd_amount,
            "local": usd_amount,
            "formatted": f"${usd_amount:.2f}",
            "currency": "USD",
            "symbol": "$",
        }
    local = usd_amount * country["rate"]
    symbol = country["symbol"]
    if local >= 1000:
        formatted = f"{symbol}{local:,.2f}"
    else:
        formatted = f"{symbol}{local:.2f}"
    return {
        "usd": usd_amount,
        "local": round(local, 2),
        "formatted": formatted,
        "currency": country["currency"],
        "symbol": symbol,
        "country": country["name"],
    }
