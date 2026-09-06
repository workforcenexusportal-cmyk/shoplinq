# ShopLinq 🛒

A full-featured, Amazon-style online marketplace built with **Python Flask** — recolored in a modern **blue & teal / white** palette.

![stack](https://img.shields.io/badge/Flask-3.x-blue) ![db](https://img.shields.io/badge/SQLAlchemy-SQLite/PostgreSQL-teal)

## Features

- **Catalog** — homepage hero carousel, category tiles, Deals of the Day with countdown, recommendation rows
- **Search & filters** — live autocomplete, sidebar filters (category, price, brand, rating, availability), sorting, pagination
- **Product pages** — image gallery, ratings & reviews, Q&A, related products, wishlist, out-of-stock "Notify me"
- **Cart** — AJAX quantity editing, save-for-later, promo codes (`SAVE10`, `WELCOME15`, `VIP20`) — no page reloads
- **Checkout** — 4-step wizard: address → delivery speed → payment → review
- **Payments** — Razorpay for India (UPI, RuPay/Visa/Mastercard cards, netbanking, wallets) with a built-in demo simulator when no keys are set (any valid UPI ID succeeds; `fail@upi` declines; card `4111 1111 1111 1111` succeeds, `4000 0000 0000 0002` declines), plus cash on delivery. Prices in ₹ (INR), GST included in listed prices
- **Customer portal** — dashboard with activity stats, order history & tracking timeline (Placed → Packed → Shipped → Out for Delivery → Delivered), addresses, payment methods, wishlist, profile
- **Admin** (reachable from the same account menu) — product CRUD, category tree management, inventory control, order fulfillment with automatic customer notifications, and a **sales analytics page** (monthly revenue chart, units sold, top products, review analysis)

## Tech

- Flask + Blueprints, Flask-SQLAlchemy (SQLite by default, PostgreSQL-ready), Flask-Login sessions
- One Jinja2 base template with inheritance · **one** shared `style.css` · **one** shared `script.js` (no inline scripts)
- Google Fonts (Poppins + Inter), fully responsive

## Quickstart (localhost)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
python seed.py                   # fresh DB + demo catalog
python app.py                    # → http://127.0.0.1:5000
```

The included `.env.example` sets `FLASK_DEBUG=1` for local development. In
production the app **requires** a real `SECRET_KEY` and enables HTTPS-only
secure cookies automatically.

### Demo accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@shoplinq.com | adminpass123 |
| Customer | demo@shoplinq.com | demopass123 |

The demo customer already has order history at different tracking stages, a wishlist, a saved address and card.

### Razorpay (optional)

Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env` to collect real payments.
When keys are set, online orders are placed with payment pending, the customer is
redirected to `/pay/<order_number>` (Razorpay Checkout sheet), and `/pay/<order_number>/verify`
validates the HMAC-SHA256 signature before marking the order paid. Without keys the
app runs in demo mode and simulates successful/declined payments.

Razorpay Checkout handles confirmation itself — no webhook is required for payment status.
The `/pay/<order_number>/verify` callback checks the HMAC-SHA256 signature with your
`RAZORPAY_KEY_SECRET` before an order is marked paid, so a tampered or replayed
response is rejected.

## Tests

```bash
pytest            # runs the functional suite in tests/
```

## Project structure

```
app.py               # app factory + CLI entry
config via .env
models.py            # all SQLAlchemy models
services.py          # cart/order/promo/email business logic
blueprints/
  main.py            # homepage, listings, product detail
  auth.py            # register / login / password reset
  cart.py            # cart, checkout, order placement, Razorpay + COD
  account.py         # customer portal
  admin.py           # admin dashboard + analytics
  api.py             # JSON endpoints powering script.js
templates/           # Jinja2 (base.html + one file per page)
static/style.css     # the single shared stylesheet
static/script.js     # the single shared script
static/images/       # bundled SVG product art
seed.py              # demo data
```

## Deployment

The app runs under gunicorn via the WSGI entrypoint:

```bash
gunicorn wsgi:app
```

### Production checklist

- Set a strong `SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`).
- Leave `FLASK_DEBUG` unset (enables secure cookies, disables the reloader).
- Set `DEMO_MODE=0` so payments and password resets stop simulating.
- Configure `DATABASE_URL` (MySQL/PostgreSQL) and `MAIL_*` for real email.
- Apply the schema with migrations instead of `create_all`:
  ```bash
  flask db upgrade      # requires FLASK_APP=app.py
  ```

### Database migrations

Schema changes are managed with Flask-Migrate (Alembic):

```bash
export FLASK_APP=app.py          # Windows: set FLASK_APP=app.py
flask db migrate -m "describe change"
flask db upgrade
```

### PythonAnywhere

1. Upload/clone the repo, create a virtualenv, `pip install -r requirements.txt`.
2. Create a **MySQL** database in the *Databases* tab, then set
   `DATABASE_URL=mysql://USER:PASSWORD@USER.mysql.pythonanywhere-services.com/USER$shoplinq`.
3. In the *Web* tab, set the source directory and edit the WSGI file to:
   ```python
   import os
   os.environ["SECRET_KEY"] = "..."
   os.environ["DATABASE_URL"] = "mysql://..."
   os.environ["DEMO_MODE"] = "0"
   from wsgi import app as application
   ```
4. Map `/static/` to the project's `static/` folder.
5. Run `flask db upgrade` (then `python seed.py` if you want demo data), and reload the web app.

## Test-card cheat sheet

- `4242 4242 4242 4242` — succeeds
- `4000 0000 0000 0002` — declined
- Any expiry date in the future works.
