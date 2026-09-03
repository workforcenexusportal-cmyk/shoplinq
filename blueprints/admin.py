"""Admin/seller dashboard: products, categories, inventory, order fulfillment."""
from functools import wraps

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required

from extensions import db
from models import (
    ORDER_STATUS_FLOW, Order, Product, ProductImage, Category, Review,
    STATUS_LABELS, utcnow,
)
from services import send_email, unique_slug

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route("/")
@admin_required
def index():
    revenue = db.session.query(db.func.sum(Order.total)).filter(
        Order.status != "cancelled").scalar() or 0
    low_stock = Product.query.filter(Product.stock <= 5).order_by(Product.stock).limit(8).all()
    recent_orders = Order.query.order_by(Order.placed_date.desc()).limit(8).all()
    stats = {
        "customers": db.session.query(db.func.count(
            __import__("models").Customer.id)).scalar(),
        "products": Product.query.count(),
        "orders": Order.query.count(),
        "revenue": revenue,
    }
    return render_template(
        "admin/dashboard.html", stats=stats, low_stock=low_stock,
        recent_orders=recent_orders,
    )


# ------------------------------------------------------------ products

@admin_bp.route("/products")
@admin_required
def products():
    q = request.args.get("q", "").strip()
    query = Product.query
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    pagination = query.order_by(Product.id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=15, error_out=False)
    return render_template("admin/products.html",
                           pagination=pagination, products=pagination.items)


def _apply_product_form(product, form):
    product.name = form.get("name", "").strip()
    product.brand = form.get("brand", "").strip()
    product.description = form.get("description", "").strip()
    product.price = float(form.get("price") or 0)
    deal_price = form.get("deal_price", "").strip()
    product.deal_price = float(deal_price) if deal_price else None
    product.stock = max(int(form.get("stock") or 0), 0)
    product.category_id = int(form.get("category_id") or 0)
    product.is_deal = bool(form.get("is_deal"))
    product.is_featured = bool(form.get("is_featured"))
    if not product.name or not product.category_id or product.price <= 0:
        return "Name, price and category are required."
    if not product.slug:
        product.slug = unique_slug(Product, product.name)
    db.session.add(product)  # no-op when editing an existing product
    db.session.flush()  # assigns PK on new products before image rows are written
    urls = [u.strip() for u in form.get("image_urls", "").splitlines() if u.strip()]
    ProductImage.query.filter_by(product_id=product.id).delete()
    for idx, url in enumerate(urls[:8]):
        db.session.add(ProductImage(
            product_id=product.id, url=url, alt=product.name,
            is_primary=(idx == 0), sort_order=idx))
    return None


@admin_bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_new():
    if request.method == "POST":
        product = Product()
        err = _apply_product_form(product, request.form)
        if err:
            db.session.rollback()
            flash(err, "error")
        else:
            db.session.commit()
            flash(f"Product “{product.name}” created.", "success")
            return redirect(url_for("admin.products"))
    categories = _category_choices()
    return render_template("admin/product_form.html", product=None,
                           categories=categories)


