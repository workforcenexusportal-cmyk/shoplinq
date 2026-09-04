"""Shared pytest fixtures for the ShopLinq test suite."""
import os
import tempfile

import pytest

# Configure the environment before the app factory reads it.
os.environ["FLASK_DEBUG"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DEMO_MODE"] = "1"
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ.pop("MAIL_SERVER", None)

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

from app import create_app  # noqa: E402
from extensions import db, limiter  # noqa: E402
from models import Category, Customer, Product  # noqa: E402


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config.update(TESTING=True)
    limiter.enabled = False
    with application.app_context():
        db.create_all()
        _seed()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
    try:
        os.remove(_db_path)
    except OSError:
        pass


def _seed():
    cat = Category(name="Widgets", slug="widgets")
    db.session.add(cat)
    db.session.flush()

    product = Product(name="Test Widget", slug="test-widget", price=25.0,
                      stock=10, category_id=cat.id, description="A widget.")
    db.session.add(product)

    admin = Customer(name="Admin User", email="admin@test.com", is_admin=True)
    admin.set_password("adminpass")
    customer = Customer(name="Jane Buyer", email="jane@test.com")
    customer.set_password("janepass")
    db.session.add_all([admin, customer])
    db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, token="testtoken"):
    """Prime the session with a known CSRF token and return it."""
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return token


def login(client, email, password):
    token = csrf(client)
    return client.post("/login", data={
        "email": email, "password": password, "csrf_token": token,
    }, follow_redirects=True)
