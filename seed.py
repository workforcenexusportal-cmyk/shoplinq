"""Seed the ShopLinq database with a full demo catalog.

Run:  python seed.py   (fresh database — wipes existing data first)
"""
from datetime import timedelta

from app import create_app
from extensions import db
from models import (
    Address, Cart, Category, Customer, Order, OrderItem, Payment,
    PaymentMethod, Product, ProductImage, ProductQA, PromoCode, Review,
    Shipping, WishlistItem, utcnow,
)
from services import unique_slug

app = create_app()

# ---------------------------------------------------------------- catalog

CATEGORIES = [
    ("Electronics", "electronics", None),
    ("Mobile Phones", "mobile-phones", "electronics"),
    ("Laptops", "laptops", "electronics"),
    ("Audio", "audio", "electronics"),
    ("Home & Kitchen", "home-kitchen", None),
    ("Cookware", "cookware", "home-kitchen"),
    ("Small Appliances", "small-appliances", "home-kitchen"),
    ("Fashion", "fashion", None),
    ("Men", "men", "fashion"),
    ("Women", "women", "fashion"),
    ("Books", "books", None),
    ("Sports & Outdoors", "sports-outdoors", None),
    ("Beauty", "beauty", None),
    ("Toys & Games", "toys-games", None),
]

