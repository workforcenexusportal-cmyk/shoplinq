# ShopLinq 🛒

A full-featured, Amazon-style online marketplace built with **Python Flask** — recolored in a modern **blue & teal / white** palette.

![stack](https://img.shields.io/badge/Flask-3.x-blue) ![db](https://img.shields.io/badge/SQLAlchemy-SQLite/PostgreSQL-teal)

## Features

- **Catalog** — homepage hero carousel, category tiles, Deals of the Day with countdown, recommendation rows
- **Search & filters** — live autocomplete, sidebar filters (category, price, brand, rating, availability), sorting, pagination
- **Product pages** — image gallery, ratings & reviews, Q&A, related products, wishlist, out-of-stock "Notify me"
- **Cart** — AJAX quantity editing, save-for-later, promo codes (`SAVE10`, `WELCOME15`, `VIP20`) — no page reloads
- **Checkout** — 4-step wizard: address → delivery speed → payment → review
- **Payments** — Stripe Checkout in test mode (falls back to a built-in demo card simulator when no keys are set — use `4242 4242 4242 4242`, declines `4000 0000 0000 0002`) or cash on delivery
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
python seed.py                   # fresh DB + demo catalog
python app.py                    # → http://127.0.0.1:5000
```

### Demo accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@shoplinq.com | adminpass123 |
| Customer | demo@shoplinq.com | demopass123 |

The demo customer already has order history at different tracking stages, a wishlist, a saved address and card.

### Stripe (optional)

Copy `.env.example` to `.env` and add your **test** keys (`sk_test_...` / `pk_test_...`). Without keys, card payments run in demo mode.

## Project structure

```
app.py               # app factory + CLI entry
config via .env
models.py            # all SQLAlchemy models
services.py          # cart/order/promo/email business logic
blueprints/
  main.py            # homepage, listings, product detail
  auth.py            # register / login / password reset
  cart.py            # cart, checkout, order placement, Stripe
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

PythonAnywhere deployment will follow once development is complete — the app already runs cleanly under gunicorn (`gunicorn app:app` style, via `create_app()`).

## Test-card cheat sheet

- `4242 4242 4242 4242` — succeeds
- `4000 0000 0000 0002` — declined
- Any expiry date in the future works.
