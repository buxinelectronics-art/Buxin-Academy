from flask import Blueprint, jsonify, request

from services.countries import get_country, list_countries
from services.currency_service import get_class_prices

country_bp = Blueprint("country", __name__, url_prefix="/api")


@country_bp.route("/countries", methods=["GET"])
def countries():
    return jsonify({"countries": list_countries()})


@country_bp.route("/countries/<code>", methods=["GET"])
def country_detail(code):
    country = get_country(code)
    if not country:
        return jsonify({"error": "Country not found"}), 404
    return jsonify({
        "code": code.upper(),
        "name": country["name"],
        "flag": country["flag"],
        "currency": country["currency"],
        "symbol": country["symbol"],
        "payment_methods": country["payment_methods"],
    })


@country_bp.route("/prices", methods=["GET"])
def prices():
    code = request.args.get("country", "GM")
    return jsonify(get_class_prices(code.upper()))