# (name, brand, price, deal_price|None, stock, cat_slug, imgs, description, featured)
PRODUCTS = [
    ("Aurora X5 5G Smartphone", "NovaTech", 699.99, 599.99, 42, "mobile-phones", ["phone-1", "phone-2", "phone-3"], "6.7\" AMOLED 120Hz display, triple 108MP camera system, 5000mAh battery with 45W fast charging. Unlocked for all carriers.", True),
    ("Aurora X5 Lite", "NovaTech", 349.99, None, 30, "mobile-phones", ["phone-2", "phone-1"], "Compact 6.1\" phone with dual camera, clean software and two-day battery life.", False),
    ("Helio S7 Pro", "Helio", 549.00, None, 18, "mobile-phones", ["phone-3", "phone-1"], "Flagship processor, IP68 water resistance and studio-grade portrait mode.", True),
    ("Zenith Fold Flex", "Zenith", 1299.00, None, 0, "mobile-phones", ["phone-3"], "Foldable 7.6\" tablet-phone hybrid with flex-hinge and wireless charging.", False),
    ("Stratus Book 14\" Ultrabook", "Stratus", 999.99, None, 15, "laptops", ["laptop-1", "laptop-2"], "1.1kg magnesium chassis, 16-hour battery, 16GB RAM and 512GB NVMe storage.", True),
    ("Stratus Book Pro 16\"", "Stratus", 1899.99, 1699.99, 8, "laptops", ["laptop-2", "laptop-1", "laptop-3"], "Creator-grade laptop with 32GB RAM, 1TB SSD and a 120Hz mini-LED display.", True),
    ("Cirrus Chrome Slim", "Cirrus", 449.00, None, 25, "laptops", ["laptop-3", "laptop-1"], "Featherweight cloud laptop — boots in seconds, updates itself, all-day battery.", False),
    ("Zenith Studio Creator 15", "Zenith", 2199.00, None, 0, "laptops", ["laptop-2"], "Mobile workstation with color-calibrated 4K panel for video and 3D work.", False),
    ("EchoWave ANC Headphones", "EchoWave", 199.99, 149.99, 60, "audio", ["audio-1", "audio-2"], "Hybrid active noise cancelling, 40-hour battery, multipoint Bluetooth 5.3.", True),
    ("EchoWave Buds Air", "EchoWave", 89.99, None, 80, "audio", ["audio-2", "audio-1"], "True wireless earbuds with transparency mode and wireless charging case.", True),
    ("Pulse Boom Mini Speaker", "Pulse", 59.99, None, 35, "audio", ["audio-3", "audio-1"], "Pocket-sized 360° speaker, IP67 waterproof, 18 hours of playtime.", False),
    ("Copperline 10-Piece Cookware Set", "Copperline", 249.99, 199.99, 22, "cookware", ["home-1", "home-3"], "Tri-ply stainless pots and pans with stay-cool handles — induction ready.", True),
    ("Copperline Chef's Knife 8\"", "Copperline", 69.99, None, 40, "cookware", ["home-1", "home-2"], "German steel, full tang, razor-sharp edge that holds through years of prep.", False),
    ("BrewMaster Espresso Machine", "BrewMaster", 399.00, None, 12, "small-appliances", ["home-2", "home-1"], "15-bar pump espresso maker with steam wand and precision temperature control.", True),
    ("VortexAir Fryer 5L", "Vortex", 129.99, None, 48, "small-appliances", ["home-3", "home-2"], "Crispy results with 90% less oil — 8 presets, dishwasher-safe basket.", True),
    ("PureSip Glass Bottle Set (6)", "PureSip", 29.99, None, 100, "small-appliances", ["home-3", "home-1"], "Borosilicate water bottles with leakproof bamboo lids.", False),
    ("Northpeak Rain Jacket", "Northpeak", 119.00, None, 28, "men", ["fashion-1", "fashion-2"], "2.5-layer waterproof shell with pit zips and packs into its own pocket.", False),
    ("Everyday Merino Tee", "Loom & Co", 49.50, None, 65, "men", ["fashion-2", "fashion-1"], "17.5 micron merino jersey — breathable, odor-resistant, impossibly soft.", True),
    ("Solstice Wrap Dress", "Solstice", 89.00, 69.00, 20, "women", ["fashion-3", "fashion-2"], "Fluid wrap silhouette in machine-washable crepe, sizes XS–XXL.", False),
    ("Cloudstep Sneakers", "Cloudstep", 94.99, None, 55, "women", ["fashion-2", "fashion-3"], "Featherlight knit uppers with responsive cushioning for all-day wear.", True),
    ("Northpeak Insulated Vest", "Northpeak", 99.00, None, 0, "women", ["fashion-1"], "650-fill responsible down vest that layers under anything.", False),
    ("The Silent Algorithm (Hardcover)", "Northgate Press", 24.00, None, 33, "books", ["book-1", "book-2"], "A near-future thriller about the machines that curate our lives. 416 pages.", False),
    ("Deep Work Habits", "Bright Mind", 18.99, None, 47, "books", ["book-2", "book-1"], "A practical field guide to focused work in a distracted world.", True),
    ("Atlas of Small Journeys", "Northgate Press", 32.50, None, 19, "books", ["book-3", "book-2"], "Illustrated travels through 40 of the world's overlooked places.", False),
    ("Cooking for One, Well", "Bright Mind", 21.00, None, 0, "books", ["home-2"], "90 single-serving recipes that never feel like a compromise.", False),
    ("Trailblazer Daypack 30L", "Trailblazer", 84.99, None, 36, "sports-outdoors", ["sport-1", "sport-2"], "Ventilated back panel, rain cover included, laptop sleeve for hybrid days.", True),
    ("FlexCore Yoga Mat", "FlexCore", 39.99, None, 58, "sports-outdoors", ["sport-2", "sport-1"], "6mm cushioned mat with alignment lines and non-slip natural rubber.", False),
    ("Trailblazer Insulated Flask", "Trailblazer", 27.99, None, 70, "sports-outdoors", ["sport-1"], "Keeps drinks cold 24 hours, hot 12 — leakproof one-hand lid.", False),
    ("Velocity Jump Rope Pro", "Velocity", 17.99, None, 90, "sports-outdoors", ["sport-2"], "Ball-bearing speed rope with adjustable steel cable.", False),
    ("Lumina Vitamin C Serum", "Lumina", 34.00, None, 44, "beauty", ["beauty-1", "beauty-2"], "15% stabilized vitamin C with ferulic acid for visible brightness in 4 weeks.", True),
    ("Lumina Hydra Cream", "Lumina", 28.00, None, 51, "beauty", ["beauty-2", "beauty-1"], "72-hour moisture barrier cream with ceramides and squalane.", False),
    ("Freshline Hair Repair Kit", "Freshline", 22.50, None, 38, "beauty", ["beauty-1"], "Bond-repair shampoo and mask duo for over-processed hair.", False),
    ("BlockWorks Space Station Kit", "BlockWorks", 59.99, None, 26, "toys-games", ["toy-1", "toy-2"], "1,050-piece buildable orbital station with 4 mini-figures. Ages 9+.", True),
    ("Puzzle Peak 1000-Piece Alpine", "Puzzle Peak", 19.99, None, 42, "toys-games", ["toy-2", "toy-1"], "Matte-finish panoramic puzzle of an alpine valley at golden hour.", False),
    ("BlockWorks Robot Starter Set", "BlockWorks", 44.99, None, 0, "toys-games", ["toy-1"], "Screen-free coding robot with 60 progressive challenge cards. Ages 6+.", False),
]

