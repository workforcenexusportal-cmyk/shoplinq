"""Shared business logic: cart, promos, orders, email-style notifications."""
import os
import secrets
import smtplib
from datetime import timedelta
from decimal import Decimal
from email.message import EmailMessage

from flask import current_app, session

from extensions import db
from models import (
    Cart, CartItem, Category, Customer, Order, OrderItem, Payment, Product,
    PromoCode, Shipping, StockNotification, utcnow,
)

# ------------------------------------------------------------ India pricing
# Prices are MRP-style: GST is included in the listed price (Indian
# convention), so no tax is added on top at checkout.
TAX_RATE = 0.0
STANDARD_SHIPPING = 79.00      # Rs.79
EXPRESS_SHIPPING = 199.00      # Rs.199
FREE_SHIPPING_THRESHOLD = 999.00  # free standard shipping over Rs.999
ONLINE_METHODS = ("upi", "card", "netbanking", "wallet")
DECLINE_HINTS = {
    "upi": "fail@upi",
    "card": "4000000000000002",
}

def inr(value):
    """Format a number as Indian Rupees with Indian digit grouping.

    Whole rupees render without decimals (Rs.1,299); fractional amounts
    keep two decimals (Rs.1,298.90). Grouping is Indian style:
    1,23,456 / 12,34,56,789.
    """
    if value is None:
        return "\u2014"
    value = round(float(value), 2)
    whole, frac = divmod(abs(value), 1)
    digits = str(int(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    out = f"\u20b9{digits}"
    if round(frac, 2) > 0:
        out += f".{int(round(frac * 100)):02d}"
    return ("-" if value < 0 else "") + out


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
    """Deliver an email.

    Sends via SMTP when MAIL_SERVER is configured; otherwise (demo mode) logs
    the message so local development and testing work without a mail server.
    Never raises — a mail failure must not break checkout or password reset.
    """
    server = os.environ.get("MAIL_SERVER")
    if not server:
        current_app.logger.info("EMAIL (demo) to=%s | subject=%s\n%s", to, subject, body)
        return True

    sender = (os.environ.get("MAIL_DEFAULT_SENDER")
              or os.environ.get("MAIL_USERNAME")
              or "no-reply@shoplinq.com")
    port = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    use_ssl = os.environ.get("MAIL_USE_SSL", "0") == "1"
    use_tls = os.environ.get("MAIL_USE_TLS", "1") == "1" and not use_ssl

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(body)

    try:
        if use_ssl:
            smtp = smtplib.SMTP_SSL(server, port, timeout=15)
        else:
            smtp = smtplib.SMTP(server, port, timeout=15)
        with smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
                smtp.ehlo()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        current_app.logger.info("EMAIL sent to=%s | subject=%s", to, subject)
        return True
    except Exception as exc:  # noqa: BLE001 — email must never break the request
        current_app.logger.error("EMAIL failed to=%s | subject=%s | %s", to, subject, exc)
        return False


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


# ---------------------------------------------------------------- recently viewed

def record_recently_viewed(product_id):
    """Remember a product the visitor just viewed (most-recent first)."""
    pid = int(product_id)
    viewed = [i for i in session.get("recently_viewed", []) if i != pid]
    viewed.insert(0, pid)
    session["recently_viewed"] = viewed[:12]
    session.modified = True


def get_recently_viewed(exclude_id=None, limit=8):
    """Return recently-viewed Product objects, most-recent first."""
    ids = [i for i in session.get("recently_viewed", []) if i != exclude_id]
    if not ids:
        return []
    ids = ids[:limit]
    products = Product.query.filter(Product.id.in_(ids)).all()
    by_id = {p.id: p for p in products}
    return [by_id[i] for i in ids if i in by_id]


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
                 promo_code=None, pay=None):
    """Create Order + items + shipping + payment from the user's cart.
    Returns (order, error).

    Payment methods (India): upi | card | netbanking | wallet | cod.
    Without Razorpay keys the online methods are simulated (demo mode);
    with keys the payment stays pending until the Razorpay callback
    verifies the signature.
    """
    summary = cart_summary(user, delivery_method, promo_code)
    if not summary["lines"]:
        return None, "Your cart is empty."
    if not bool(getattr(user, "is_authenticated", False)):
        return None, "Please sign in to place your order."
    if payment_method not in ONLINE_METHODS + ("cod",):
        return None, "Please choose a valid payment method."

    pay = pay or {}
    if payment_method == "card":
        number = (pay.get("number") or "").replace(" ", "")
        if len(number) != 16 or not number.isdigit():
            return None, "Please enter a valid 16-digit card number."
        if number == DECLINE_HINTS["card"]:
            return None, "Your card was declined. Try the demo card 4111 1111 1111 1111."
    elif payment_method == "upi":
        vpa = (pay.get("vpa") or "").strip()
        if "@" not in vpa or len(vpa.split("@")[0]) < 2 or len(vpa.split("@")[1]) < 3:
            return None, "Please enter a valid UPI ID, e.g. name@okhdfcbank."
        if vpa.lower() == DECLINE_HINTS["upi"]:
            return None, "UPI payment was declined by your bank. Please try again."
    elif payment_method == "netbanking":
        if not (pay.get("bank") or "").strip():
            return None, "Please choose your bank."
    elif payment_method == "wallet":
        if not (pay.get("wallet") or "").strip():
            return None, "Please choose a wallet."

    order_number = "SL{}-{}".format(utcnow().strftime("%Y%m%d%H%M"), secrets.token_hex(2).upper())
    order = Order(
        customer_id=user.id,
        guest_email=None,
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

    # COD: collected on delivery. Online: paid instantly in demo mode;
    # with Razorpay keys, pending until the signed callback verifies.
    payment_status = "pending"
    brand = last4 = None
    if payment_method == "card":
        number = (pay.get("number") or "").replace(" ", "")
        brand = ("RuPay" if number[:2] in ("60", "65", "81", "82")
                 else "Visa" if number.startswith("4")
                 else "Mastercard" if number.startswith("5")
                 else "Card")
        last4 = number[-4:]
    elif payment_method == "upi":
        brand = "UPI"
    elif payment_method == "netbanking":
        brand = pay.get("bank", "").strip()[:40] or "Netbanking"
    elif payment_method == "wallet":
        brand = pay.get("wallet", "").strip()[:40] or "Wallet"
    if payment_method in ONLINE_METHODS and not current_app.config.get("RAZORPAY_KEY_ID"):
        payment_status = "paid"
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
        f"  - {i.quantity} x {i.product_name} ({inr(i.unit_price)} each)"
        for i in order.items
    )
    recipient_name = order.ship_name or (order.customer.name if order.customer else "there")
    body = (
        f"Hi {recipient_name},\n\n"
        f"Thanks for your order! Here is your confirmation.\n\n"
        f"Order number: {order.order_number}\n"
        f"Tracking number: {order.shipping.tracking_number}\n"
        f"Items:\n{items}\n\n"
        f"Subtotal: {inr(order.subtotal)}\n"
        f"Discount: -{inr(order.discount)}\n"
        f"GST: included in prices\n"
        f"Shipping: {inr(order.shipping_fee) if order.shipping_fee else 'FREE'}\n"
        f"Total: {inr(order.total)}\n\n"
        f"Track your order anytime from Your Account > Your Orders.\n\n"
        f"— The ShopLinq Team"
    )
    send_email(order.contact_email, f"ShopLinq order {order.order_number} confirmed", body)


def restock_order(order):
    """Return an order's items to inventory (used on cancellation/refund)."""
    for item in order.items:
        if item.product_id:
            product = db.session.get(Product, item.product_id)
            if product:
                product.stock += item.quantity


def notify_back_in_stock(product):
    """Email everyone waiting for this product and clear their subscriptions.
    Returns the number of notifications sent."""
    waiting = StockNotification.query.filter_by(
        product_id=product.id, notified=False).all()
    sent = 0
    for sub in waiting:
        send_email(
            sub.email,
            f"\u201c{product.name}\u201d is back in stock",
            f"Good news! \u201c{product.name}\u201d is available again.\n\n"
            f"Grab it here before it sells out.\n\n\u2014 The ShopLinq Team",
        )
        sub.notified = True
        sent += 1
    return sent


def create_razorpay_order(order):
    """Create a Razorpay order (amount in paise) for a placed order.

    Returns (razorpay_order_id, error). Uses the plain REST API via
    urllib so no extra SDK dependency is needed.
    """
    key_id = current_app.config.get("RAZORPAY_KEY_ID")
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        return None, "Razorpay keys are not configured."
    import json as _json
    import urllib.request as _r
    from base64 import b64encode as _b64
    payload = _json.dumps({
        "amount": int(Decimal(str(order.total)) * 100),  # paise
        "currency": "INR",
        "receipt": order.order_number,
        "notes": {"order_number": order.order_number},
    }).encode()
    req = _r.Request(
        "https://api.razorpay.com/v1/orders", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    token = _b64(f"{key_id}:{key_secret}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    try:
        with _r.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
            return data["id"], None
    except Exception as exc:
        current_app.logger.warning("Razorpay order creation failed: %s", exc)
        return None, f"Payment gateway error: {exc}"


def verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, signature):
    """Verify the HMAC-SHA256 signature Razorpay sends on payment success."""
    import hashlib
    import hmac
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET", "")
    expected = hmac.new(
        key_secret.encode(),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


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
