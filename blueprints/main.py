"""Main catalog routes: homepage, product listing, product detail."""
from flask import Blueprint, abort, render_template, request
from flask_login import current_user

from extensions import db
from models import Category, Product, ProductQA, Review
from services import (
    cache_get, cache_set, get_brand_list, get_category_counts, get_nav_tree,
    get_recently_viewed, record_recently_viewed,
)

main_bp = Blueprint("main", __name__)

SORTS = {
    "featured": (Product.rating.desc(), Product.rating_count.desc()),
    "price_asc": (Product.price.asc(),),
    "price_desc": (Product.price.desc(),),
    "rating": (Product.rating.desc(), Product.rating_count.desc()),
    "newest": (Product.created_date.desc(),),
}
PER_PAGE = 24


@main_bp.route("/")
def index():
    """Homepage rows are cached for a few minutes — with 5,000+ products
    we don't want every visitor re-running the heavy picks."""
    deals = cache_get("home_deals")
    if deals is None:
        deals = (Product.query.filter(Product.is_deal.is_(True), Product.stock > 0)
                 .order_by(db.func.random()).limit(8).all())
        cache_set("home_deals", deals, ttl=180)
    recommended = cache_get("home_reco")
    if recommended is None:
        recommended = (Product.query.filter(Product.rating >= 4.2, Product.stock > 0)
                       .order_by(Product.rating_count.desc()).limit(12).all())
        cache_set("home_reco", recommended, ttl=300)
    new_arrivals = cache_get("home_new")
    if new_arrivals is None:
        new_arrivals = Product.query.order_by(Product.created_date.desc()).limit(8).all()
        cache_set("home_new", new_arrivals, ttl=300)
    return render_template(
        "index.html", deals=deals, recommended=recommended,
        new_arrivals=new_arrivals, recently_viewed=get_recently_viewed(limit=8),
    )


def _category_ids(category):
    return [category.id] + [c.id for c in category.children]


@main_bp.route("/products")
@main_bp.route("/category/<slug>")
def products(slug=None):
    page = max(1, request.args.get("page", 1, type=int) or 1)
    sort = request.args.get("sort", "featured")
    q = request.args.get("q", "").strip()[:100]
    category = None
    query = Product.query

    if slug:
        category = Category.query.filter_by(slug=slug).first_or_404()
        query = query.filter(Product.category_id.in_(_category_ids(category)))
    else:
        cat_arg = request.args.get("category", type=int)
        if cat_arg:
            category = db.session.get(Category, cat_arg)
            if category:
                query = query.filter(Product.category_id.in_(_category_ids(category)))

    if request.args.get("deals", type=int):
        query = query.filter(Product.is_deal.is_(True))

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Product.name.ilike(like), Product.brand.ilike(like),
                   Product.description.ilike(like))
        )
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    brands = request.args.getlist("brand")
    if brands:
        query = query.filter(Product.brand.in_(brands))

    min_rating = request.args.get("rating", type=float)
    if min_rating:
        query = query.filter(Product.rating >= min_rating)

    if request.args.get("in_stock"):
        query = query.filter(Product.stock > 0)

    order_cols = SORTS.get(sort, SORTS["featured"])
    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)

    return render_template(
        "products.html", pagination=pagination, products=pagination.items,
        all_brands=get_brand_list(), root_categories=get_nav_tree(),
        category_counts=get_category_counts(),
        current_category=category, current_sort=sort, query=q,
    )


@main_bp.route("/product/<slug>")
def product(slug):
    p = Product.query.filter_by(slug=slug).first_or_404()
    related = (
        Product.query.filter(
            Product.category_id == p.category_id, Product.id != p.id
        ).order_by(Product.rating.desc()).limit(6).all()
    )
    reviews = p.reviews.order_by(Review.created_date.desc()).limit(8).all()
    my_review = None
    if current_user.is_authenticated:
        my_review = Review.query.filter_by(
            product_id=p.id, customer_id=current_user.id).first()
    recently_viewed = get_recently_viewed(exclude_id=p.id, limit=6)
    record_recently_viewed(p.id)
    return render_template(
        "product.html", product=p, related=related,
        reviews=reviews, my_review=my_review, qa=p.questions,
        recently_viewed=recently_viewed,
    )