REVIEWS = {
    "Aurora X5 5G Smartphone": [
        ("Maya Chen", 5, "Best phone I've owned", "The camera is unreal and battery easily lasts a full day of heavy use."),
        ("Jonas Weber", 4, "Great, but big", "Coming from a compact phone this took getting used to. Performance is flawless."),
    ],
    "Aurora X5 Lite": [("Priya Nair", 4, "Perfect budget pick", "Does everything I need — calls, maps, photos of my dog.")],
    "Helio S7 Pro": [
        ("Liam O'Brien", 5, "Flagship feel, mid price", "Portrait mode rivals phones twice the price."),
        ("Sofia Rossi", 4, "Solid all-rounder", "Screen could be brighter in direct sun, otherwise wonderful."),
    ],
    "Stratus Book 14\" Ultrabook": [
        ("Maya Chen", 5, "Feather light and fast", "Carried it across Europe for two weeks and barely noticed it in my bag."),
        ("Jonas Weber", 5, "Battery life is magic", "Real-world 14+ hours writing code."),
    ],
    "Stratus Book Pro 16\"": [("Liam O'Brien", 5, "Worth every cent", "Renders 4K timelines without breaking a sweat.")],
    "EchoWave ANC Headphones": [
        ("Sofia Rossi", 5, "Silence on demand", "The noise cancelling erases my noisy neighbors completely."),
        ("Priya Nair", 4, "Comfy for long flights", "Slight clamping force at first but breaks in nicely."),
        ("Jonas Weber", 5, "Superb sound", "Bass is punchy without drowning the mids."),
    ],
    "EchoWave Buds Air": [("Maya Chen", 4, "Great for the price", "Case is chunky but battery life makes up for it.")],
    "Pulse Boom Mini Speaker": [("Liam O'Brien", 4, "Tiny but loud", "Shocked by the volume from something this small.")],
    "Copperline 10-Piece Cookware Set": [
        ("Sofia Rossi", 5, "Restaurant quality at home", "Heats evenly, cleans up easily, looks beautiful hanging on the rack."),
        ("Jonas Weber", 4, "Heavy but excellent", "These are substantial pans — my arms are getting a workout."),
    ],
    "Copperline Chef's Knife 8\"": [("Priya Nair", 5, "Scary sharp", "Slices tomatoes like they're nothing.")],
    "BrewMaster Espresso Machine": [
        ("Jonas Weber", 5, "Café quality espresso", "Dialed in the grind and now my mornings are perfect."),
        ("Maya Chen", 4, "Learning curve", "Takes practice, but the results are worth it."),
    ],
    "VortexAir Fryer 5L": [
        ("Sofia Rossi", 5, "Use it every single day", "Crispy fries with a teaspoon of oil. My kids approve."),
        ("Liam O'Brien", 4, "Big and powerful", "Takes counter space but roasts a whole chicken beautifully."),
    ],
    "Northpeak Rain Jacket": [("Liam O'Brien", 5, "Dry in a downpour", "Hiked 6 hours in Scottish rain — bone dry underneath.")],
    "Everyday Merino Tee": [
        ("Maya Chen", 5, "Softest shirt I own", "Wore it three days traveling — no odor, no wrinkles."),
        ("Jonas Weber", 4, "Pricey for a tee", "But it genuinely outlasts cheap cotton tees."),
    ],
    "Solstice Wrap Dress": [("Sofia Rossi", 5, "Flattering and comfy", "Works at the office and at dinner.")],
    "Cloudstep Sneakers": [("Priya Nair", 5, "Like walking on air", "Did 20k steps in Lisbon with zero complaints from my feet.")],
    "The Silent Algorithm (Hardcover)": [
        ("Maya Chen", 4, "Timely and tense", "Couldn't put it down — finished it in two nights."),
        ("Liam O'Brien", 5, "Best thriller this year", "Genuinely plausible tech, great characters."),
    ],
    "Deep Work Habits": [("Jonas Weber", 5, "Changed how I work", "Simple system, dramatic results in my focus.")],
    "Trailblazer Daypack 30L": [("Sofia Rossi", 5, "Perfect travel companion", "Fits under airplane seats and carries a weekend of gear.")],
    "FlexCore Yoga Mat": [("Priya Nair", 4, "Grippy and supportive", "Alignment lines actually help my practice.")],
    "Lumina Vitamin C Serum": [
        ("Maya Chen", 5, "Visible glow", "Dark spots fading after a month of use."),
        ("Sofia Rossi", 4, "Gentle but effective", "No tingling like other vitamin C serums I've tried."),
    ],
    "BlockWorks Space Station Kit": [("Jonas Weber", 5, "Kid approved", "My daughter built it over a weekend and now displays it proudly.")],
    "Puzzle Peak 1000-Piece Alpine": [("Liam O'Brien", 4, "Beautiful image", "Challenging sky section but very satisfying.")],
}

