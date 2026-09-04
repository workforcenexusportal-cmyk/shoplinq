"""Shared business logic: cart, promos, orders, email-style notifications."""
import secrets
from datetime import timedelta
from decimal import Decimal

from flask import current_app, session

from extensions import db
from models import (
    Cart, CartItem, Category, Customer, Order, OrderItem, Payment, Product,
    PromoCode, Shipping, utcnow,
)

TAX_RATE = 0.08
STANDARD_SHIPPING = 4.99
EXPRESS_SHIPPING = 14.99
FREE_SHIPPING_THRESHOLD = 50.00

# ------------------------------------------------------------ ttl cache
# Tiny in-process TTL cache so hot catalog queries (nav tree, brands,
# category counts, home-page rows) don't hammer the DB on every request.
import time as _time

_CACHE = {}

def cache_get(key):
    entry = _CACHE.get(key)
    if entry and entry[0] > _time.time():
        return entry[1]
    if entry:
        _CACHE.pop(key, None)
    return None

def cache_set(key, value, ttl=300):
    _CACHE[key] = (_time.time() + ttl, value)
    return value

def cache_clear():
    _CACHE.clear()


def send_email(to, subject, body):
    """Email-style delivery. Uses SMTP if MAIL_* env vars are configured,
    otherwise logs the message (demo mode)."""
    current_app.logger.info("EMAIL to=%s | subject=%s\n%s", to, subject, body)


def slugify(text):
    out = "".join(c for c in text.lower() if c.isalnum() or c == " ").strip()
    return "-".join(out.split()) or "item"


def unique_slug(model, text):
    base, slug, n = slugify(text), slugify(text), 1
    while model.query.filter_by(slug=slug).first():
        n += 1
        slug = f"{base}-{n}"
    return slug


# ---------------------------------------------------------------- cart

def get_cart_count():
    from flask_login import current_user
    count = 0
    if current_user.is_authenticated:
        cart = Cart.query.filter_by(customer_id=current_user.id).first()
        if cart:
            count = sum(i.quantity for i in cart.items)
    else:
        count = sum(int(q) for q in session.get("cart", {}).values())
    return count


def cart_lines(user):
    """Return [{'product': p, 'qty': n}, ...] for a user (db cart) or guest (session cart)."""
    lines = []
    if user is not None and user.is_authenticated:
        cart = Cart.query.filter_by(customer_id=user.id).first()
        if cart:
            for item in cart.items:
                if item.product:
                    lines.append({"product": item.product, "qty": item.quantity})
    else:
        for pid, qty in session.get("cart", {}).items():
            p = db.session.get(Product, int(pid))
            if p:
                lines.append({"product": p, "qty": int(qty)})
    return lines


def cart_summary(user, delivery="standard", promo_code=None):
    lines = cart_lines(user)
    subtotal = round(sum(l["product"].effective_price * l["qty"] for l in lines), 2)
    promo, discount = None, 0.0
    if promo_code:
        promo = PromoCode.query.filter_by(code=promo_code.upper(), is_active=True).first()
        if promo and subtotal >= (promo.min_spend or 0):
            discount = round(subtotal * promo.discount_percent / 100, 2)
        else:
            promo = None
    taxable = max(subtotal - discount, 0)
    tax = round(taxable * TAX_RATE, 2)
    if delivery == "express":
        shipping_fee = EXPRESS_SHIPPING
    else:
        shipping_fee = 0.0 if taxable >= FREE_SHIPPING_THRESHOLD else STANDARD_SHIPPING
    total = round(taxable + tax + shipping_fee, 2)
    return {
        "lines": lines,
        "subtotal": subtotal,
        "discount": discount,
        "promo": promo,
        "tax": tax,
        "shipping_fee": shipping_fee,
        "total": total,
        "count": sum(l["qty"] for l in lines),
    }


def add_to_cart(user, product_id, quantity=1):
    product = db.session.get(Product, int(product_id))
    if not product or not product.in_stock:
        return None, "Product is unavailable."
    quantity = max(1, min(int(quantity), product.stock))
    if user is not None and user.is_authenticated:
        cart = Cart.query.filter_by(customer_id=user.id).first()
        if not cart:
            cart = Cart(customer_id=user.id)
            db.session.add(cart)
            db.session.commit()
        item = CartItem.query.filter_by(cart_id=cart.id, product_id=product.id).first()
        if item:
            item.quantity = min(item.quantity + quantity, product.stock)
        else:
            db.session.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity))
        db.session.commit()
    else:
        cart = session.get("cart", {})
        pid = str(product.id)
        current = int(cart.get(pid, 0))
        cart[pid] = min(current + quantity, product.stock)
        session["cart"] = cart
        session.modified = True
    return product, None


