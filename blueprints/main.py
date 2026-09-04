"""Main catalog routes: homepage, product listing, product detail."""
from flask import Blueprint, render_template, request
from flask_login import current_user

from extensions import db
from models import Category, Product, ProductQA, Review
from services import (
    cache_get, cache_set, get_brand_list, get_category_counts, get_nav_tree,
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
        new_arrivals=new_arrivals,
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
    return render_template(
        "product.html", product=p, related=related,
        reviews=reviews, my_review=my_review, qa=p.questions,
    )