# ------------------------------------------------------------------
# Static info pages (about, shipping, returns, FAQ, contact, legal)
# ------------------------------------------------------------------
INFO_PAGES = {
    "about": {
        "title": "About ShopLinq",
        "subtitle": "A marketplace built around one idea: everything you need, delivered well.",
        "blocks": [
            {"text": "ShopLinq started in 2024 as a small marketplace with a simple promise "
                     "&mdash; honest prices, fast delivery, and a shopping experience that "
                     "respects your time. Today we list thousands of products across 22 "
                     "departments, from electronics to garden supplies."},
            {"heading": "What we stand for",
             "list": [
                 "<strong>Fair pricing.</strong> Deals you can actually verify &mdash; every "
                 "discount is shown against the real list price.",
                 "<strong>Fast, tracked delivery.</strong> Standard delivery in 5 business "
                 "days, express in 2, with a tracking timeline on every order.",
                 "<strong>Easy returns.</strong> 30 days to change your mind, prepaid return "
                 "labels, refunds processed within 3 business days.",
                 "<strong>Human support.</strong> Real people answer email and phone, "
                 "Monday to Friday.",
             ]},
            {"heading": "By the numbers",
             "rows": [("Products listed", "5,000+"), ("Product categories", "250+"),
                      ("Customers served", "120,000+"), ("Countries shipped to", "38"),
                      ("Average rating", "4.6 / 5")]},
        ],
    },
    "shipping": {
        "title": "Shipping & Delivery",
        "subtitle": "Where your order is, and when it gets there.",
        "blocks": [
            {"heading": "Delivery options",
             "rows": [("Standard delivery", "5 business days &mdash; FREE over &#8377;999, otherwise &#8377;79"),
                      ("Express delivery", "2 business days &mdash; &#8377;199"),
                      ("Cash on delivery", "Available on orders up to &#8377;50,000")]},
            {"heading": "Order processing",
             "text": "Orders placed before 14:00 IST are picked and packed the same day. "
                     "You receive a confirmation email immediately and a tracking "
                     "number as soon as the parcel leaves our fulfillment center."},
            {"heading": "Things to know",
             "list": [
                 "We currently ship to all 28 states and 8 union territories across India.",
                 "Large items (furniture, gym equipment) may add 2&ndash;4 days.",
                 "COD is available on orders up to &#8377;50,000.",
                 "Delivery timelines exclude public holidays.",
             ]},
        ],
    },
    "returns-policy": {
        "title": "Returns & Refunds",
        "subtitle": "Changed your mind? No problem.",
        "blocks": [
            {"heading": "The short version",
             "text": "You have 30 days from delivery to return almost anything. Items must "
                     "be unused and in original packaging. Refunds are issued to your "
                     "original payment method within 3 business days of the return "
                     "arriving at our warehouse."},
            {"heading": "How to return an item",
             "list": [
                 "Open <strong>Your Orders</strong> in your account and pick the order.",
                 "Click <strong>Request return</strong>, choose a reason, and submit.",
                 "Print the prepaid label from the confirmation email.",
                 "Drop the parcel at any partner location &mdash; tracking starts automatically.",
             ]},
            {"heading": "Exceptions",
             "list": [
                 "Grocery and personal-care items can only be returned unopened.",
                 "Customized products are final sale.",
                 "Damaged or wrong item? We refund instantly and cover the return.",
             ]},
        ],
    },
    "faq": {
        "title": "Frequently Asked Questions",
        "subtitle": "The questions our support team hears most.",
        "blocks": [
            {"heading": "Do I need an account to order?",
             "text": "Yes &mdash; an account keeps your order history, saved addresses, "
                     "wishlist and payment status in one place, and makes checkout faster."},
            {"heading": "Which payment methods do you accept?",
             "text": "UPI (GPay, PhonePe, Paytm, BHIM), cards (RuPay, Visa, Mastercard, Amex), "
                     "netbanking from all major Indian banks, wallets, and cash on delivery. "
                     "Online payments are collected by Razorpay and card details never "
                     "touch our servers."},
            {"heading": "Can I change or cancel my order?",
             "text": "You can cancel from Your Orders until the status changes to "
                     "Packed. After that, refuse the parcel or use the free returns process."},
            {"heading": "How do promo codes work?",
             "text": "Enter the code in your cart and the discount applies to eligible "
                     "items immediately. One promo per order; deals and promos don't stack."},
            {"heading": "Is my data safe?",
             "text": "Traffic is encrypted end-to-end, payments are processed by our "
                     "payment provider, and we never sell personal data. See the "
                     "Privacy Policy for details."},
        ],
    },
    "contact": {
        "title": "Contact Us",
        "subtitle": "We answer every message — usually within one business day.",
        "blocks": [
            {"heading": "Talk to a human",
             "rows": [("Email", '<a href="mailto:support@shoplinq.com">support@shoplinq.com</a>'),
                      ("Phone", '<a href="tel:+15550102030">+1 (555) 010-2030</a>'),
                      ("Hours", "Mon&ndash;Fri, 9:00&ndash;18:00 ET"),
                      ("Address", "123 Market Street, Suite 400, Springfield, IL 62704, USA")]},
            {"heading": "Order support",
             "text": "Have your order number ready (it looks like SLQ-2026-1234) — it helps "
                     "us find your parcel in seconds. You can also track every order "
                     "yourself from <strong>Your Orders</strong>."},
            {"heading": "Business inquiries",
             "text": "Want to sell on ShopLinq or partner with us? Write to "
                     "<a href=\"mailto:partners@shoplinq.com\">partners@shoplinq.com</a>."},
        ],
    },
    "privacy": {
        "title": "Privacy Policy",
        "subtitle": "Last updated: September 2026",
        "blocks": [
            {"heading": "What we collect",
             "list": [
                 "Account details: name, email, and (optionally) saved addresses.",
                 "Order data: items, totals, delivery choice, and order status.",
                 "Technical basics: session cookie and CSRF token, to keep you logged in safely.",
             ]},
            {"heading": "What we never do",
             "list": [
                 "Sell or rent your personal data to anyone.",
                 "Store full card numbers &mdash; payments run through our payment provider.",
                 "Track you across other websites.",
             ]},
            {"heading": "Your rights",
             "text": "You can request a copy of your data, correct it, or delete your "
                     "account entirely. Email <a href=\"mailto:privacy@shoplinq.com\">"
                     "privacy@shoplinq.com</a> and we action requests within 30 days."},
        ],
    },
    "terms": {
        "title": "Terms of Service",
        "subtitle": "Last updated: September 2026",
        "blocks": [
            {"heading": "Using ShopLinq",
             "text": "By placing an order you confirm the details you give are accurate "
                     "and that you're authorized to use the chosen payment method. "
                     "Prices are shown in USD and include applicable taxes at checkout."},
            {"heading": "Orders & pricing",
             "list": [
                 "An order is a contract only once we confirm it by email.",
                 "We may cancel and refund orders affected by obvious pricing errors.",
                 "Stock is reserved at the moment your payment is confirmed.",
             ]},
            {"heading": "Liability",
             "text": "ShopLinq's liability for any order is limited to the order total. "
                     "Nothing in these terms limits your statutory consumer rights."},
            {"heading": "Note",
             "text": "ShopLinq is a demo application. No real goods are sold and no real "
                     "payments are captured."},
        ],
    },
}


@main_bp.route("/info/<page>")
def info(page):
    content = INFO_PAGES.get(page)
    if not content:
        abort(404)
    return render_template("info.html", page=content)
