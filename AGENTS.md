# ShopLinq — Base44 Dev Environment

## What this is
A Flask e-commerce app (Amazon-style marketplace) with Jinja2 templates, SQLite by default, and demo-mode payments. No external services are required to boot.

## Running the app
```bash
docker compose -f docker-compose.base44.yml up -d
```
- **Setup service** (one-shot): installs pip deps, runs `python seed.py` which recreates the SQLite DB and fills it with demo data (5073 products, 251 categories, demo orders).
- **Web service**: Flask dev server (`flask run`) with auto-reload on `0.0.0.0:3000`, mapped to host port 3000.

## Key details
- **No external secrets required.** The app runs in `DEMO_MODE=1` — payments are simulated, emails are logged. Razorpay keys and SMTP settings are optional (see `.base44/environment.json`).
- **SQLite** is file-based (`shoplinq.db` in the bind-mounted source). No DB container needed. The file persists across container restarts but is gitignored.
- **Live reload** works via Flask/Werkzeug stat-polling reloader (watchdog is not installed). Edits to Python files, templates, CSS, and JS are picked up automatically.
- **External hostname**: Flask's dev server accepts all hosts by default — no `allowedHosts` config needed.
- **Env vars** come from `.env.base44-defaults` (placeholders) overridden by `/run/base44/app.env` (platform secrets, if any).

## Demo accounts
| Role | Email | Password |
|---|---|---|
| Admin | admin@shoplinq.com | adminpass123 |
| Customer | demo@shoplinq.com | demopass123 |

## Verifying it works
```bash
curl -sf http://localhost:3000/ | head -3   # should return HTML
docker compose -f docker-compose.base44.yml ps  # web should be "healthy"
```

## Re-seeding the database
```bash
docker compose -f docker-compose.base44.yml run --rm setup
```

## Tests
```bash
docker compose -f docker-compose.base44.yml exec web pytest
```