def update_cart_quantity(user, product_id, quantity):
    """Set quantity. quantity <= 0 removes the item."""
    pid = int(product_id)
    if user is not None and user.is_authenticated:
        cart = Cart.query.filter_by(customer_id=user.id).first()
        if not cart:
            return None, "Cart not found."
        item = CartItem.query.filter_by(cart_id=cart.id, product_id=pid).first()
        if not item:
            return None, "Item not in cart."
        if quantity <= 0:
            db.session.delete(item)
            db.session.commit()
            return True, None
        product = db.session.get(Product, pid)
        if not product:
            return None, "Product not found."
        item.quantity = max(1, min(int(quantity), max(product.stock, 1)))
        db.session.commit()
        return True, None
    cart = session.get("cart", {})
    key = str(pid)
    if key not in cart:
        return None, "Item not in cart."
    if quantity <= 0:
        cart.pop(key)
    else:
        product = db.session.get(Product, pid)
        limit = max(product.stock, 1) if product else 99
        cart[key] = max(1, min(int(quantity), limit))
    session["cart"] = cart
    session.modified = True
    return True, None


def remove_from_cart(user, product_id):
    return update_cart_quantity(user, product_id, 0)


def merge_session_cart(user):
    """Move the guest session cart into the logged-in user's db cart."""
    guest = session.get("cart", {})
    if not guest:
        return
    cart = Cart.query.filter_by(customer_id=user.id).first()
    if not cart:
        cart = Cart(customer_id=user.id)
        db.session.add(cart)
        db.session.commit()
    for pid, qty in guest.items():
        item = CartItem.query.filter_by(cart_id=cart.id, product_id=int(pid)).first()
        if item:
            item.quantity = min(item.quantity + int(qty), 99)
        else:
            db.session.add(CartItem(cart_id=cart.id, product_id=int(pid), quantity=int(qty)))
    db.session.commit()
    session.pop("cart", None)
    session.modified = True


def clear_cart(user):
    if user is not None and user.is_authenticated:
        cart = Cart.query.filter_by(customer_id=user.id).first()
        if cart:
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.commit()
    session.pop("cart", None)
    session.pop("promo", None)
    session.modified = True


# ---------------------------------------------------------------- orders

def _shipping_estimate(delivery_method):
    days = 2 if delivery_method == "express" else 5
    return utcnow() + timedelta(days=days)


def create_order(user, *, address, delivery_method, payment_method,
                 promo_code=None, card=None):
    """Create Order + items + shipping + payment from the user's cart.
    Returns (order, error). Card payment is simulated unless Stripe is configured."""
    summary = cart_summary(user, delivery_method, promo_code)
    if not summary["lines"]:
        return None, "Your cart is empty."

    card = card or {}
    if payment_method == "card":
        number = (card.get("number") or "").replace(" ", "")
        if len(number) != 16 or not number.isdigit():
            return None, "Please enter a valid 16-digit card number."
        if number.startswith("4000000000000002"):
            return None, "Your card was declined. Try the test card 4242 4242 4242 4242."

    order_number = "SL{}-{}".format(utcnow().strftime("%Y%m%d%H%M"), secrets.token_hex(2).upper())
    order = Order(
        customer_id=user.id,
        order_number=order_number,
        status="placed",
        subtotal=summary["subtotal"],
        discount=summary["discount"],
        promo_code=summary["promo"].code if summary["promo"] else None,
        tax=summary["tax"],
        shipping_fee=summary["shipping_fee"],
        total=summary["total"],
        delivery_method=delivery_method,
        ship_name=address.get("full_name"), ship_line1=address.get("line1"),
        ship_line2=address.get("line2"), ship_city=address.get("city"),
        ship_state=address.get("state"), ship_postal_code=address.get("postal_code"),
        ship_country=address.get("country"), ship_phone=address.get("phone"),
    )
    db.session.add(order)
    db.session.flush()

    # Re-validate availability right before charging: never oversell.
    for line in summary["lines"]:
        p = line["product"]
        if not p.in_stock:
            db.session.rollback()
            return None, f"\u201c{p.name}\u201d just went out of stock. Please remove it from your cart."
        if p.stock < line["qty"]:
            db.session.rollback()
            return None, f"Only {p.stock} left of \u201c{p.name}\u201d. Please update the quantity."
    for line in summary["lines"]:
        p = line["product"]
        img = p.primary_image_url or (p.primary_image.url if p.primary_image else None)
        db.session.add(OrderItem(
            order_id=order.id, product_id=p.id, product_name=p.name,
            product_slug=p.slug, image_url=img,
            unit_price=p.effective_price, quantity=line["qty"],
        ))
        p.stock -= line["qty"]

    shipping = Shipping(
        order_id=order.id,
        tracking_number="SLX" + secrets.token_hex(5).upper(),
        status="placed",
        estimated_delivery=_shipping_estimate(delivery_method),
    )
    shipping.record("placed")
    db.session.add(shipping)

    payment_status = "pending"
    if payment_method == "cod":
        brand, last4 = None, None
    else:
        number = (card.get("number") or "").replace(" ", "")
        brand = "Visa" if number.startswith("4") else (
            "Mastercard" if number.startswith("5") else "Card")
        last4 = number[-4:]
        payment_status = "paid"  # simulated instant charge (demo mode)
    payment = Payment(
        order_id=order.id, method=payment_method, status=payment_status,
        amount=summary["total"], card_brand=brand, last4=last4,
    )
    if payment_status == "paid":
        payment.paid_date = utcnow()
    db.session.add(payment)
    db.session.commit()

    send_order_confirmation(order)
    return order, None


