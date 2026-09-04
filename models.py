"""ShopLinq data models."""
import json
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


ORDER_STATUS_FLOW = ["placed", "packed", "shipped", "out_for_delivery", "delivered"]
STATUS_LABELS = {
    "placed": "Placed",
    "packed": "Packed",
    "shipped": "Shipped",
    "out_for_delivery": "Out for Delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}
RETURN_STATUS_LABELS = {
    "none": "",
    "requested": "Return requested",
    "approved": "Return approved",
    "rejected": "Return rejected",
    "refunded": "Refunded",
}


class Customer(UserMixin, db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_date = db.Column(db.DateTime, default=utcnow)

    addresses = db.relationship("Address", backref="customer", lazy=True,
                                order_by="Address.id")
    orders = db.relationship("Order", backref="customer", lazy="dynamic")
    cart = db.relationship("Cart", backref="customer", uselist=False)
    payment_methods = db.relationship("PaymentMethod", backref="customer", lazy=True)
    wishlist_items = db.relationship("WishlistItem", backref="customer", lazy="dynamic")
    reviews = db.relationship("Review", backref="customer", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def first_name(self):
        return self.name.split(" ")[0]


class Address(db.Model):
    __tablename__ = "addresses"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    label = db.Column(db.String(60), default="Home")
    full_name = db.Column(db.String(120), nullable=False)
    line1 = db.Column(db.String(255), nullable=False)
    line2 = db.Column(db.String(255))
    city = db.Column(db.String(120), nullable=False)
    state = db.Column(db.String(120))
    postal_code = db.Column(db.String(30), nullable=False)
    country = db.Column(db.String(120), default="United States")
    phone = db.Column(db.String(40))
    is_default = db.Column(db.Boolean, default=False)

    def as_dict(self):
        return {
            "full_name": self.full_name, "line1": self.line1, "line2": self.line2,
            "city": self.city, "state": self.state,
            "postal_code": self.postal_code, "country": self.country,
            "phone": self.phone,
        }

    def one_line(self):
        parts = [self.line1, self.line2, self.city, self.state, self.postal_code]
        return ", ".join([p for p in parts if p])


class PaymentMethod(db.Model):
    __tablename__ = "payment_methods"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    card_brand = db.Column(db.String(40), nullable=False)
    last4 = db.Column(db.String(4), nullable=False)
    exp_month = db.Column(db.Integer, nullable=False)
    exp_year = db.Column(db.Integer, nullable=False)
    is_default = db.Column(db.Boolean, default=False)


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True)

    parent = db.relationship("Category", remote_side=[id], backref="children")
    products = db.relationship("Product", backref="category", lazy="dynamic")

    @property
    def path(self):
        node, parts = self, []
        while node:
            parts.append(node.name)
            node = node.parent
        return " > ".join(reversed(parts))


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    description = db.Column(db.Text, default="")
    brand = db.Column(db.String(100), index=True)
    price = db.Column(db.Float, nullable=False, index=True)
    deal_price = db.Column(db.Float)
    stock = db.Column(db.Integer, default=0, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    is_deal = db.Column(db.Boolean, default=False, index=True)
    is_featured = db.Column(db.Boolean, default=False, index=True)
    rating = db.Column(db.Float, default=0.0, index=True)
    primary_image_url = db.Column(db.String(500))
    rating_count = db.Column(db.Integer, default=0)
    created_date = db.Column(db.DateTime, default=utcnow)

    images = db.relationship("ProductImage", backref="product", lazy=True,
                            order_by="ProductImage.sort_order")
    reviews = db.relationship("Review", backref="product", lazy="dynamic")
    questions = db.relationship("ProductQA", backref="product", lazy=True)

    @property
    def effective_price(self):
        if self.is_deal and self.deal_price:
            return self.deal_price
        return self.price

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def primary_image(self):
        for img in self.images:
            if img.is_primary:
                return img
        return self.images[0] if self.images else None

    @property
    def image_url(self):
        """Single fast image URL for cards/lists (no N+1 on the images table)."""
        if self.primary_image_url:
            return self.primary_image_url
        img = self.primary_image
        if img:
            return img.url
        return "/static/images/placeholder.svg"

    def recompute_rating(self):
        agg = db.session.query(
            db.func.avg(Review.rating), db.func.count(Review.id)
        ).filter(Review.product_id == self.id).first()
        self.rating = round(agg[0] or 0.0, 2)
        self.rating_count = agg[1] or 0


class ProductImage(db.Model):
    __tablename__ = "product_images"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    alt = db.Column(db.String(200))
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)


class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160))
    body = db.Column(db.Text)
    created_date = db.Column(db.DateTime, default=utcnow)
    __table_args__ = (db.UniqueConstraint("product_id", "customer_id"),)


