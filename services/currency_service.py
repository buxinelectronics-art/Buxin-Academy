from flask import current_app

from services.countries import convert_price, get_country


def get_class_prices(country_code: str) -> dict:
    group_usd = current_app.config["BASE_GROUP_PRICE_USD"]
    individual_usd = current_app.config["BASE_INDIVIDUAL_PRICE_USD"]
    return {
        "group": convert_price(group_usd, country_code),
        "individual": convert_price(individual_usd, country_code),
        "payment_methods": get_country(country_code).get("payment_methods", [])
        if get_country(country_code)
        else [],
    }
