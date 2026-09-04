"""Authentication: register, login, logout, password reset."""
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from extensions import db
from models import Customer
from services import merge_session_cart, send_email

auth_bp = Blueprint("auth", __name__)

RESET_SALT = "password-reset"


def get_reset_serializer():
    from flask import current_app
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=RESET_SALT)


def generate_reset_token(email):
    return get_reset_serializer().dumps({"email": email})


def verify_reset_token(token, max_age=3600):
    try:
        data = get_reset_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return Customer.query.filter_by(email=data["email"]).first()


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif Customer.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = Customer(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            merge_session_cart(user)
            flash(f"Welcome to ShopLinq, {user.first_name}!", "success")
            return redirect(url_for("main.index"))
    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = Customer.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=bool(request.form.get("remember")))
            merge_session_cart(user)
            flash(f"Welcome back, {user.first_name}!", "success")
            next_url = request.args.get("next") or ""
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("main.index"))
        flash("Incorrect email or password.", "error")
    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.index"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = Customer.query.filter_by(email=email).first()
        if user:
            token = generate_reset_token(email)
            link = url_for("auth.reset_password", token=token, _external=True)
            send_email(email, "Reset your ShopLinq password",
                       f"Hi {user.first_name},\n\nReset your password using this link "
                       f"(valid for 1 hour):\n\n{link}\n\n— The ShopLinq Team")
            if current_app.config.get("DEMO_MODE"):
                # Demo convenience ONLY: surface the reset link so testers can proceed.
                # Set DEMO_MODE=0 in production to disable this.
                flash(f"Demo mode: your reset link is {link}", "info")
        flash("If an account exists for that email, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = verify_reset_token(token)
    if not user:
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user.set_password(password)
            db.session.commit()
            flash("Your password has been reset. Please sign in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token)