class ProductQA(db.Model):
    __tablename__ = "product_qa"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    question = db.Column(db.String(400), nullable=False)
    answer = db.Column(db.Text)
    author = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=utcnow)


class Cart(db.Model):
    __tablename__ = "carts"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), unique=True, nullable=False)
    items = db.relationship("CartItem", backref="cart", lazy=True, cascade="all, delete-orphan")


class CartItem(db.Model):
    __tablename__ = "cart_items"
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey("carts.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    product = db.relationship("Product")
    __table_args__ = (db.UniqueConstraint("cart_id", "product_id"),)


class WishlistItem(db.Model):
    __tablename__ = "wishlist_items"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product = db.relationship("Product")
    __table_args__ = (db.UniqueConstraint("customer_id", "product_id"),)


class PromoCode(db.Model):
    __tablename__ = "promo_codes"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    discount_percent = db.Column(db.Integer, nullable=False)
    min_spend = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)


class StockNotification(db.Model):
    __tablename__ = "stock_notifications"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)
    created_date = db.Column(db.DateTime, default=utcnow)
    notified = db.Column(db.Boolean, default=False)


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    guest_email = db.Column(db.String(255))
    order_number = db.Column(db.String(40), unique=True, nullable=False)
    status = db.Column(db.String(30), default="placed", nullable=False, index=True)
    return_status = db.Column(db.String(20), default="none", nullable=False)
    return_reason = db.Column(db.Text)
    subtotal = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0.0)
    promo_code = db.Column(db.String(40))
    tax = db.Column(db.Float, default=0.0)
    shipping_fee = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, nullable=False)
    delivery_method = db.Column(db.String(30), default="standard")
    placed_date = db.Column(db.DateTime, default=utcnow, index=True)
    # Shipping address snapshot
    ship_name = db.Column(db.String(120))
    ship_line1 = db.Column(db.String(255))
    ship_line2 = db.Column(db.String(255))
    ship_city = db.Column(db.String(120))
    ship_state = db.Column(db.String(120))
    ship_postal_code = db.Column(db.String(30))
    ship_country = db.Column(db.String(120))
    ship_phone = db.Column(db.String(40))

    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")
    shipping = db.relationship("Shipping", backref="order", uselist=False, cascade="all, delete-orphan")
    payment = db.relationship("Payment", backref="order", uselist=False, cascade="all, delete-orphan")

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status.title())

    @property
    def return_label(self):
        return RETURN_STATUS_LABELS.get(self.return_status, "")

    @property
    def can_cancel(self):
        return self.status in ("placed", "packed")

    @property
    def can_return(self):
        return self.status == "delivered" and self.return_status in ("none", "rejected")

    @property
    def contact_email(self):
        return self.customer.email if self.customer else self.guest_email


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), index=True)
    product_name = db.Column(db.String(200), nullable=False)
    product_slug = db.Column(db.String(220))
    image_url = db.Column(db.String(500))
    unit_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)


class Shipping(db.Model):
    __tablename__ = "shipping"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    tracking_number = db.Column(db.String(60), unique=True)
    carrier = db.Column(db.String(60), default="ShopLinq Express")
    status = db.Column(db.String(30), default="placed", nullable=False)
    estimated_delivery = db.Column(db.DateTime)
    updated_date = db.Column(db.DateTime, default=utcnow)
    history_json = db.Column(db.Text, default="[]")

    @property
    def history(self):
        try:
            return json.loads(self.history_json or "[]")
        except (TypeError, ValueError):
            return []

    def record(self, status, when=None):
        self.status = status
        self.updated_date = when or utcnow()
        hist = self.history
        hist.append({"status": status, "at": self.updated_date.isoformat()})
        self.history_json = json.dumps(hist)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    method = db.Column(db.String(30), nullable=False)  # card | cod
    status = db.Column(db.String(30), default="pending", nullable=False)  # pending | paid | failed
    amount = db.Column(db.Float, nullable=False)
    provider_ref = db.Column(db.String(120))
    card_brand = db.Column(db.String(40))
    last4 = db.Column(db.String(4))
    paid_date = db.Column(db.DateTime)
