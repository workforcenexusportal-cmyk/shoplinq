"""ShopLinq application factory."""
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, session

from extensions import db, login_manager

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///shoplinq.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["STRIPE_SECRET_KEY"] = os.environ.get("STRIPE_SECRET_KEY", "")
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    app.config["DEMO_MODE"] = os.environ.get("DEMO_MODE", "1") != "0"

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def csrf_protect():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        sent = (request.headers.get("X-CSRF-Token")
                or request.form.get("csrf_token"))
        if sent and sent == session.get("csrf_token"):
            return None
        if request.path.startswith("/api/"):
            return jsonify({
                "ok": False,
                "message": "Your session changed — please refresh the page and try again.",
            }), 403
        abort(400, description="Invalid or missing CSRF token — please go back, "
              "reload the page and try again.")

    from blueprints.main import main_bp
    from blueprints.auth import auth_bp
    from blueprints.cart import cart_bp
    from blueprints.account import account_bp
    from blueprints.admin import admin_bp
    from blueprints.api import api_bp

    for bp in (main_bp, auth_bp, cart_bp, account_bp, admin_bp, api_bp):
        app.register_blueprint(bp)

    from models import Category, Customer, Order, OrderItem, Shipping, Payment, Cart, CartItem

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Customer, int(user_id))

    @app.template_filter("money")
    def money(value):
        return f"${value:,.2f}" if value is not None else "—"

    @app.context_processor
    def inject_globals():
        from services import get_cart_count, get_nav_tree
        try:
            nav_categories = get_nav_tree()
        except Exception:
            nav_categories = []
        from flask import request, url_for

        def page_url(endpoint, view_args, args, page):
            merged = dict(view_args or {})
            merged.update(args)
            merged["page"] = page
            return url_for(endpoint, **merged)

        return {
            "nav_categories": nav_categories,
            "cart_count": get_cart_count(),
            "page_url": page_url,
        }

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        port=int(os.environ.get("PORT", "5000")),
    )
