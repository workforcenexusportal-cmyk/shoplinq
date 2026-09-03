"""Main catalog routes: homepage, product listing, product detail."""
from flask import Blueprint, render_template, request

from extensions import db
from models import Category, Product, ProductQA, Review

main_bp = Blueprint("main", __name__)

SORTS = {
    "featured": (Product.rating.desc(), Product.rating_count.desc()),
    "price_asc": (Product.price.asc(),),
    "price_desc": (Product.price.desc(),),
    "rating": (Product.rating.desc(), Product.rating_count.desc()),
    "newest": (Product.created_date.desc(),),
}


@main_bp.route("/")
def index():
    deals = Product.query.filter_by(is_deal=True).order_by(Product.rating.desc()).limit(8).all()
    recommended = (
        Product.query.filter(Product.rating >= 4.0)
        .order_by(Product.rating_count.desc()).limit(12).all()
    )
    new_arrivals = Product.query.order_by(Product.created_date.desc()).limit(8).all()
    return render_template(
        "index.html", deals=deals, recommended=recommended,
        new_arrivals=new_arrivals,
    )


def _category_ids(category):
    return [category.id] + [c.id for c in category.children]


@main_bp.route("/products")
@main_bp.route("/category/<slug>")
def products(slug=None):
    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "featured")
    q = request.args.get("q", "").strip()
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
    query = query.order_by(*order_cols)
    pagination = query.paginate(page=page, per_page=12, error_out=False)

    all_brands = [
        r[0] for r in db.session.query(Product.brand).filter(Product.brand.isnot(None))
        .distinct().order_by(Product.brand).all()
    ]
    root_categories = Category.query.filter_by(parent_id=None).order_by(Category.name).all()

    return render_template(
        "products.html", pagination=pagination, products=pagination.items,
        all_brands=all_brands, root_categories=root_categories,
        current_category=category, current_sort=sort,
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
    from flask_login import current_user
    my_review = None
    if current_user.is_authenticated:
        my_review = Review.query.filter_by(product_id=p.id, customer_id=current_user.id).first()
    return render_template(
        "product.html", product=p, related=related,
        reviews=reviews, my_review=my_review, qa=p.questions,
    )