QA = [
    ("Aurora X5 5G Smartphone", "Does this phone support dual SIM?", "Yes — one nano-SIM plus an eSIM, both active at once.", "Maya Chen"),
    ("Aurora X5 5G Smartphone", "Is a charger included in the box?", "It ships with a 45W USB-C charger and cable.", "Jonas Weber"),
    ("Stratus Book 14\" Ultrabook", "Can the RAM be upgraded later?", "The RAM is soldered, so choose your configuration up front.", "Liam O'Brien"),
    ("EchoWave ANC Headphones", "Do these work wired for flights?", "Yes — a 3.5mm cable is included and ANC works in wired mode.", "Sofia Rossi"),
    ("VortexAir Fryer 5L", "Is the basket really dishwasher safe?", "Yes, both the basket and crisper tray are top-rack safe.", "Priya Nair"),
    ("BlockWorks Space Station Kit", "What ages is this suitable for?", "We recommend 9 and up due to small parts.", "Jonas Weber"),
]

PROMOS = [
    ("SAVE10", 10, 0),
    ("WELCOME15", 15, 30),
    ("VIP20", 20, 100),
]


def seed():
    db.drop_all()
    db.create_all()
    print("· database recreated")

    cats = {}
    for name, slug, parent_slug in CATEGORIES:
        cat = Category(name=name, slug=slug,
                       parent_id=cats[parent_slug].id if parent_slug else None)
        db.session.add(cat)
        db.session.flush()
        cats[slug] = cat

    products = {}
    for (name, brand, price, deal, stock, cat_slug, imgs, desc, featured) in PRODUCTS:
        p = Product(
            name=name, slug=unique_slug(Product, name), brand=brand, price=price,
            deal_price=deal, stock=stock, category_id=cats[cat_slug].id,
            description=desc, is_deal=bool(deal), is_featured=featured,
        )
        db.session.add(p)
        db.session.flush()
        products[name] = p
        for idx, img in enumerate(imgs):
            db.session.add(ProductImage(
                product_id=p.id, url=f"/static/images/{img}.svg", alt=name,
                is_primary=(idx == 0), sort_order=idx))
    print(f"· {len(products)} products across {len(cats)} categories")

    admin = Customer(name="Avery Admin", email="admin@shoplinq.com", is_admin=True)
    admin.set_password("adminpass123")
    demo = Customer(name="Demo Demo", email="demo@shoplinq.com")
    demo.set_password("demopass123")
    db.session.add_all([admin, demo])
    db.session.flush()

    addr = Address(
        customer_id=demo.id, label="Home", full_name="Demo Demo",
        line1="42 Harbor Lane", city="Springfield", state="IL",
        postal_code="62701", country="United States", phone="+1 555 010 2030",
        is_default=True)
    db.session.add(addr)
    db.session.add(PaymentMethod(
        customer_id=demo.id, card_brand="Visa", last4="4242",
        exp_month=12, exp_year=2030, is_default=True))
    db.session.flush()

    # reviewers
    reviewers = {}
    for rname in ["Maya Chen", "Jonas Weber", "Priya Nair", "Liam O'Brien", "Sofia Rossi"]:
        first = rname.split(" ")[0].lower()
        u = Customer(name=rname, email=f"{first}@shoplinq.com")
        u.set_password("reviewerpass123")
        db.session.add(u)
        reviewers[rname] = u
    db.session.flush()

    for product_name, entries in REVIEWS.items():
        p = products[product_name]
        for (rname, rating, title, body) in entries:
            db.session.add(Review(
                product_id=p.id, customer_id=reviewers[rname].id,
                rating=rating, title=title, body=body))
    db.session.flush()
    for p in products.values():
        p.recompute_rating()
    print(f"· {sum(len(v) for v in REVIEWS.values())} reviews written")

    for (product_name, q, a, author) in QA:
        db.session.add(ProductQA(
            product_id=products[product_name].id, question=q, answer=a,
            author=author))
    print(f"· {len(QA)} Q&A entries")

    for code, pct, min_spend in PROMOS:
        db.session.add(PromoCode(code=code, discount_percent=pct, min_spend=min_spend))
    db.session.flush()

    # demo orders at different stages
    def make_order(customer, items, status, days_ago, address):
        order = Order(
            customer_id=customer.id,
            order_number=f"SL2026{days_ago:03d}-DEMO",
            status=status,
            subtotal=round(sum(p.effective_price * q for p, q in items), 2),
            tax=0, shipping_fee=0, total=0,
            delivery_method="standard",
            ship_name=address["full_name"], ship_line1=address["line1"],
            ship_city=address["city"], ship_state=address["state"],
            ship_postal_code=address["postal_code"], ship_country=address["country"],
            ship_phone=address.get("phone"),
            placed_date=utcnow() - timedelta(days=days_ago),
        )
        subtotal = order.subtotal
        order.tax = round(subtotal * 0.08, 2)
        order.shipping_fee = 0 if subtotal >= 50 else 4.99
        order.total = round(subtotal + order.tax + order.shipping_fee, 2)
        db.session.add(order)
        db.session.flush()
        for p, q in items:
            db.session.add(OrderItem(
                order_id=order.id, product_id=p.id, product_name=p.name,
                product_slug=p.slug,
                image_url=p.primary_image.url if p.primary_image else None,
                unit_price=p.effective_price, quantity=q))
        shipping = Shipping(
            order_id=order.id, tracking_number=f"SLXDEMO{days_ago:03d}",
            status=status, estimated_delivery=order.placed_date + timedelta(days=5))
        flow = ["placed", "packed", "shipped", "out_for_delivery", "delivered"]
        upto = flow.index(status) + 1 if status in flow else 1
        for i, step in enumerate(flow[:upto]):
            shipping.record(step, when=order.placed_date + timedelta(days=i))
        db.session.add(shipping)
        db.session.add(Payment(
            order_id=order.id, method="card", status="paid",
            amount=order.total, card_brand="Visa", last4="4242",
            paid_date=order.placed_date))
        return order

    demo_addr = addr.as_dict()
    o1 = make_order(demo, [(products["Aurora X5 5G Smartphone"], 1),
                           (products["EchoWave Buds Air"], 1)],
                    "delivered", 14, demo_addr)
    o2 = make_order(demo, [(products["VortexAir Fryer 5L"], 1),
                           (products["Lumina Vitamin C Serum"], 2),
                           (products["Deep Work Habits"], 1)],
                    "out_for_delivery", 6, demo_addr)
    o3 = make_order(demo, [(products["Stratus Book 14\" Ultrabook"], 1)],
                    "shipped", 2, demo_addr)
    db.session.add_all([o1, o2, o3])
    db.session.flush()

    # wishlist for demo
    for name in ["Pulse Boom Mini Speaker", "Solstice Wrap Dress", "BlockWorks Space Station Kit"]:
        db.session.add(WishlistItem(customer_id=demo.id, product_id=products[name].id))
    db.session.add(Cart(customer_id=demo.id))
    db.session.commit()
    print(f"· demo customer + 3 orders (delivered / out for delivery / shipped)")
    print("\nSeed complete! Accounts:")
    print("  admin: admin@shoplinq.com / adminpass123")
    print("  demo:  demo@shoplinq.com  / demopass123")


if __name__ == "__main__":
    with app.app_context():
        seed()
