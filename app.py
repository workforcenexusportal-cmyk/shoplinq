"""ShopLinq application factory."""
import logging
import os
import secrets
from datetime import timedelta
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import db, limiter, login_manager, migrate

load_dotenv()


def _normalize_db_url(url):
    """Make hosted-DB URLs work with SQLAlchemy drivers (Heroku / PythonAnywhere)."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    return url


def _configure_logging(app):
    """Send warnings/errors to stderr (and a rotating file when writable)."""
    if app.debug:
        return
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.setLevel(logging.INFO)
    app.logger.addHandler(stream)
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(app.instance_path, "shoplinq.log"),
            maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(fmt)
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
    except OSError:
        pass
    app.logger.setLevel(logging.INFO)


ERROR_PAGES = {
    400: ("Bad request", "That request didn't look right. Please go back and try again."),
    403: ("Access denied", "You don't have permission to view this page."),
    404: ("Page not found", "We couldn't find the page you were looking for."),
    413: ("File too large", "That upload exceeded the size limit."),
    429: ("Slow down", "You've made too many requests. Please wait a moment and try again."),
    500: ("Something went wrong", "An unexpected error occurred on our end. We're on it."),
}


def _register_error_handlers(app):
    def render_error(err):
        code = err.code if isinstance(err, HTTPException) else 500
        if code >= 500:
            db.session.rollback()
            app.logger.exception("Unhandled error on %s", request.path)
        title, message = ERROR_PAGES.get(code, ERROR_PAGES[500])
        description = getattr(err, "description", None) if isinstance(err, HTTPException) else None
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "message": description or message}), code
        return render_template(
            "errors/error.html", code=code, title=title,
            message=description or message), code

    for status in (400, 403, 404, 413, 429, 500):
        app.register_error_handler(status, render_error)


def create_app():
    app = Flask(__name__)
    app.debug = os.environ.get("FLASK_DEBUG") == "1"

    # --- secret key (must be set explicitly in production) ---
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if not app.debug:
            raise RuntimeError(
                "SECRET_KEY must be set in production. Generate one with: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        secret_key = "dev-secret-key-change-me"
    app.config["SECRET_KEY"] = secret_key

    # --- database ---
    db_url = _normalize_db_url(os.environ.get("DATABASE_URL", "sqlite:///shoplinq.db"))
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if not db_url.startswith("sqlite"):
        # Hosted DBs (e.g. PythonAnywhere MySQL) drop idle connections.
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_recycle": 280, "pool_pre_ping": True,
        }

    app.config["STRIPE_SECRET_KEY"] = os.environ.get("STRIPE_SECRET_KEY", "")
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    app.config["STRIPE_WEBHOOK_SECRET"] = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    app.config["DEMO_MODE"] = os.environ.get("DEMO_MODE", "1") != "0"

    # --- session / cookie hardening ---
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not app.debug,  # HTTPS-only cookies in production
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # 8 MB request cap
    )

    # Honor X-Forwarded-* headers behind PythonAnywhere / reverse proxies.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
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
        # External webhooks authenticate via their own signature, not CSRF.
        if request.path.startswith("/webhooks/"):
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

    _register_error_handlers(app)

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