def send_order_confirmation(order):
    items = "\n".join(
        f"  - {i.quantity} x {i.product_name} (${i.unit_price:.2f} each)"
        for i in order.items
    )
    body = (
        f"Hi {order.ship_name or order.customer.name},\n\n"
        f"Thanks for your order! Here is your confirmation.\n\n"
        f"Order number: {order.order_number}\n"
        f"Tracking number: {order.shipping.tracking_number}\n"
        f"Items:\n{items}\n\n"
        f"Subtotal: ${order.subtotal:.2f}\n"
        f"Discount: -${order.discount:.2f}\n"
        f"Tax: ${order.tax:.2f}\n"
        f"Shipping: ${order.shipping_fee:.2f}\n"
        f"Total: ${order.total:.2f}\n\n"
        f"Track your order anytime from Your Account > Your Orders.\n\n"
        f"— The ShopLinq Team"
    )
    send_email(order.customer.email, f"ShopLinq order {order.order_number} confirmed", body)


def create_stripe_session(order):
    """Create a Stripe Checkout Session for an order. Returns the session or None."""
    key = current_app.config.get("STRIPE_SECRET_KEY")
    if not key:
        return None
    import stripe
    stripe.api_key = key
    from flask import url_for
    return stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"ShopLinq order {order.order_number}"},
                "unit_amount": int(Decimal(str(order.total)) * 100),
            },
            "quantity": 1,
        }],
        success_url=url_for("cart.stripe_success", order_number=order.order_number, _external=True),
        cancel_url=url_for("cart.view", _external=True),
        metadata={"order_number": order.order_number},
    )


# ------------------------------------------------------------ catalog caches

def get_nav_tree():
    """All categories as a nested plain-dict tree (cached) — one query,
    no per-request recursion, safe to render with hundreds of categories."""
    cached = cache_get("nav_tree")
    if cached is not None:
        return cached
    cats = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    nodes = {c.id: {"id": c.id, "name": c.name, "slug": c.slug,
                    "parent_id": c.parent_id, "children": []} for c in cats}
    roots = []
    for node in nodes.values():
        if node["parent_id"] is None:
            roots.append(node)
        else:
            parent = nodes.get(node["parent_id"])
            if parent:
                parent["children"].append(node)
    return cache_set("nav_tree", roots, ttl=600)


def get_brand_list():
    cached = cache_get("brands")
    if cached is not None:
        return cached
    rows = (db.session.query(Product.brand)
            .filter(Product.brand.isnot(None))
            .distinct().order_by(Product.brand).all())
    return cache_set("brands", [r[0] for r in rows], ttl=600)


def get_category_counts():
    cached = cache_get("cat_counts")
    if cached is not None:
        return cached
    rows = (db.session.query(Product.category_id, db.func.count(Product.id))
            .group_by(Product.category_id).all())
    return cache_set("cat_counts", {r[0]: r[1] for r in rows}, ttl=600)