def _category_choices():
    out = []
    roots = Category.query.filter_by(parent_id=None).order_by(Category.name).all()
    for root in roots:
        out.append((root.id, root.name))
        for child in sorted(root.children, key=lambda c: c.name):
            out.append((child.id, f"{root.name} › {child.name}"))
    return out


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if request.method == "POST":
        err = _apply_product_form(product, request.form)
        if err:
            flash(err, "error")
        else:
            db.session.commit()
            flash("Product updated.", "success")
            return redirect(url_for("admin.products"))
    categories = _category_choices()
    return render_template("admin/product_form.html", product=product,
                           categories=categories)


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def product_delete(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    Review.query.filter_by(product_id=product.id).delete()
    ProductImage.query.filter_by(product_id=product.id).delete()
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin.products"))


# ------------------------------------------------------------ categories

@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    editing = None
    if request.method == "POST":
        cat_id = request.form.get("category_id", type=int)
        name = request.form.get("name", "").strip()
        parent_id = request.form.get("parent_id", type=int) or None
        if not name:
            flash("Category name is required.", "error")
        else:
            if cat_id:
                cat = db.session.get(Category, cat_id)
                if not cat:
                    abort(404)
                cat.name = name
                cat.parent_id = parent_id
                cat.slug = unique_slug(Category, name) if name != cat.name else cat.slug
            else:
                cat = Category(name=name, slug=unique_slug(Category, name),
                               parent_id=parent_id)
                db.session.add(cat)
            db.session.commit()
            flash("Category saved.", "success")
            return redirect(url_for("admin.categories"))
        editing = db.session.get(Category, cat_id) if cat_id else None
    else:
        edit_id = request.args.get("edit", type=int)
        if edit_id:
            editing = db.session.get(Category, edit_id)
    roots = Category.query.filter_by(parent_id=None).order_by(Category.name).all()
    return render_template("admin/categories.html", roots=roots, editing=editing)


@admin_bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@admin_required
def category_delete(cat_id):
    cat = db.session.get(Category, cat_id) or abort(404)
    if cat.children:
        flash("Delete or move the subcategories first.", "error")
    elif cat.products.count():
        flash("Category still has products — reassign them first.", "error")
    else:
        db.session.delete(cat)
        db.session.commit()
        flash("Category deleted.", "success")
    return redirect(url_for("admin.categories"))


# ------------------------------------------------------------ orders / fulfillment

@admin_bp.route("/orders")
@admin_required
def orders():
    status = request.args.get("status", "")
    query = Order.query
    if status:
        query = query.filter_by(status=status)
    pagination = query.order_by(Order.placed_date.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=15, error_out=False)
    return render_template("admin/orders.html",
                           pagination=pagination, orders=pagination.items,
                           statuses=STATUS_LABELS, current_status=status)


@admin_bp.route("/orders/<int:order_id>")
@admin_required
def order_detail(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    return render_template("admin/order_detail.html", order=order,
                           status_flow=ORDER_STATUS_FLOW,
                           status_labels=STATUS_LABELS)


@admin_bp.route("/orders/<int:order_id>/update", methods=["POST"])
@admin_required
def order_update(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    new_status = request.form.get("status", "")
    if new_status not in ORDER_STATUS_FLOW + ["cancelled"]:
        flash("Unknown status.", "error")
        return redirect(url_for("admin.order_detail", order_id=order.id))
    order.status = new_status
    shipping = order.shipping
    if shipping:
        tracking = request.form.get("tracking_number", "").strip()
        if tracking:
            shipping.tracking_number = tracking
        carrier = request.form.get("carrier", "").strip()
        if carrier:
            shipping.carrier = carrier
        if new_status != "cancelled":
            shipping.record(new_status)
    if new_status == "delivered" and order.payment and order.payment.method == "cod":
        order.payment.status = "paid"
        order.payment.paid_date = utcnow()
    db.session.commit()

    if shipping and new_status != "cancelled":
        send_email(
            order.customer.email,
            f"ShopLinq order {order.order_number}: {STATUS_LABELS[new_status]}",
            f"Hi {order.customer.first_name},\n\nYour order {order.order_number} is now: "
            f"{STATUS_LABELS[new_status]}.\nTracking number: {shipping.tracking_number}\n\n"
            f"— The ShopLinq Team")
    flash("Order updated.", "success")
    return redirect(url_for("admin.order_detail", order_id=order.id))


# ------------------------------------------------------------ analytics

@admin_bp.route("/analytics")
@admin_required
def analytics():
    """Monthly sales, top products, and review analysis."""
    from models import OrderItem
    month_expr = db.func.strftime("%Y-%m", Order.placed_date)
    monthly = (
        db.session.query(
            month_expr.label("month"),
            db.func.count(Order.id).label("orders"),
            db.func.sum(Order.total).label("revenue"),
        )
        .filter(Order.status != "cancelled")
        .group_by(month_expr).order_by(month_expr.desc()).limit(6).all()
    )
    units_by_month = dict(
        db.session.query(month_expr, db.func.sum(OrderItem.quantity))
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(Order.status != "cancelled")
        .group_by(month_expr).all()
    )
    units = db.func.sum(OrderItem.quantity)
    revenue = db.func.sum(OrderItem.quantity * OrderItem.unit_price)
    top_products = (
        db.session.query(Product, units.label("units"), revenue.label("revenue"))
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status != "cancelled")
        .group_by(Product.id).order_by(db.desc(units)).limit(10).all()
    )
    from models import Review as _Review
    recent_reviews = _Review.query.order_by(_Review.created_date.desc()).limit(10).all()
    rating_dist = dict(
        db.session.query(_Review.rating, db.func.count(_Review.id))
        .group_by(_Review.rating).all()
    )
    avg_catalog_rating = db.session.query(db.func.avg(Product.rating)).filter(
        Product.rating_count > 0).scalar()
    return render_template(
        "admin/analytics.html", monthly=monthly, units_by_month=units_by_month,
        top_products=top_products, recent_reviews=recent_reviews,
        rating_dist=rating_dist, avg_catalog_rating=avg_catalog_rating,
    )
