"""Cart, multi-step checkout, order placement, confirmation."""
from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required

from extensions import db, limiter
from models import Address, Order
from services import (
    ONLINE_METHODS, cart_summary, clear_cart, create_order,
    create_razorpay_order, verify_razorpay_signature,
)
from models import utcnow

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
    if not current_user.is_authenticated:
        flash("Please sign in or create an account to place your order.", "info")
        return redirect(url_for("auth.login", next=url_for("cart.checkout")))
    summary = _summary()
    if not summary["lines"]:
        flash("Your cart is empty — add some products first.", "info")
        return redirect(url_for("cart.view"))
    addresses = Address.query.filter_by(customer_id=current_user.id).all()
    selected_address = addresses[0] if addresses else None
    from services import EXPRESS_SHIPPING, FREE_SHIPPING_THRESHOLD, STANDARD_SHIPPING
    return render_template(
        "checkout.html", summary=summary, addresses=addresses,
        selected_address=selected_address,
        razorpay_key=current_app.config.get("RAZORPAY_KEY_ID") or "",
        standard_fee=STANDARD_SHIPPING, express_fee=EXPRESS_SHIPPING,
        free_threshold=FREE_SHIPPING_THRESHOLD,
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
        "country": request.form.get("country", "India").strip() or "India",
        "phone": request.form.get("phone", "").strip(),
    }
    if not fields["full_name"] or not fields["line1"] or not fields["city"] or not fields["postal_code"]:
        return None, "Please complete the shipping address (name, street, city, ZIP)."
    save = request.form.get("save_address")
    if save and current_user.is_authenticated:
        db.session.add(Address(customer_id=current_user.id, **fields))
        db.session.commit()
    return fields, None


def _get_viewable_order(order_number):
    """Return one of the signed-in customer's own orders, or 404."""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if current_user.is_authenticated and order.customer_id == current_user.id:
        return order
    abort(404)


@cart_bp.route("/checkout/place", methods=["POST"])
@login_required
@limiter.limit("30 per hour; 8 per minute")
def place():
    address, err = _resolve_address()
    if err:
        flash(err, "error")
        return redirect(url_for("cart.checkout"))
    delivery = request.form.get("delivery", "standard")
    if delivery not in ("standard", "express"):
        delivery = "standard"
    payment_method = request.form.get("payment", "upi")
    if payment_method not in ONLINE_METHODS + ("cod",):
        payment_method = "upi"
    pay = {
        "vpa": request.form.get("upi_vpa", ""),
        "number": request.form.get("card_number", ""),
        "bank": request.form.get("netbanking_bank", ""),
        "wallet": request.form.get("wallet_choice", ""),
    }
    order, err = create_order(
        current_user, address=address, delivery_method=delivery,
        payment_method=payment_method,
        promo_code=session.get("promo"), pay=pay,
    )
    if err:
        flash(err, "error")
        return redirect(url_for("cart.checkout"))
    clear_cart(current_user)

    # Razorpay configured: send online payments through the gateway.
    if payment_method in ONLINE_METHODS and current_app.config.get("RAZORPAY_KEY_ID"):
        rp_order_id, rp_err = create_razorpay_order(order)
        if rp_order_id:
            order.payment.provider_ref = rp_order_id
            order.payment.status = "pending"
            db.session.commit()
            return redirect(url_for("cart.pay", order_number=order.order_number))
        # Gateway error → keep the order, let the customer retry payment.
        order.payment.status = "pending"
        db.session.commit()
        flash(f"Order {order.order_number} is placed, but the payment gateway "
              f"could not be reached ({rp_err}). Please retry from your orders.",
              "error")
        return redirect(url_for("cart.confirmation", order_number=order.order_number))

    flash(f"Order {order.order_number} placed! A confirmation email is on its way.", "success")
    return redirect(url_for("cart.confirmation", order_number=order.order_number))


@cart_bp.route("/pay/<order_number>")
def pay(order_number):
    """Razorpay Checkout page for a placed order awaiting payment."""
    order = _get_viewable_order(order_number)
    if not (order and order.payment):
        abort(404)
    if order.payment.status == "paid":
        return redirect(url_for("cart.confirmation", order_number=order.order_number))
    if not order.payment.provider_ref or not current_app.config.get("RAZORPAY_KEY_ID"):
        abort(404)
    return render_template(
        "pay.html", order=order,
        razorpay_key=current_app.config["RAZORPAY_KEY_ID"],
    )


@cart_bp.route("/pay/<order_number>/verify", methods=["POST"])
def pay_verify(order_number):
    """Verify the Razorpay signature and mark the order paid."""
    order = _get_viewable_order(order_number)
    if not (order and order.payment):
        abort(404)
    rp_order_id = request.form.get("razorpay_order_id", "")
    rp_payment_id = request.form.get("razorpay_payment_id", "")
    signature = request.form.get("razorpay_signature", "")
    if rp_order_id != (order.payment.provider_ref or ""):
        flash("Payment could not be verified — unknown payment reference.", "error")
        return redirect(url_for("cart.confirmation", order_number=order.order_number))
    if not verify_razorpay_signature(rp_order_id, rp_payment_id, signature):
        order.payment.status = "failed"
        db.session.commit()
        flash("Payment verification failed. If money was deducted it will "
              "be auto-refunded by your bank within 5-7 business days.", "error")
        return redirect(url_for("cart.confirmation", order_number=order.order_number))
    order.payment.status = "paid"
    order.payment.paid_date = utcnow()
    db.session.commit()
    flash("Payment received \u2014 thank you!", "success")
    return redirect(url_for("cart.confirmation", order_number=order.order_number))


@cart_bp.route("/order-confirmation/<order_number>")
def confirmation(order_number):
    order = _get_viewable_order(order_number)
    return render_template("order_confirmation.html", order=order)


