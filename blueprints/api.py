"""JSON endpoints powering the shared script.js (AJAX) interactions.

All handlers coerce and validate their input — malformed payloads get a 400,
never a 500.
"""
from flask import Blueprint, jsonify, request, session
from flask_login import current_user

from extensions import db, limiter
from models import (
    NewsletterSubscriber, Product, PromoCode, StockNotification, WishlistItem,
)
from services import (
    add_to_cart, cart_summary, inr, remove_from_cart, send_email,
    update_cart_quantity,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _int_or_none(value):
    """Strict int coercion: '12' -> 12, None/'abc'/12.7 -> None."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


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
    if len(q) < 2 or len(q) > 100:
        return jsonify({"results": []})
    like = f"%{q}%"
    rows = (
        Product.query.filter(
            db.or_(Product.name.ilike(like), Product.brand.ilike(like))
        )
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
            "image": p.image_url,
        } for p in rows]
    })


@api_bp.route("/cart/add", methods=["POST"])
@limiter.limit("60 per minute")
def cart_add():
    data = request.get_json(silent=True) or request.form
    product_id = _int_or_none(data.get("product_id"))
    quantity = _int_or_none(data.get("quantity", 1))
    if product_id is None:
        return jsonify({"ok": False, "message": "Invalid product."}), 400
    if quantity is None or quantity < 1:
        quantity = 1
    product, err = add_to_cart(current_user, product_id, quantity)
    if err:
        return jsonify({"ok": False, "message": err}), 400
    payload = summary_payload()
    payload["message"] = f"Added “{product.name}” to your cart."
    return jsonify(payload)


@api_bp.route("/cart/update", methods=["POST"])
def cart_update():
    data = request.get_json(silent=True) or request.form
    product_id = _int_or_none(data.get("product_id"))
    quantity = _int_or_none(data.get("quantity", 0))
    if product_id is None or quantity is None:
        return jsonify({"ok": False,
                        "message": "Invalid product or quantity."}), 400
    ok, err = update_cart_quantity(current_user, product_id, quantity)
    if err:
        return jsonify({"ok": False, "message": err}), 400
    payload = summary_payload()
    qty = max(quantity, 0)
    if qty:
        product = db.session.get(Product, product_id)
        payload["row_total"] = (
            round(product.effective_price * qty, 2) if product else 0)
    else:
        payload["row_total"] = 0
    return jsonify(payload)


@api_bp.route("/cart/remove", methods=["POST"])
def cart_remove():
    data = request.get_json(silent=True) or request.form
    product_id = _int_or_none(data.get("product_id"))
    if product_id is None:
        return jsonify({"ok": False, "message": "Invalid product."}), 400
    ok, err = remove_from_cart(current_user, product_id)
    if err:
        return jsonify({"ok": False, "message": err}), 400
    return jsonify(summary_payload())


@api_bp.route("/cart/save-later", methods=["POST"])
def cart_save_later():
    """Atomically move an item from the cart to the wishlist."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "login_required": True,
                        "message": "Please sign in to save items for later."}), 401
    data = request.get_json(silent=True) or request.form
    product_id = _int_or_none(data.get("product_id"))
    if product_id is None:
        return jsonify({"ok": False, "message": "Invalid product."}), 400
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"ok": False, "message": "Product not found."}), 404
    exists = current_user.wishlist_items.filter_by(
        product_id=product.id).first()
    if not exists:
        db.session.add(WishlistItem(customer_id=current_user.id,
                                    product_id=product.id))
        db.session.commit()
    ok, err = remove_from_cart(current_user, product_id)
    if err:
        return jsonify({"ok": False, "message": err}), 400
    payload = summary_payload()
    payload["message"] = "Saved to your wishlist."
    return jsonify(payload)


@api_bp.route("/promo", methods=["POST"])
@limiter.limit("15 per minute; 80 per hour")
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
                              f"Code {code} requires a minimum spend of {inr(check.min_spend)}.")
        return jsonify(payload), 200
    session["promo"] = code
    session.modified = True
    payload = summary_payload()
    payload["message"] = f"Promo {code} applied — {check.discount_percent}% off!"
    return jsonify(payload)


@api_bp.route("/wishlist/toggle", methods=["POST"])
@limiter.limit("60 per minute")
def wishlist_toggle():
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "message": "Sign in to use your wishlist.",
                        "login_required": True}), 401
    data = request.get_json(silent=True) or request.form
    product_id = _int_or_none(data.get("product_id"))
    if product_id is None:
        return jsonify({"ok": False, "message": "Invalid product."}), 400
    product = db.session.get(Product, product_id)
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
@limiter.limit("10 per hour; 3 per minute")
def notify():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    product_id = _int_or_none(data.get("product_id"))
    if product_id is None:
        return jsonify({"ok": False, "message": "Invalid product."}), 400
    if "@" not in email or len(email) > 255:
        return jsonify({"ok": False, "message": "Please enter a valid email."}), 400
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"ok": False, "message": "Product not found."}), 404
    already = StockNotification.query.filter_by(
        product_id=product.id, email=email).first()
    if already:
        return jsonify({"ok": True,
                        "message": "You're already on the list for this product."})
    db.session.add(StockNotification(product_id=product.id, email=email))
    db.session.commit()
    send_email(email, "We'll let you know when it's back",
               f"Thanks! We'll email you as soon as “{product.name}” is back in stock.")
    return jsonify({"ok": True,
                    "message": "You're on the list — we'll email you when it's back."})


@api_bp.route("/product/<int:product_id>/card")
def product_card_data(product_id):
    """Lightweight product payload for the quick-view modal."""
    p = db.session.get(Product, product_id)
    if not p:
        return jsonify({"ok": False, "message": "Product not found."}), 404
    images = [img.url for img in p.images][:5] or [p.image_url]
    wishlisted = bool(
        current_user.is_authenticated
        and current_user.wishlist_items.filter_by(product_id=p.id).first()
    )
    desc = (p.description or "").strip()
    if len(desc) > 260:
        desc = desc[:257].rstrip() + "…"
    return jsonify({
        "ok": True,
        "id": p.id,
        "name": p.name,
        "brand": p.brand or "ShopLinq",
        "url": f"/product/{p.slug}",
        "price": p.effective_price,
        "list_price": p.price if (p.is_deal and p.deal_price) else None,
        "is_deal": bool(p.is_deal and p.deal_price),
        "rating": p.rating,
        "rating_count": p.rating_count,
        "in_stock": p.in_stock,
        "stock": p.stock,
        "description": desc,
        "images": images,
        "wishlisted": wishlisted,
    })


@api_bp.route("/newsletter/subscribe", methods=["POST"])
@limiter.limit("12 per hour; 4 per minute")
def newsletter_subscribe():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 255:
        return jsonify({"ok": False, "message": "Please enter a valid email address."}), 400
    existing = NewsletterSubscriber.query.filter_by(email=email).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.session.commit()
        return jsonify({"ok": True, "message": "You're subscribed — thanks for staying in touch!"})
    db.session.add(NewsletterSubscriber(email=email))
    db.session.commit()
    send_email(email, "Welcome to ShopLinq",
               "Thanks for subscribing! You'll be first to hear about new drops and deals.")
    return jsonify({"ok": True, "message": "You're in! Watch your inbox for new drops and deals."})
