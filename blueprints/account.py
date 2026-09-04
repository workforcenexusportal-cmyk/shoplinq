"""Customer portal: dashboard, profile, addresses, payment methods,
orders, tracking, wishlist."""
from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required

from extensions import db
from models import (
    Address, Customer, Order, PaymentMethod, Product, ProductQA, Review,
    WishlistItem,
)
from services import (
    add_to_cart, remove_from_cart, restock_order, send_email, unique_slug,
)

account_bp = Blueprint("account", __name__)


@account_bp.route("/account")
@login_required
def dashboard():
    from models import Category, OrderItem, Product
    agg = db.session.query(
        db.func.count(Order.id), db.func.sum(Order.total)
    ).filter(Order.customer_id == current_user.id,
             Order.status != "cancelled").first()
    items_bought = (
        db.session.query(db.func.sum(OrderItem.quantity))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.customer_id == current_user.id,
                Order.status != "cancelled").scalar() or 0
    )
    top_cat = (
        db.session.query(Category.name, db.func.sum(OrderItem.quantity))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Category, Category.id == Product.category_id)
        .filter(Order.customer_id == current_user.id,
                Order.status != "cancelled")
        .group_by(Category.id)
        .order_by(db.func.sum(OrderItem.quantity).desc()).first()
    )
    top_prod = (
        db.session.query(Product.name, db.func.sum(OrderItem.quantity))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(Order.customer_id == current_user.id,
                Order.status != "cancelled")
        .group_by(Product.id)
        .order_by(db.func.sum(OrderItem.quantity).desc()).first()
    )
    my_stats = {
        "orders": agg[0] or 0,
        "total_spent": agg[1] or 0,
        "items": items_bought,
        "top_category": top_cat[0] if top_cat else None,
        "top_product": top_prod[0] if top_prod else None,
    }
    recent_orders = (
        current_user.orders.order_by(Order.placed_date.desc()).limit(4).all()
    )
    default_address = Address.query.filter_by(
        customer_id=current_user.id, is_default=True).first()
    return render_template(
        "account/dashboard.html",
        recent_orders=recent_orders, default_address=default_address,
        my_stats=my_stats,
    )


