"""Cart, multi-step checkout, order placement, confirmation."""
from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user

from extensions import db
from models import Address, Order
from services import (
    cart_summary, clear_cart, create_order, create_stripe_session,
)

cart_bp = Blueprint("cart", __name__)


def _summary(delivery=None):
    promo = session.get("promo") or None
    if not promo:
        promo = None
    if delivery is None:
        delivery = session.get("delivery", "standard")
    return cart_summary(current_user, delivery, promo)


@cart_bp.route("/cart")
def view():
    summary = _summary()
    return render_template("cart.html", summary=summary)


@cart_bp.route("/checkout")
def checkout():
    summary = _summary()
    if not summary["lines"]:
        flash("Your cart is empty — add some products first.", "info")
        return redirect(url_for("cart.view"))
    if current_user.is_authenticated:
        addresses = Address.query.filter_by(customer_id=current_user.id).all()
        selected_address = addresses[0] if addresses else None
    else:
        addresses = []
        selected_address = None
    return render_template(
        "checkout.html", summary=summary, addresses=addresses,
        selected_address=selected_address,
        stripe_key=current_app.config.get("STRIPE_PUBLISHABLE_KEY") or "",
    )


def _resolve_address():
    """Return (address_dict, error) from the checkout form."""
    choice = request.form.get("address_choice", "new")
    if choice.startswith("saved-") and current_user.is_authenticated:
        addr = db.session.get(Address, int(choice.split("-")[1]))
        if not addr or addr.customer_id != current_user.id:
            return None, "Invalid address selected."
        return addr.as_dict(), None
    fields = {
        "full_name": request.form.get("full_name", "").strip(),
        "line1": request.form.get("line1", "").strip(),
        "line2": request.form.get("line2", "").strip(),
        "city": request.form.get("city", "").strip(),
        "state": request.form.get("state", "").strip(),
        "postal_code": request.form.get("postal_code", "").strip(),
        "country": request.form.get("country", "United States").strip() or "United States",
        "phone": request.form.get("phone", "").strip(),
    }
    if not fields["full_name"] or not fields["line1"] or not fields["city"] or not fields["postal_code"]:
        return None, "Please complete the shipping address (name, street, city, ZIP)."
    save = request.form.get("save_address")
    if save and current_user.is_authenticated:
        db.session.add(Address(customer_id=current_user.id, **fields))
        db.session.commit()
    return fields, None


def _remember_guest_order(order_number):
    """Track a guest's order numbers in the session so they can view it."""
    orders = session.get("guest_orders", [])
    if order_number not in orders:
        orders.append(order_number)
        session["guest_orders"] = orders[-20:]
        session.modified = True


def _get_viewable_order(order_number):
    """Return an order the current visitor is allowed to see, or 404."""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if current_user.is_authenticated and order.customer_id == current_user.id:
        return order
    if order.customer_id is None and order_number in session.get("guest_orders", []):
        return order
    abort(404)


@cart_bp.route("/checkout/place", methods=["POST"])
def place():
    address, err = _resolve_address()
    if err:
        flash(err, "error")
        return redirect(url_for("cart.checkout"))
    guest_email = None
    if not current_user.is_authenticated:
        guest_email = request.form.get("guest_email", "").strip().lower()
        if "@" not in guest_email or "." not in guest_email:
            flash("Please enter a valid email address for your order.", "error")
            return redirect(url_for("cart.checkout"))
    delivery = request.form.get("delivery", "standard")
    if delivery not in ("standard", "express"):
        delivery = "standard"
    payment_method = request.form.get("payment", "card")
    if payment_method not in ("card", "cod"):
        payment_method = "card"
    card = {
        "number": request.form.get("card_number", ""),
        "exp_month": request.form.get("exp_month", ""),
        "exp_year": request.form.get("exp_year", ""),
        "cvc": request.form.get("cvc", ""),
    }
    order, err = create_order(
        current_user, address=address, delivery_method=delivery,
        payment_method=payment_method,
        promo_code=session.get("promo"), card=card, guest_email=guest_email,
    )
    if err:
        flash(err, "error")
        return redirect(url_for("cart.checkout"))
    clear_cart(current_user)
    if order.customer_id is None:
        _remember_guest_order(order.order_number)

    # If Stripe is configured and the customer chose card, redirect to Stripe Checkout.
    if payment_method == "card" and current_app.config.get("STRIPE_SECRET_KEY"):
        try:
            stripe_session = create_stripe_session(order)
            if stripe_session:
                order.payment.provider_ref = stripe_session.id
                order.payment.status = "pending"
                db.session.commit()
                return redirect(stripe_session.url, code=303)
        except Exception as exc:  # Stripe outage → fall back to demo mode
            current_app.logger.warning("Stripe checkout failed (%s); simulating payment.", exc)

    flash(f"Order {order.order_number} placed! A confirmation email is on its way.", "success")
    return redirect(url_for("cart.confirmation", order_number=order.order_number))


@cart_bp.route("/checkout/stripe-success/<order_number>")
def stripe_success(order_number):
    order = _get_viewable_order(order_number)
    ref = order.payment.provider_ref if order.payment else None
    key = current_app.config.get("STRIPE_SECRET_KEY")
    if ref and key:
        import stripe
        stripe.api_key = key
        try:
            stripe_session = stripe.checkout.Session.retrieve(ref)
            if stripe_session.payment_status == "paid":
                order.payment.status = "paid"
                from models import utcnow
                order.payment.paid_date = utcnow()
                db.session.commit()
                flash("Payment received — thanks!", "success")
        except Exception as exc:
            current_app.logger.warning("Could not verify Stripe session: %s", exc)
    return redirect(url_for("cart.confirmation", order_number=order.order_number))


@cart_bp.route("/order-confirmation/<order_number>")
def confirmation(order_number):
    order = _get_viewable_order(order_number)
    return render_template("order_confirmation.html", order=order)


@cart_bp.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    """Receive Stripe events and mark orders paid on completed checkout."""
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        import stripe
        if secret:
            event = stripe.Webhook.construct_event(payload, sig, secret)
        else:  # No signing secret configured — parse without verification.
            event = stripe.Event.construct_from(request.get_json(force=True), None)
    except Exception as exc:
        current_app.logger.warning("Invalid Stripe webhook: %s", exc)
        abort(400)

    if event["type"] == "checkout.session.completed":
        data = event["data"]["object"]
        session_id = data.get("id")
        order = Order.query.filter(
            Order.payment.has(provider_ref=session_id)).first()
        if order and order.payment and order.payment.status != "paid":
            order.payment.status = "paid"
            from models import utcnow
            order.payment.paid_date = utcnow()
            db.session.commit()
            current_app.logger.info("Stripe webhook marked %s paid.", order.order_number)
    return "", 200
