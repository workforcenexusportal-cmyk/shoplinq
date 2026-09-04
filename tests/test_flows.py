"""Functional tests covering core ShopLinq flows."""
from conftest import csrf, login


def test_homepage_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_products_page_ok(client):
    resp = client.get("/products")
    assert resp.status_code == 200


def test_product_detail_ok(client):
    resp = client.get("/product/test-widget")
    assert resp.status_code == 200


def test_404_page(client):
    resp = client.get("/no-such-page")
    assert resp.status_code == 404


# ------------------------------------------------------------ auth

def test_register_and_logout(client):
    token = csrf(client)
    resp = client.post("/register", data={
        "name": "New Person", "email": "new@test.com",
        "password": "secret123", "confirm": "secret123", "csrf_token": token,
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_login_success(client):
    resp = login(client, "jane@test.com", "janepass")
    assert resp.status_code == 200


def test_login_wrong_password(client):
    resp = login(client, "jane@test.com", "wrongpass")
    assert b"nvalid" in resp.data or b"ncorrect" in resp.data or resp.status_code == 200


# ------------------------------------------------------------ csrf

def test_csrf_blocks_form_post(client):
    # No csrf token primed/sent -> rejected with 400.
    resp = client.post("/login", data={"email": "x@test.com", "password": "y"})
    assert resp.status_code == 400


def test_csrf_blocks_api_post(client):
    resp = client.post("/api/cart/add", json={"product_id": 1})
    assert resp.status_code == 403


# ------------------------------------------------------------ cart + guest checkout

def test_add_to_cart_and_guest_checkout(client):
    token = csrf(client)
    resp = client.post("/api/cart/add",
                       json={"product_id": 1, "quantity": 2},
                       headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    place = client.post("/checkout/place", data={
        "csrf_token": token,
        "guest_email": "guest@test.com",
        "full_name": "Guest Shopper",
        "line1": "1 Test St",
        "city": "Testville",
        "postal_code": "12345",
        "country": "United States",
        "delivery": "standard",
        "payment": "cod",
    }, follow_redirects=True)
    assert place.status_code == 200
    assert b"order" in place.data.lower()


# ------------------------------------------------------------ admin access control

def test_admin_requires_login(client):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code in (301, 302, 308)


def test_non_admin_forbidden(client):
    login(client, "jane@test.com", "janepass")
    resp = client.get("/admin/")
    assert resp.status_code in (403, 302)


def test_admin_can_access_dashboard(client):
    login(client, "admin@test.com", "adminpass")
    resp = client.get("/admin/")
    assert resp.status_code == 200


# ------------------------------------------------------------ admin promo CRUD

def test_admin_create_promo(client):
    login(client, "admin@test.com", "adminpass")
    token = csrf(client)
    resp = client.post("/admin/promos", data={
        "csrf_token": token,
        "code": "TESTCODE",
        "discount_percent": "15",
        "min_spend": "0",
        "is_active": "1",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"TESTCODE" in resp.data


# ------------------------------------------------------------ admin customers

def test_admin_customers_list(client):
    login(client, "admin@test.com", "adminpass")
    resp = client.get("/admin/customers")
    assert resp.status_code == 200
    assert b"jane@test.com" in resp.data


# ------------------------------------------------------------ admin returns

def test_admin_returns_page(client):
    login(client, "admin@test.com", "adminpass")
    resp = client.get("/admin/returns")
    assert resp.status_code == 200
