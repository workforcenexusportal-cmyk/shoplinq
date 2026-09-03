"""JSON endpoints powering the shared script.js (AJAX) interactions."""
from flask import Blueprint, jsonify, request, session
from flask_login import current_user

from blueprints.cart import _summary
from extensions import db
from models import Product, PromoCode, StockNotification, WishlistItem
from services import (
    add_to_cart, cart_summary, remove_from_cart, send_email,
    update_cart_quantity,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def summary_payload(delivery=None, promo=None):
    s = cart_summary(current_user, delivery or session.get("delivery", "standard"),
                     promo if promo is not None else session.get("promo"))
    return {
        "ok": True,
        "count": s["count"],
        "subtotal": s["subtotal"],
        "discount": s["discount"],
        "tax": s["tax"],
        "shipping_fee": s["shipping_fee"],
        "total": s["total"],
        "promo": s["promo"].code if s["promo"] else None,
        "message": None,
    }


@api_bp.route("/search/suggest")
def suggest():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"results": []})
    like = f"%{q}%"
    rows = (
        Product.query.filter(
            db.or_(Product.name.ilike(like), Product.brand.ilike(like))
        )
        .filter(Product.stock >= 0)
        .order_by(Product.rating_count.desc())
        .limit(8)
        .all()
    )
    return jsonify({
        "results": [{
            "name": p.name,
            "brand": p.brand,
            "url": f"/product/{p.slug}",
            "price": p.effective_price,
            "image": p.primary_image.url if p.primary_image else None,
        } for p in rows]
    })


@api_bp.route("/cart/add", methods=["POST"])
def cart_add():
    data = request.get_json(silent=True) or request.form
    product, err = add_to_cart(current_user, data.get("product_id"),
                               data.get("quantity", 1))
    if err:
        return jsonify({"ok": False, "message": err}), 400
    payload = summary_payload()
    payload["message"] = f"Added “{product.name}” to your cart."
    return jsonify(payload)


@api_bp.route("/cart/update", methods=["POST"])
def cart_update():
    data = request.get_json(silent=True) or request.form
    product_id = data.get("product_id")
    ok, err = update_cart_quantity(current_user, product_id, data.get("quantity", 0))
    if err:
        return jsonify({"ok": False, "message": err}), 400
    payload = summary_payload()
    product = db.session.get(Product, int(product_id))
    qty = int(data.get("quantity", 0))
    payload["row_total"] = round(product.effective_price * qty, 2) if product and qty else 0
    return jsonify(payload)


@api_bp.route("/cart/remove", methods=["POST"])
def cart_remove():
    data = request.get_json(silent=True) or request.form
    ok, err = remove_from_cart(current_user, data.get("product_id"))
    if err:
        return jsonify({"ok": False, "message": err}), 400
    return jsonify(summary_payload())


@api_bp.route("/promo", methods=["POST"])
def promo():
    data = request.get_json(silent=True) or request.form
    code = (data.get("code") or "").strip().upper()
    if not code:
        session.pop("promo", None)
        session.modified = True
        return jsonify(summary_payload())
    check = PromoCode.query.filter_by(code=code, is_active=True).first()
    subtotal = cart_summary(current_user)["subtotal"]
    if not check or subtotal < (check.min_spend or 0):
        session.pop("promo", None)
        session.modified = True
        payload = summary_payload()
        payload["ok"] = False
        payload["message"] = ("That promo code isn't valid"
                              if not check else
                              f"Code {code} requires a minimum spend of ${check.min_spend:.2f}.")
        return jsonify(payload), 200
    session["promo"] = code
    session.modified = True
    payload = summary_payload()
    payload["message"] = f"Promo {code} applied — {check.discount_percent}% off!"
    return jsonify(payload)


@api_bp.route("/wishlist/toggle", methods=["POST"])
def wishlist_toggle():
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "message": "Sign in to use your wishlist.",
                        "login_required": True}), 401
    data = request.get_json(silent=True) or request.form
    product = db.session.get(Product, int(data.get("product_id") or 0))
    if not product:
        return jsonify({"ok": False, "message": "Product not found."}), 404
    item = current_user.wishlist_items.filter_by(product_id=product.id).first()
    if item:
        db.session.delete(item)
        added = False
        message = "Removed from your wishlist."
    else:
        db.session.add(WishlistItem(customer_id=current_user.id, product_id=product.id))
        added = True
        message = "Saved to your wishlist."
    db.session.commit()
    return jsonify({"ok": True, "added": added, "message": message})


@api_bp.route("/notify", methods=["POST"])
def notify():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    product = db.session.get(Product, int(data.get("product_id") or 0))
    if not product or "@" not in email:
        return jsonify({"ok": False, "message": "Please enter a valid email."}), 400
    db.session.add(StockNotification(product_id=product.id, email=email))
    db.session.commit()
    send_email(email, "We'll let you know when it's back",
               f"Thanks! We'll email you as soon as “{product.name}” is back in stock.")
    return jsonify({"ok": True,
                    "message": "You're on the list — we'll email you when it's back."})