@account_bp.route("/account/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "details":
            name = request.form.get("name", "").strip()
            if name:
                current_user.name = name
                db.session.commit()
                flash("Profile updated.", "success")
        elif action == "password":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            confirm = request.form.get("confirm", "")
            if not current_user.check_password(current_pw):
                flash("Current password is incorrect.", "error")
            elif len(new_pw) < 8:
                flash("New password must be at least 8 characters.", "error")
            elif new_pw != confirm:
                flash("New passwords do not match.", "error")
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash("Password changed.", "success")
        return redirect(url_for("account.profile"))
    return render_template("account/profile.html")


# ------------------------------------------------------------ addresses

def _address_from_form(form):
    return {
        "label": form.get("label", "").strip() or "Home",
        "full_name": form.get("full_name", "").strip(),
        "line1": form.get("line1", "").strip(),
        "line2": form.get("line2", "").strip(),
        "city": form.get("city", "").strip(),
        "state": form.get("state", "").strip(),
        "postal_code": form.get("postal_code", "").strip(),
        "country": form.get("country", "United States").strip() or "United States",
        "phone": form.get("phone", "").strip(),
    }


def _validate_address(data):
    return all([data["full_name"], data["line1"], data["city"], data["postal_code"]])


@account_bp.route("/account/addresses", methods=["GET", "POST"])
@login_required
def addresses():
    editing = None
    if request.method == "POST":
        address_id = request.form.get("address_id", type=int)
        data = _address_from_form(request.form)
        if not _validate_address(data):
            flash("Name, street, city and ZIP are required.", "error")
        else:
            is_default = bool(request.form.get("is_default"))
            if address_id:
                addr = db.session.get(Address, address_id)
                if not addr or addr.customer_id != current_user.id:
                    abort(403)
                for k, v in data.items():
                    setattr(addr, k, v)
            else:
                addr = Address(customer_id=current_user.id, **data)
                db.session.add(addr)
            if is_default:
                Address.query.filter_by(customer_id=current_user.id).update({"is_default": False})
                addr.is_default = True
            elif not Address.query.filter_by(
                    Address.customer_id == current_user.id,
                    Address.is_default == True).first():  # noqa: E712
                addr.is_default = True
            db.session.commit()
            flash("Address saved.", "success")
            return redirect(url_for("account.addresses"))
        editing = db.session.get(Address, address_id) if address_id else None
    else:
        edit_id = request.args.get("edit", type=int)
        if edit_id:
            editing = db.session.get(Address, edit_id)
            if not editing or editing.customer_id != current_user.id:
                abort(403)
    items = Address.query.filter_by(customer_id=current_user.id).all()
    return render_template("account/addresses.html", addresses=items, editing=editing)


@account_bp.route("/account/addresses/<int:address_id>/delete", methods=["POST"])
@login_required
def address_delete(address_id):
    addr = db.session.get(Address, address_id)
    if not addr or addr.customer_id != current_user.id:
        abort(403)
    db.session.delete(addr)
    db.session.commit()
    flash("Address removed.", "success")
    return redirect(url_for("account.addresses"))


# ------------------------------------------------------------ payment methods

@account_bp.route("/account/payment-methods", methods=["GET", "POST"])
@login_required
def payment_methods():
    if request.method == "POST":
        number = (request.form.get("card_number") or "").replace(" ", "")
        if not (number.isdigit() and len(number) in (15, 16)):
            flash("Enter a valid card number (test cards welcome).", "error")
        else:
            brand = ("Visa" if number.startswith("4")
                     else "Mastercard" if number.startswith("5")
                     else "American Express" if number.startswith("3") else "Card")
            is_default = bool(request.form.get("is_default"))
            if is_default:
                PaymentMethod.query.filter_by(
                    customer_id=current_user.id).update({"is_default": False})
            pm = PaymentMethod(
                customer_id=current_user.id, card_brand=brand, last4=number[-4:],
                exp_month=int(request.form.get("exp_month", 1) or 1),
                exp_year=int(request.form.get("exp_year", 2030) or 2030),
                is_default=is_default or PaymentMethod.query.filter_by(
                    customer_id=current_user.id).count() == 0,
            )
            db.session.add(pm)
            db.session.commit()
            flash("Card saved (only brand and last 4 digits are stored).", "success")
        return redirect(url_for("account.payment_methods"))
    items = PaymentMethod.query.filter_by(customer_id=current_user.id).all()
    return render_template("account/payment_methods.html", payment_methods=items)


@account_bp.route("/account/payment-methods/<int:pm_id>/delete", methods=["POST"])
@login_required
def payment_method_delete(pm_id):
    pm = db.session.get(PaymentMethod, pm_id)
    if not pm or pm.customer_id != current_user.id:
        abort(403)
    db.session.delete(pm)
    db.session.commit()
    flash("Card removed.", "success")
    return redirect(url_for("account.payment_methods"))


# ------------------------------------------------------------ orders

@account_bp.route("/account/orders")
@login_required
def orders():
    pagination = current_user.orders.order_by(
        Order.placed_date.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=10, error_out=False)
    return render_template("account/orders.html", pagination=pagination,
                           orders=pagination.items)


def _get_own_order(order_id):
    order = db.session.get(Order, order_id)
    if not order or order.customer_id != current_user.id:
        abort(404)
    return order


@account_bp.route("/account/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = _get_own_order(order_id)
    return render_template("account/order_detail.html", order=order)


@account_bp.route("/account/track/<int:order_id>")
@login_required
def track(order_id):
    order = _get_own_order(order_id)
    return render_template("account/tracking.html", order=order)


@account_bp.route("/account/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = _get_own_order(order_id)
    if not order.can_cancel:
        flash("This order can no longer be cancelled.", "error")
        return redirect(url_for("account.order_detail", order_id=order.id))
    order.status = "cancelled"
    restock_order(order)
    if order.shipping:
        order.shipping.status = "cancelled"
    if order.payment and order.payment.status == "paid":
        order.payment.status = "refunded"
    db.session.commit()
    send_email(
        order.contact_email,
        f"ShopLinq order {order.order_number} cancelled",
        f"Hi {order.customer.first_name if order.customer else 'there'},\n\n"
        f"Your order {order.order_number} has been cancelled"
        + (" and a refund has been issued.\n\n"
           if order.payment and order.payment.status == "refunded"
           else ".\n\n")
        + "\u2014 The ShopLinq Team",
    )
    flash("Your order has been cancelled.", "success")
    return redirect(url_for("account.order_detail", order_id=order.id))


@account_bp.route("/account/orders/<int:order_id>/return", methods=["POST"])
@login_required
def return_order(order_id):
    order = _get_own_order(order_id)
    if not order.can_return:
        flash("This order isn't eligible for a return.", "error")
        return redirect(url_for("account.order_detail", order_id=order.id))
    reason = request.form.get("reason", "").strip()
    if len(reason) < 5:
        flash("Please tell us briefly why you're returning this order.", "error")
        return redirect(url_for("account.order_detail", order_id=order.id))
    order.return_status = "requested"
    order.return_reason = reason[:1000]
    db.session.commit()
    send_email(
        order.contact_email,
        f"Return requested for order {order.order_number}",
        f"We've received your return request for order {order.order_number}.\n\n"
        f"Reason: {reason}\n\nOur team will review it shortly.\n\n"
        f"\u2014 The ShopLinq Team",
    )
    flash("Return requested — we'll email you once it's reviewed.", "success")
    return redirect(url_for("account.order_detail", order_id=order.id))


# ------------------------------------------------------------ reviews

@account_bp.route("/account/review/<int:product_id>", methods=["POST"])
@login_required
def review(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    rating = request.form.get("rating", type=int)
    if not rating or not 1 <= rating <= 5:
        flash("Please choose a star rating.", "error")
        return redirect(request.referrer or url_for("main.index"))
    review = Review.query.filter_by(
        product_id=product.id, customer_id=current_user.id).first()
    if not review:
        review = Review(product_id=product.id, customer_id=current_user.id)
        db.session.add(review)
    review.rating = rating
    review.title = request.form.get("title", "").strip()
    review.body = request.form.get("body", "").strip()
    db.session.commit()
    product.recompute_rating()
    db.session.commit()
    flash("Thanks for your review!", "success")
    return redirect(url_for("main.product", slug=product.slug) + "#reviews")


@account_bp.route("/account/questions/<int:product_id>", methods=["POST"])
@login_required
def ask_question(product_id):
    from models import Product
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    question = request.form.get("question", "").strip()
    if len(question) < 10:
        flash("Please write a slightly longer question.", "error")
    else:
        db.session.add(ProductQA(
            product_id=product.id, question=question[:400],
            author=current_user.name))
        db.session.commit()
        flash("Question submitted — our team will answer shortly.", "success")
    return redirect(url_for("main.product", slug=product.slug) + "#qa")


# ------------------------------------------------------------ wishlist

@account_bp.route("/account/wishlist")
@login_required
def wishlist():
    items = current_user.wishlist_items.all()
    return render_template("account/wishlist.html", items=items)


@account_bp.route("/account/wishlist/<int:product_id>/move-to-cart", methods=["POST"])
@login_required
def wishlist_move_to_cart(product_id):
    item = current_user.wishlist_items.filter_by(product_id=product_id).first()
    if item:
        _, err = add_to_cart(current_user, product_id)
        if err:
            flash(err, "error")
        else:
            db.session.delete(item)
            db.session.commit()
            flash("Moved to your cart.", "success")
    return redirect(url_for("account.wishlist"))


@account_bp.route("/account/wishlist/<int:product_id>/remove", methods=["POST"])
@login_required
def wishlist_remove(product_id):
    item = current_user.wishlist_items.filter_by(product_id=product_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Removed from wishlist.", "success")
    return redirect(url_for("account.wishlist"))
