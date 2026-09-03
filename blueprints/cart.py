"""Cart, multi-step checkout, order placement, confirmation."""
from flask import (
    Blueprint, current_app, flash, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required

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
@login_required
def checkout():
    summary = _summary()
    if not summary["lines"]:
        flash("Your cart is empty — add some products first.", "info")
        return redirect(url_for("cart.view"))
    addresses = Address.query.filter_by(customer_id=current_user.id).all()
    if addresses:
        selected_address = addresses[0]
    else:
        selected_address = None
    return render_template(
        "checkout.html", summary=summary, addresses=addresses,
        selected_address=selected_address,
        stripe_key=current_app.config.get("STRIPE_PUBLISHABLE_KEY") or "",
    )


def _resolve_address():
    """Return (address_dict, error) from the checkout form."""
    choice = request.form.get("address_choice", "new")
    if choice.startswith("saved-"):
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
    if save:
        db.session.add(Address(customer_id=current_user.id, **fields))
        db.session.commit()
    return fields, None


@cart_bp.route("/checkout/place", methods=["POST"])
@login_required
def place():
    address, err = _resolve_address()
    if err:
        flash(err, "error")
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
        promo_code=session.get("promo"), card=card,
    )
    if err:
        flash(err, "error")
        return redirect(url_for("cart.checkout"))
    clear_cart(current_user)

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
@login_required
def stripe_success(order_number):
    order = Order.query.filter_by(
        order_number=order_number, customer_id=current_user.id
    ).first_or_404()
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
@login_required
def confirmation(order_number):
    order = Order.query.filter_by(
        order_number=order_number, customer_id=current_user.id
    ).first_or_404()
    return render_template("order_confirmation.html", order=order)
