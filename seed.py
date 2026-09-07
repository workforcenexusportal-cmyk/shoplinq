"""Seed the ShopLinq database with a production-scale demo catalog.

Run:  python seed.py   (fresh database — wipes existing data first)

Generates:
  * 255 categories (22 roots + 233 subcategories)
  * 5,000+ products (35 hand-crafted "hero" products + synthetic catalog)
  * hundreds of reviews, dozens of demo orders across 6 months,
    promo codes, wishlists, Q&A — everything the UI needs to feel real.
"""
import random
from datetime import timedelta

from app import create_app, _bootstrap_local_env
from extensions import db
from models import (
    Address, Cart, Category, Customer, Order, OrderItem, Payment,
    PaymentMethod, Product, ProductImage, ProductQA, PromoCode, Review,
    Shipping, WishlistItem, utcnow,
)
from services import cache_clear, slugify

_bootstrap_local_env()  # zero-config first run: make a local .env if missing
app = create_app()
random.seed(4242)  # reproducible catalog

# ================================================================ catalog

# Each root: (name, theme, (price_lo, price_hi), [(sub, [types...]), ...])
ROOTS = [
    ("Electronics", "electronics", (14.99, 2499.00), [
        ("Mobile Phones", ["5G Smartphone", "Foldable Phone", "Rugged Smartphone", "Compact Phone"]),
        ("Laptops & Notebooks", ["Ultrabook", "Gaming Laptop", "Creator Laptop", "Chromebook", "2-in-1 Laptop"]),
        ("Audio & Headphones", ["Wireless Earbuds", "ANC Headphones", "Bluetooth Speaker", "Soundbar", "Studio Monitor"]),
        ("Cameras & Drones", ["Mirrorless Camera", "Action Camera", "Camera Drone", "Vlogging Camera"]),
        ("TV & Home Theater", ["4K Smart TV", "OLED TV", "Streaming Stick", "Laser Projector", "AV Receiver"]),
        ("Wearable Tech", ["Smartwatch", "Fitness Tracker", "Smart Ring", "VR Headset"]),
        ("Gaming", ["Gaming Console", "Handheld Console", "Pro Controller", "Gaming Headset"]),
        ("Tablets & E-Readers", ["Tablet", "E-Reader", "Kids Tablet", "Stylus Pen"]),
        ("Computer Accessories", ["Mechanical Keyboard", "Wireless Mouse", "Monitor", "USB-C Hub", "Webcam"]),
        ("Components & Storage", ["NVMe SSD", "Graphics Card", "RAM Kit", "External Drive"]),
        ("Networking", ["WiFi 6 Router", "Mesh WiFi System", "Ethernet Switch", "NAS Drive"]),
        ("Smart Home", ["Smart Speaker", "Security Camera", "Smart Thermostat", "Smart Doorbell"]),
        ("Portable Power", ["Power Bank", "Wireless Charger", "Solar Charger", "Laptop Charger"]),
        ("Hobby Electronics", ["Soldering Kit", "Arduino Starter Kit", "Raspberry Pi Kit", "Electronics Toolkit"]),
    ]),
    ("Home & Kitchen", "home", (8.99, 799.00), [
        ("Cookware", ["Frying Pan", "Stockpot", "Wok", "Knife Set", "Cutting Board Set"]),
        ("Small Appliances", ["Air Fryer", "Espresso Machine", "Blender", "Toaster Oven", "Stand Mixer"]),
        ("Coffee & Tea", ["Pour-Over Kit", "Electric Kettle", "Milk Frother", "Tea Sampler"]),
        ("Kitchen Storage", ["Glass Container Set", "Spice Rack", "Pantry Jars", "Food Wrap Set"]),
        ("Bedding", ["Sheet Set", "Down Comforter", "Memory Foam Pillow", "Mattress Topper"]),
        ("Bathroom", ["Towel Set", "Shower Caddy", "Bath Mat", "Bathrobe"]),
        ("Home Décor", ["Wall Art Set", "Throw Pillow Set", "Table Lamp", "Area Rug"]),
        ("Dining & Entertaining", ["Dinnerware Set", "Wine Glass Set", "Serving Board", "Flatware Set"]),
        ("Vacuum & Cleaning", ["Robot Vacuum", "Cordless Vacuum", "Steam Mop", "Cleaning Kit"]),
        ("Air Quality", ["Air Purifier", "Humidifier", "Dehumidifier", "Tower Fan"]),
        ("Laundry", ["Laundry Hamper", "Drying Rack", "Fabric Steamer", "Ironing Board"]),
        ("Kitchen Linens", ["Apron Set", "Dish Towel Set", "Oven Mitts", "Table Runner"]),
        ("Home Office", ["Desk Organizer", "Monitor Stand", "Cable Management Kit", "Desk Lamp"]),
        ("Entryway & Storage", ["Storage Bins", "Closet Organizer", "Shoe Rack", "Entryway Bench"]),
    ]),
    ("Furniture", "furniture", (39.00, 1999.00), [
        ("Living Room", ["Fabric Sofa", "Sectional Sofa", "Coffee Table", "TV Stand", "Accent Chair"]),
        ("Bedroom", ["Bed Frame", "Nightstand", "Dresser", "Wardrobe"]),
        ("Office Furniture", ["Standing Desk", "Office Chair", "Bookshelf", "Filing Cabinet"]),
        ("Dining Room", ["Dining Table", "Dining Chair", "Bar Stool Set", "Sideboard"]),
        ("Entryway", ["Console Table", "Shoe Cabinet", "Coat Rack"]),
        ("Kids' Room", ["Bunk Bed", "Kids' Desk", "Toy Storage"]),
        ("Outdoor", ["Patio Conversation Set", "Adirondack Chair", "Outdoor Bench", "Porch Swing"]),
        ("Lighting", ["Floor Lamp", "Pendant Light", "Wall Sconce", "LED Strip Kit"]),
        ("Home Accents", ["Wall Mirror", "Room Divider", "Mantel Clock", "Decorative Ladder"]),
    ]),
    ("Men's Fashion", "men", (12.00, 349.00), [
        ("Tees & Polos", ["Crew Tee", "Polo Shirt", "Henley", "Pocket Tee"]),
        ("Shirts", ["Oxford Shirt", "Flannel Shirt", "Dress Shirt", "Linen Shirt"]),
        ("Pants & Denim", ["Slim Jeans", "Chino Pants", "Joggers", "Cargo Pants"]),
        ("Outerwear", ["Rain Jacket", "Puffer Jacket", "Bomber Jacket", "Softshell Vest"]),
        ("Activewear", ["Training Shorts", "Performance Tee", "Track Jacket", "Swim Trunks"]),
        ("Footwear", ["Running Shoes", "Leather Sneakers", "Chelsea Boots", "Hiking Boots"]),
        ("Watches & Accessories", ["Wrist Watch", "Leather Belt", "Wallet", "Sunglasses"]),
        ("Underwear & Socks", ["Boxer Briefs", "Crew Socks", "Undershirts"]),
        ("Suits & Formal", ["Blazer", "Suit Separates", "Leather Oxfords", "Bow Tie"]),
        ("Streetwear", ["Graphic Hoodie", "Cargo Shorts", "Bucket Hat", "Chunky Sneakers"]),
    ]),
    ("Women's Fashion", "women", (12.00, 399.00), [
        ("Dresses", ["Wrap Dress", "Maxi Dress", "Midi Dress", "Summer Sundress"]),
        ("Tops & Blouses", ["Blouse", "Knit Sweater", "Crop Top", "Tunic"]),
        ("Trousers & Denim", ["High-Rise Jeans", "Wide-Leg Trousers", "Leggings", "Culottes"]),
        ("Coats & Jackets", ["Trench Coat", "Wool Coat", "Quilted Jacket", "Denim Jacket"]),
        ("Shoes & Boots", ["Sneakers", "Ankle Boots", "Ballet Flats", "Sandals"]),
        ("Handbags", ["Tote Bag", "Crossbody Bag", "Shoulder Bag", "Clutch"]),
        ("Workout Wear", ["Yoga Leggings", "Sports Bra", "Running Shorts", "Zip-Up Hoodie"]),
        ("Jewelry", ["Stud Earrings", "Pendant Necklace", "Bracelet", "Hoop Earrings"]),
        ("Swimwear", ["One-Piece Swimsuit", "Bikini Set", "Cover-Up", "Rash Guard"]),
        ("Loungewear", ["Pajama Set", "Fleece Robe", "Lounge Pants", "Slippers"]),
        ("Denim", ["Skinny Jeans", "Mom Jeans", "Denim Skirt", "Denim Overalls"]),
        ("Workwear", ["Blazer", "Pencil Skirt", "Tailored Trousers", "Silk Blouse"]),
    ]),
    ("Beauty & Personal Care", "beauty", (5.99, 189.00), [
        ("Skincare", ["Vitamin C Serum", "Moisturizer", "Night Cream", "Sunscreen", "Face Mask Set"]),
        ("Hair Care", ["Shampoo", "Conditioner", "Hair Mask", "Hair Dryer", "Curling Iron"]),
        ("Hair Styling", ["Straightener", "Curling Wand", "Hair Dryer Brush", "Hot Brush Set"]),
        ("Makeup", ["Lipstick Set", "Foundation", "Mascara", "Eyeshadow Palette", "Blush"]),
        ("Fragrance", ["Eau de Parfum", "Cologne", "Body Mist", "Perfume Gift Set"]),
        ("Men's Grooming", ["Beard Kit", "Safety Razor", "Trimmer", "Aftershave Balm"]),
        ("Bath & Body", ["Body Lotion", "Bath Bombs", "Body Scrub", "Shower Gel"]),
        ("Tools & Brushes", ["Makeup Brush Set", "Jade Roller", "Hair Brush", "Beauty Blender"]),
        ("Oral Care", ["Electric Toothbrush", "Whitening Kit", "Water Flosser"]),
        ("Nails", ["Nail Polish Set", "Manicure Kit", "Gel Kit", "Cuticle Oil"]),
        ("Wellness Devices", ["LED Face Mask", "Microcurrent Wand", "Scalp Massager"]),
    ]),
    ("Health & Household", "health", (4.99, 129.00), [
        ("Vitamins & Supplements", ["Multivitamin", "Vitamin D3", "Omega-3 Capsules", "Protein Powder"]),
        ("Pain Relief", ["Heating Pad", "Muscle Balm", "Ice Pack Wrap", "TENS Unit"]),
        ("First Aid", ["First Aid Kit", "Bandage Set", "Antiseptic Spray", "Kinesiology Tape"]),
        ("Household Supplies", ["Laundry Detergent", "Trash Bags", "Paper Towels", "Cleaning Wipes"]),
        ("Medical Supplies", ["Digital Thermometer", "Blood Pressure Monitor", "Pulse Oximeter"]),
        ("Sleep", ["Sleep Mask", "Weighted Blanket", "White Noise Machine"]),
        ("Mobility", ["Knee Brace", "Ankle Support", "Wrist Brace", "Posture Corrector"]),
        ("Mental Wellness", ["Meditation Cushion", "Journal Set", "Stress Ball Set", "Weighted Eye Mask"]),
        ("Home Health", ["Vaporizer", "Nebulizer", "Heating Wrap", "Pill Organizer"]),
    ]),
    ("Sports & Outdoors", "sports", (8.99, 899.00), [
        ("Exercise & Fitness", ["Adjustable Dumbbells", "Yoga Mat", "Resistance Band Set", "Kettlebell"]),
        ("Camping & Hiking", ["Daypack", "Camping Tent", "Sleeping Bag", "Trekking Poles"]),
        ("Yoga & Pilates", ["Yoga Blocks", "Pilates Ring", "Yoga Strap", "Pilates Mat"]),
        ("Cycling", ["Mountain Bike", "Road Bike", "Bike Helmet", "Bike Trainer"]),
        ("Water Sports", ["Paddleboard", "Kayak", "Snorkel Set", "Wetsuit"]),
        ("Running", ["Trail Running Shoes", "Running Belt", "Hydration Vest", "Reflective Vest"]),
        ("Team Sports", ["Soccer Ball", "Basketball", "Volleyball Set", "Disc Golf Set"]),
        ("Racquet Sports", ["Tennis Racket", "Pickleball Set", "Badminton Set", "Table Tennis Paddle"]),
        ("Golf", ["Golf Club Set", "Golf Glove", "Putting Mat", "Golf Bag"]),
        ("Winter Sports", ["Ski Jacket", "Snowboard", "Thermal Base Layer", "Ski Goggles"]),
        ("Fishing", ["Spinning Rod", "Tackle Box", "Fishing Reel", "Waders"]),
        ("Outdoor Gear", ["Headlamp", "Camp Stove", "Cooler Box", "Multi-Tool"]),
        ("Boxing & MMA", ["Punching Bag", "Boxing Gloves", "Hand Wraps", "Speed Ladder"]),
        ("Recovery", ["Massage Gun", "Foam Roller", "Massage Ball", "Compression Boots"]),
    ]),
    ("Toys & Games", "toys", (6.99, 299.00), [
        ("Building Sets", ["Space Station Kit", "Castle Build", "Race Car Set", "Robot Starter Set"]),
        ("Board Games", ["Strategy Board Game", "Family Board Game", "Card Game", "Party Game"]),
        ("Puzzles", ["1000-Piece Puzzle", "3D Puzzle", "Kids' Puzzle Set", "Wooden Puzzle"]),
        ("Dolls & Plush", ["Stuffed Animal", "Fashion Doll", "Interactive Plush", "Baby Doll Set"]),
        ("Outdoor Play", ["Trampoline", "Swing Set", "Slip & Slide", "Bubble Machine"]),
        ("Learning & STEM", ["Science Kit", "Microscope Set", "Coding Robot", "Solar Robot Kit"]),
        ("Action Figures", ["Hero Action Figure", "Collectible Figure", "Playset", "Model Kit"]),
        ("Baby & Toddler Toys", ["Stacking Rings", "Pull-Along Toy", "Soft Blocks", "Musical Table"]),
        ("Video Games", ["Action Game", "Racing Game", "Puzzle Game", "Sports Game"]),
        ("Ride-Ons & Scooters", ["Kick Scooter", "Balance Bike", "Electric Ride-On", "Skateboard"]),
        ("Collectibles", ["Trading Card Set", "Collector's Display Case", "Minifigure Set", "Mystery Box"]),
        ("Musical Toys", ["Toy Piano", "Xylophone", "Kids' Drum Set", "Tambourine Set"]),
    ]),
    ("Baby", "baby", (5.99, 499.00), [
        ("Diapering", ["Diaper Bag", "Changing Pad", "Cloth Diapers", "Diaper Pail"]),
        ("Feeding", ["Baby Bottle Set", "High Chair", "Breast Pump", "Baby Food Maker"]),
        ("Baby Gear", ["Stroller", "Baby Carrier", "Car Seat", "Portable Crib"]),
        ("Nursery", ["Crib", "Glider Chair", "Nursery Dresser", "Baby Monitor"]),
        ("Bath & Care", ["Baby Bathtub", "Baby Towel Set", "Baby Lotion", "Grooming Kit"]),
        ("Baby Toys", ["Rattle Set", "Activity Gym", "Teether", "Stroller Toy"]),
        ("Baby Clothing", ["Onesie Set", "Sleep Sack", "Baby Booties", "Sun Hat"]),
        ("Safety", ["Baby Gate", "Corner Guards", "Outlet Covers", "Cabinet Locks"]),
        ("Car Travel", ["Car Mirror", "Sun Shades", "Travel Bottle Warmer", "Backseat Organizer"]),
    ]),
    ("Pet Supplies", "pets", (4.99, 399.00), [
        ("Dogs", ["Dog Bed", "Dog Harness", "Dog Toy Set", "Dog Bowl Set", "Dog Leash"]),
        ("Cats", ["Cat Tree", "Cat Litter Box", "Cat Toy Set", "Cat Scratcher", "Cat Carrier"]),
        ("Fish & Aquatic", ["Aquarium Kit", "Fish Food", "Aquarium Filter", "Tank Décor Set"]),
        ("Small Pets", ["Hamster Cage", "Rabbit Hutch", "Guinea Pig Bedding", "Small Pet Toy"]),
        ("Birds", ["Bird Cage", "Bird Food", "Parrot Toy Set", "Bird Perch"]),
        ("Reptiles", ["Terrarium Kit", "Heat Lamp", "Reptile Bedding", "Terrarium Thermometer"]),
        ("Pet Grooming", ["Pet Brush", "Nail Trimmer", "Pet Shampoo", "Grooming Glove"]),
        ("Pet Food & Treats", ["Dog Treats", "Cat Treats", "Grain-Free Dog Food", "Dental Chews"]),
        ("Pet Health", ["Flea Collar", "Joint Supplements", "Calming Chews", "Pet First-Aid Kit"]),
        ("Pet Travel", ["Pet Carrier", "Travel Bowl", "Car Seat Cover", "Backpack Carrier"]),
    ]),
    ("Automotive", "auto", (7.99, 699.00), [
        ("Car Electronics", ["Dash Cam", "Car Stereo", "GPS Navigator", "Backup Camera"]),
        ("Car Care", ["Wax Kit", "Microfiber Towel Set", "Interior Cleaner", "Tire Shine"]),
        ("Interior Accessories", ["Seat Covers", "Floor Mats", "Steering Wheel Cover", "Seat Organizer"]),
        ("Exterior Accessories", ["Car Cover", "Roof Rack", "Cargo Box", "Window Visors"]),
        ("Oils & Fluids", ["Engine Oil", "Coolant", "Brake Fluid", "Wiper Fluid Set"]),
        ("Tools & Equipment", ["Jump Starter", "Tire Inflator", "OBD2 Scanner", "Roadside Kit"]),
        ("Auto Lighting", ["LED Headlight Kit", "Interior LED Kit", "Fog Lights", "Light Bars"]),
        ("Motorcycle", ["Helmet", "Riding Gloves", "Saddlebags", "Phone Mount"]),
        ("Replacement Parts", ["Wiper Blades", "Air Filter", "Cabin Filter", "Brake Pads"]),
        ("RV & Trailer", ["RV Cover", "Tire Chocks", "Trailer Hitch", "Leveling Blocks"]),
    ]),
    ("Tools & Home Improvement", "tools", (5.99, 899.00), [
        ("Power Tools", ["Cordless Drill", "Impact Driver", "Circular Saw", "Angle Grinder"]),
        ("Hand Tools", ["Screwdriver Set", "Wrench Set", "Hammer", "Pliers Set"]),
        ("Hardware", ["Screws Set", "Wall Anchors", "Drawer Slides", "Padlocks"]),
        ("Measuring", ["Laser Level", "Tape Measure", "Digital Caliper", "Stud Finder"]),
        ("Painting", ["Paint Roller Kit", "Painter's Tape", "Drop Cloths", "Paint Sprayer"]),
        ("Electrical", ["Smart Switch", "Wiring Kit", "Outlet Tester", "Surge Protector"]),
        ("Plumbing", ["Pipe Wrench", "Drain Snake", "Shower Head", "Faucet Kit"]),
        ("Smart Home Devices", ["Smart Lock", "Smart Bulb Set", "Smart Plug", "Video Doorbell"]),
        ("Safety Gear", ["Work Gloves", "Safety Glasses", "Hard Hat", "Ear Protection"]),
        ("Storage & Organization", ["Tool Box", "Pegboard Set", "Parts Organizer", "Tool Belt"]),
        ("Lighting Fixtures", ["LED Shop Light", "Motion Sensor Light", "Cabinet Lighting", "Emergency Light"]),
        ("Woodworking", ["Chisel Set", "Wood Plane", "Clamps Set", "Saw Horses"]),
        ("Welding", ["Welding Machine", "Welding Helmet", "Welding Gloves", "Welding Rods"]),
    ]),
    ("Garden & Outdoor", "garden", (8.99, 549.00), [
        ("Plants & Seeds", ["Seed Kit", "Succulent Set", "Indoor Plant", "Seedling Set"]),
        ("Garden Tools", ["Pruning Shears", "Garden Trowel Set", "Hose Reel", "Garden Hoe"]),
        ("Pots & Planters", ["Planter Set", "Raised Bed Kit", "Hanging Planter", "Self-Watering Pot"]),
        ("Outdoor Décor", ["Wind Chimes", "Garden Flags", "Solar Lantern Set", "Bird Bath"]),
        ("Grills & Cooking", ["Gas Grill", "Charcoal Grill", "Pizza Oven", "Grilling Tool Set"]),
        ("Greenhouses", ["Mini Greenhouse", "Cold Frame", "Grow Light Kit", "Plant Starter Kit"]),
        ("Pest Control", ["Insect Trap Set", "Plant Spray", "Garden Netting", "Slug Traps"]),
        ("Watering", ["Sprinkler System", "Watering Can", "Drip Irrigation Kit", "Spray Nozzle"]),
        ("Snow & Seasonal", ["Snow Shovel", "Ice Scraper", "Snow Blower", "De-Icing Salt"]),
        ("Lawn Care", ["Lawn Mower", "String Trimmer", "Leaf Blower", "Garden Hose"]),
    ]),
    ("Grocery", "grocery", (3.99, 89.00), [
        ("Coffee Shop", ["Whole Bean Coffee", "Green Tea Set", "Herbal Tea", "Cold Brew Kit"]),
        ("Snacks", ["Mixed Nuts", "Protein Bars", "Chocolate Set", "Granola"]),
        ("Pantry", ["Olive Oil", "Pasta Set", "Spice Set", "Honey Jars"]),
        ("Beverages", ["Sparkling Water", "Juice Set", "Energy Drinks", "Lemonade Mix"]),
        ("Breakfast", ["Oatmeal Set", "Cereal Variety Pack", "Pancake Mix", "Maple Syrup"]),
        ("Baking", ["Flour Set", "Baking Chocolate", "Vanilla Extract", "Sprinkles Set"]),
        ("Condiments", ["Hot Sauce Set", "Mustard Trio", "BBQ Sauce", "Spice Rubs"]),
        ("International", ["Ramen Set", "Taco Kit", "Curry Set", "Biscotti Tin"]),
        ("Gift Sets", ["Coffee Gift Box", "Snack Gift Basket", "Tea Gift Set", "Chocolate Gift Box"]),
    ]),
    ("Books", "books", (6.99, 59.99), [
        ("Fiction", ["Mystery Novel", "Sci-Fi Novel", "Romance Novel", "Literary Fiction", "Thriller"]),
        ("Non-Fiction", ["History Book", "Science Book", "Memoir", "Business Book"]),
        ("Children's Books", ["Picture Book", "Early Reader Set", "Bedtime Story Collection", "Kids' Encyclopedia"]),
        ("Comics & Graphic Novels", ["Graphic Novel", "Manga Volume", "Comic Collection", "Comic Omnibus"]),
        ("Reference & Education", ["Dictionary", "Atlas", "Study Guide", "Test Prep Book"]),
        ("Cookbooks", ["Baking Cookbook", "Weeknight Dinners", "Grilling Cookbook", "Cocktail Book"]),
        ("Art & Photography", ["Photography Book", "Art History Book", "Coffee Table Book", "Design Book"]),
        ("Poetry", ["Poetry Collection", "Verse Anthology", "Haiku Set", "Poetry Journal"]),
        ("Young Adult", ["YA Fantasy", "YA Dystopian", "Teen Romance", "Coming-of-Age Novel"]),
    ]),
    ("Music", "music", (8.99, 1299.00), [
        ("Instruments", ["Acoustic Guitar", "Electric Guitar", "Digital Piano", "Ukulele", "Drum Kit"]),
        ("Recording", ["USB Microphone", "Audio Interface", "Studio Headphones", "MIDI Keyboard"]),
        ("Vinyl & CDs", ["Vinyl Record", "Vinyl Box Set", "CD Album", "Deluxe Reissue"]),
        ("Instrument Accessories", ["Guitar Strings", "Guitar Case", "Piano Bench", "Capo & Picks Set"]),
        ("Karaoke", ["Karaoke Machine", "Wireless Mic Set", "Karaoke Speaker", "Fog Machine"]),
        ("Sheet Music", ["Songbook", "Piano Score", "Guitar Tab Book", "Method Book"]),
        ("Live Sound", ["PA Speaker", "Mixer Board", "Stage Monitor", "Cable Set"]),
        ("Percussion", ["Cajon", "Bongo Drums", "Tambourine", "Practice Pad"]),
    ]),
    ("Office Products", "office", (3.99, 549.00), [
        ("Desk Supplies", ["Pen Holder", "Desk Organizer", "Stapler", "Tape Dispenser"]),
        ("Paper & Stationery", ["Notebook Set", "Printer Paper", "Index Cards", "Stationery Set"]),
        ("Writing Instruments", ["Gel Pen Set", "Fountain Pen", "Mechanical Pencil Set", "Highlighters"]),
        ("Seating", ["Office Stool", "Standing Mat", "Seat Cushion", "Foot Rest"]),
        ("Office Electronics", ["Label Maker", "Paper Shredder", "Calculator", "Document Scanner"]),
        ("Presentation", ["Whiteboard", "Cork Board", "Easel Pad", "Projector Screen"]),
        ("Filing & Storage", ["Filing Box", "Binder Set", "Document Tray", "Archive Box"]),
        ("Calendars & Planners", ["Wall Calendar", "Daily Planner", "Academic Planner", "Desk Pad"]),
        ("Mail & Shipping", ["Packaging Tape", "Bubble Mailers", "Shipping Labels", "Box Set"]),
        ("Desk & Workspace", ["Desk Mat", "Monitor Riser", "Under-Desk Organizer", "Desk Drawer"]),
    ]),
    ("Arts & Crafts", "crafts", (4.99, 299.00), [
        ("Paint & Canvas", ["Acrylic Paint Set", "Watercolor Kit", "Canvas Set", "Paint Brushes"]),
        ("Drawing", ["Sketch Pad", "Pencil Set", "Markers Set", "Charcoal Kit"]),
        ("Sewing & Fabric", ["Sewing Kit", "Fabric Set", "Thread Set", "Sewing Machine"]),
        ("Knitting & Crochet", ["Yarn Set", "Crochet Kit", "Knitting Needles", "Pattern Book"]),
        ("Scrapbooking", ["Scrapbook Kit", "Sticker Set", "Craft Paper Pack", "Photo Corners"]),
        ("Kids' Crafts", ["Craft Box", "Slime Kit", "Bead Set", "Origami Paper"]),
        ("Jewelry Making", ["Bead Kit", "Wire Set", "Pliers Kit", "Pendant Blanks"]),
        ("Paper Crafts", ["Card Making Kit", "Quilling Set", "Stamp Set", "Embossing Kit"]),
        ("Model Making", ["Model Kit", "Model Paint Set", "Hobby Knife Set", "Airbrush Kit"]),
        ("Resin Art", ["Epoxy Resin Kit", "Resin Molds", "Pigment Set", "Resin Tools Set"]),
    ]),
    ("Luggage & Bags", "luggage", (14.99, 599.00), [
        ("Suitcases", ["Carry-On Suitcase", "Checked Luggage", "Hardside Spinner", "Luggage Set"]),
        ("Backpacks", ["Travel Backpack", "Daypack", "Laptop Backpack", "Hiking Pack"]),
        ("Duffels & Weekenders", ["Duffel Bag", "Weekender Bag", "Gym Duffel", "Rolling Duffel"]),
        ("Business Bags", ["Briefcase", "Messenger Bag", "Laptop Tote", "Document Sleeve"]),
        ("Travel Accessories", ["Packing Cubes", "Luggage Scale", "Travel Pillow", "Toiletry Bag"]),
        ("Utility Sling Bags", ["Fanny Pack", "Sling Bag", "Chest Pack", "Waist Belt"]),
        ("Kids' Bags", ["Kids' Backpack", "Lunch Box", "Kids' Rolling Luggage", "Drawstring Bag"]),
        ("Travel Comfort", ["Travel Blanket", "Footrest Hammock", "Travel Bottles Set", "Luggage Tags Set"]),
    ]),
    ("Jewelry & Watches", "jewelry", (18.99, 2499.00), [
        ("Fine Jewelry", ["Gold Necklace", "Diamond Studs", "Tennis Bracelet", "Sapphire Ring"]),
        ("Fashion Jewelry", ["Statement Necklace", "Cuff Bracelet", "Hoop Earrings", "Layered Necklace Set"]),
        ("Watches", ["Automatic Watch", "Quartz Watch", "Dive Watch", "Chronograph"]),
        ("Wedding & Engagement", ["Solitaire Ring", "Wedding Band Set", "Bridal Jewelry Set", "Anniversary Band"]),
        ("Sunglasses & Eyewear", ["Aviator Sunglasses", "Round Sunglasses", "Blue-Light Glasses", "Reading Glasses"]),
        ("Jewelry Storage", ["Jewelry Box", "Travel Case", "Ring Dish", "Watch Box"]),
        ("Charms & Brooches", ["Charm Bracelet", "Brooch Set", "Charm Set", "Anklet"]),
        ("Men's Jewelry", ["Signet Ring", "Leather Bracelet", "Curb Chain", "Stud Earrings Set"]),
        ("Body Jewelry", ["Nose Ring Set", "Ear Cuff Set", "Septum Ring", "Cartilage Set"]),
    ]),
    ("Industrial & Scientific", "industrial", (7.99, 1499.00), [
        ("Lab Supplies", ["Beaker Set", "Lab Coat", "Test Tube Rack", "Microscope"]),
        ("Safety Equipment", ["Safety Goggles", "Ear Muffs", "Respirator Mask", "Hi-Vis Vest"]),
        ("Fasteners", ["Bolt Kit", "Nut Assortment", "Washer Set", "Anchor Kit"]),
        ("Material Handling", ["Hand Truck", "Platform Cart", "Storage Tote Set", "Pallet Jack"]),
        ("Measuring Instruments", ["Digital Scale", "Infrared Thermometer", "Pressure Gauge", "Multimeter"]),
        ("Electrical Testing", ["Circuit Tester", "Wire Tracer", "Clamp Meter", "Power Supply Unit"]),
        ("Adhesives & Sealants", ["Epoxy Kit", "Silicone Sealant", "Threadlocker", "Super Glue Set"]),
        ("Packaging", ["Shrink Wrap Roll", "Strapping Kit", "Foam Sheets", "Box Bundle"]),
        ("Facility", ["Safety Sign Set", "Floor Marking Kit", "Spill Kit", "Lockout Tagout Set"]),
    ]),
]

# Hero products keep their multi-image galleries and hand-written copy.
# (name, brand, price, deal_price|None, stock, sub_slug, imgs, description, featured)
HEROES = [
    ("Aurora X5 5G Smartphone", "NovaTech", 699.99, 599.99, 42, "mobile-phones", ["phone-1", "phone-2", "phone-3"], "6.7\" AMOLED 120Hz display, triple 108MP camera system, 5000mAh battery with 45W fast charging. Unlocked for all carriers.", True),
    ("Aurora X5 Lite", "NovaTech", 349.99, None, 30, "mobile-phones", ["phone-2", "phone-1"], "Compact 6.1\" phone with dual camera, clean software and two-day battery life.", False),
    ("Helio S7 Pro", "Helio", 549.00, None, 18, "mobile-phones", ["phone-3", "phone-1"], "Flagship processor, IP68 water resistance and studio-grade portrait mode.", True),
    ("Zenith Fold Flex", "Zenith", 1299.00, None, 0, "mobile-phones", ["phone-3"], "Foldable 7.6\" tablet-phone hybrid with flex-hinge and wireless charging.", False),
    ("Stratus Book 14\" Ultrabook", "Stratus", 999.99, None, 15, "laptops-notebooks", ["laptop-1", "laptop-2"], "1.1kg magnesium chassis, 16-hour battery, 16GB RAM and 512GB NVMe storage.", True),
    ("Stratus Book Pro 16\"", "Stratus", 1899.99, 1699.99, 8, "laptops-notebooks", ["laptop-2", "laptop-1", "laptop-3"], "Creator-grade laptop with 32GB RAM, 1TB SSD and a 120Hz mini-LED display.", True),
    ("Cirrus Chrome Slim", "Cirrus", 449.00, None, 25, "laptops-notebooks", ["laptop-3", "laptop-1"], "Featherweight cloud laptop — boots in seconds, updates itself, all-day battery.", False),
    ("Zenith Studio Creator 15", "Zenith", 2199.00, None, 0, "laptops-notebooks", ["laptop-2"], "Mobile workstation with color-calibrated 4K panel for video and 3D work.", False),
    ("EchoWave ANC Headphones", "EchoWave", 199.99, 149.99, 60, "audio-headphones", ["audio-1", "audio-2"], "Hybrid active noise cancelling, 40-hour battery, multipoint Bluetooth 5.3.", True),
    ("EchoWave Buds Air", "EchoWave", 89.99, None, 80, "audio-headphones", ["audio-2", "audio-1"], "True wireless earbuds with transparency mode and wireless charging case.", True),
    ("Pulse Boom Mini Speaker", "Pulse", 59.99, None, 35, "audio-headphones", ["audio-3", "audio-1"], "Pocket-sized 360° speaker, IP67 waterproof, 18 hours of playtime.", False),
    ("Copperline 10-Piece Cookware Set", "Copperline", 249.99, 199.99, 22, "cookware", ["home-1", "home-3"], "Tri-ply stainless pots and pans with stay-cool handles — induction ready.", True),
    ("Copperline Chef's Knife 8\"", "Copperline", 69.99, None, 40, "cookware", ["home-1", "home-2"], "German steel, full tang, razor-sharp edge that holds through years of prep.", False),
    ("BrewMaster Espresso Machine", "BrewMaster", 399.00, None, 12, "small-appliances", ["home-2", "home-1"], "15-bar pump espresso maker with steam wand and precision temperature control.", True),
    ("VortexAir Fryer 5L", "Vortex", 129.99, None, 48, "small-appliances", ["home-3", "home-2"], "Crispy results with 90% less oil — 8 presets, dishwasher-safe basket.", True),
    ("PureSip Glass Bottle Set (6)", "PureSip", 29.99, None, 100, "kitchen-storage", ["home-3", "home-1"], "Borosilicate water bottles with leakproof bamboo lids.", False),
    ("Northpeak Rain Jacket", "Northpeak", 119.00, None, 28, "outerwear", ["fashion-1", "fashion-2"], "2.5-layer waterproof shell with pit zips and packs into its own pocket.", False),
    ("Everyday Merino Tee", "Loom & Co", 49.50, None, 65, "tees-polos", ["fashion-2", "fashion-1"], "17.5 micron merino jersey — breathable, odor-resistant, impossibly soft.", True),
    ("Solstice Wrap Dress", "Solstice", 89.00, 69.00, 20, "dresses", ["fashion-3", "fashion-2"], "Fluid wrap silhouette in machine-washable crepe, sizes XS–XXL.", False),
    ("Cloudstep Sneakers", "Cloudstep", 94.99, None, 55, "shoes-boots", ["fashion-2", "fashion-3"], "Featherlight knit uppers with responsive cushioning for all-day wear.", True),
    ("Northpeak Insulated Vest", "Northpeak", 99.00, None, 0, "coats-jackets", ["fashion-1"], "650-fill responsible down vest that layers under anything.", False),
    ("The Silent Algorithm (Hardcover)", "Northgate Press", 24.00, None, 33, "fiction", ["book-1", "book-2"], "A near-future thriller about the machines that curate our lives. 416 pages.", False),
    ("Deep Work Habits", "Bright Mind", 18.99, None, 47, "nonfiction", ["book-2", "book-1"], "A practical field guide to focused work in a distracted world.", True),
    ("Atlas of Small Journeys", "Northgate Press", 32.50, None, 19, "art-photography", ["book-3", "book-2"], "Illustrated travels through 40 of the world's overlooked places.", False),
    ("Cooking for One, Well", "Bright Mind", 21.00, None, 0, "cookbooks", ["home-2"], "90 single-serving recipes that never feel like a compromise.", False),
    ("Trailblazer Daypack 30L", "Trailblazer", 84.99, None, 36, "camping-hiking", ["sport-1", "sport-2"], "Ventilated back panel, rain cover included, laptop sleeve for hybrid days.", True),
    ("FlexCore Yoga Mat", "FlexCore", 39.99, None, 58, "yoga-pilates", ["sport-2", "sport-1"], "6mm cushioned mat with alignment lines and non-slip natural rubber.", False),
    ("Trailblazer Insulated Flask", "Trailblazer", 27.99, None, 70, "outdoor-gear", ["sport-1"], "Keeps drinks cold 24 hours, hot 12 — leakproof one-hand lid.", False),
    ("Velocity Jump Rope Pro", "Velocity", 17.99, None, 90, "exercise-fitness", ["sport-2"], "Ball-bearing speed rope with adjustable steel cable.", False),
    ("Lumina Vitamin C Serum", "Lumina", 34.00, None, 44, "skincare", ["beauty-1", "beauty-2"], "15% stabilized vitamin C with ferulic acid for visible brightness in 4 weeks.", True),
    ("Lumina Hydra Cream", "Lumina", 28.00, None, 51, "skincare", ["beauty-2", "beauty-1"], "72-hour moisture barrier cream with ceramides and squalane.", False),
    ("Freshline Hair Repair Kit", "Freshline", 22.50, None, 38, "hair-care", ["beauty-1"], "Bond-repair shampoo and mask duo for over-processed hair.", False),
    ("BlockWorks Space Station Kit", "BlockWorks", 59.99, None, 26, "building-sets", ["toy-1", "toy-2"], "1,050-piece buildable orbital station with 4 mini-figures. Ages 9+.", True),
    ("Puzzle Peak 1000-Piece Alpine", "Puzzle Peak", 19.99, None, 42, "puzzles", ["toy-2", "toy-1"], "Matte-finish panoramic puzzle of an alpine valley at golden hour.", False),
    ("BlockWorks Robot Starter Set", "BlockWorks", 44.99, None, 0, "learning-stem", ["toy-1"], "Screen-free coding robot with 60 progressive challenge cards. Ages 6+.", False),
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
    ("Copperline Chef's Knife 8\""): [("Priya Nair", 5, "Scary sharp", "Slices tomatoes like they're nothing.")],
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
    ("WELCOME15", 15, 2400),
    ("VIP20", 20, 7999),
]

# ================================================================ generator banks

SERIES = ["Aurora", "Zen", "Nova", "Prime", "Vertex", "Pulse", "Cobalt", "Summit",
          "Orbit", "Lumen", "Vantage", "Ember", "Terra", "Aero", "Atlas", "Flux",
          "Halo", "Onyx", "Sage", "Rift", "Cascade", "Solace", "Beacon", "Drift",
          "Evolve", "Fable", "Gale", "Harbor", "Ionic", "Kestrel", "Mesa", "Nimbus",
          "Pinnacle", "Quartz", "Ranger", "Titan", "Umber", "Willow", "Zephyr"]
MODELS = ["M1", "M2", "S3", "S5", "X2", "X7", "7", "8", "12", "200", "300", "500",
          "Pro", "Pro Max", "Plus", "Lite", "Ultra", "Mini", "One", "Elite"]
BRANDS = ["NovaTech", "Stratus", "Zenith", "Helio", "Cirrus", "EchoWave", "Pulse",
          "Copperline", "BrewMaster", "Vortex", "PureSip", "Northpeak", "Loom & Co",
          "Solstice", "Cloudstep", "Trailblazer", "FlexCore", "Velocity", "Lumina",
          "Freshline", "BlockWorks", "Puzzle Peak", "Northgate Press", "Bright Mind",
          "Hearthstone", "PantryCraft", "Nestwell", "Verdant", "Timberline", "Oakhearth",
          "Slate & Oak", "Loftworks", "Cartelle", "Kestrel Labs", "Pixonar", "Voltaix",
          "Beacon Hill", "Marlowe", "Juniper Goods", "Alcott", "Ridgeview", "Cascadia",
          "Wavelength", "Foundry Co", "Bluebird Home", "Meridian", "Ashgrove",
          "Copperwell", "Larkspur", "Stonebridge", "Halcyon", "Fernway", "Brookfield"]

FEATURES = {
    "electronics": ["blazing-fast performance", "all-day battery life", "premium metal chassis",
                    "intuitive controls", "seamless connectivity", "crystal-clear display"],
    "home": ["durable everyday construction", "easy-clean finish", "space-saving design",
             "heat- and stain-resistant", "family-friendly sizing", "modern minimalist look"],
    "furniture": ["solid hardwood frame", "stain-resistant upholstery", "tool-free assembly",
                  "compact footprint", "weight-rated construction", "timeless finish"],
    "men": ["true-to-size fit", "breathable premium fabric", "reinforced stitching",
            "machine-washable", "versatile styling", "all-season comfort"],
    "women": ["flattering cut", "stretch comfort fabric", "easy-care machine washable",
              "transition-ready styling", "soft hand feel", "wardrobe staple"],
    "beauty": ["dermatologist-tested formula", "clean ingredients", "long-lasting results",
               "gentle on sensitive skin", "cruelty-free", "salon-grade quality"],
    "health": ["clinically-proven relief", "compact and portable", "latex-free materials",
               "household-safe", "easy to clean", "doctor-recommended design"],
    "sports": ["weatherproof build", "lightweight performance materials", "grippy non-slip texture",
               "packable design", "adjustable fit", "pro-grade durability"],
    "toys": ["child-safe materials", "screen-free play", "skill-building design",
             "drop-tested construction", "hours of open-ended fun", "award-winning concept"],
    "baby": ["pediatrician-approved", "BPA-free materials", "one-hand fold",
             "gentle on delicate skin", "wipeable surfaces", "grows with your child"],
    "pets": ["chew-resistant materials", "vet-recommended", "easy to wash",
             "non-toxic finish", "quiet operation", "pet-approved comfort"],
    "auto": ["universal fit", "all-weather durability", "precision-engineered",
             "easy no-drill install", "anti-scratch protection", "workshop-grade quality"],
    "tools": ["lifetime warranty", "ergonomic soft-grip handle", "heavy-duty steel construction",
              "corrosion-resistant coating", "precision-machined", "jobsite-tough"],
    "garden": ["UV-resistant materials", "season-long durability", "water-smart design",
               "easy assembly", "pollinator-friendly", "all-climate construction"],
    "grocery": ["small-batch quality", "all-natural ingredients", "responsibly sourced",
                "shelf-stable packaging", "award-winning taste", "no artificial additives"],
    "books": ["critically acclaimed", "bestselling author", "beautifully illustrated",
              "gift-ready edition", "engaging page-turner", "perfect for gift-giving"],
    "music": ["studio-grade sound", "roadworthy construction", "responsive feel",
              "beginner-friendly setup", "rich warm tone", "gig-ready durability"],
    "office": ["workspace-boosting design", "recycled materials", "smooth everyday use",
               "professional finish", "clutter-free organization", "built to last"],
    "crafts": ["artist-grade pigments", "smooth application", "beginner-friendly",
               "archival quality", "non-toxic formula", "generous kit contents"],
    "luggage": ["airline-carry-on compliant", "water-resistant shell", "smooth 360° wheels",
                "TSA-friendly locks", "expansion zipper", "lifetime repair support"],
    "jewelry": ["hypoallergenic materials", "conflict-free stones", "tarnish-resistant finish",
                "handcrafted detail", "certified quality", "gift-box packaging"],
    "industrial": ["OSHA-compliant design", "heavy-load rating", "corrosion-proof finish",
                   "calibrated accuracy", "workshop-tested", "bulk-value packaging"],
}

GENERIC_FEATURES = ["ships fast from our warehouse", "backed by a 30-day return policy",
                    "covered by the ShopLinq 2-year guarantee"]

REVIEW_TITLES = {
    5: ["Exceeded expectations", "Couldn't be happier", "Worth every penny",
        "Exactly what I needed", "Five stars, no notes"],
    4: ["Really good, minor quibbles", "Solid purchase", "Would buy again",
         "Very happy overall", "Great value"],
    3: ["Does the job", "Decent for the price", "Mixed feelings",
        "Fine, nothing special"],
    2: ["Expected more", "Not for me", "Disappointing quality"],
}
REVIEW_BODIES = {
    5: ["Arrived quickly and works perfectly. The quality is better than I expected at this price.",
        "I've used this daily for weeks now and it still feels brand new. Highly recommend.",
        "Bought one for myself and another as a gift — both of us love it.",
        "Exactly as described. The details are what make it — you can tell it's well made."],
    4: ["Great product overall. One small thing kept it from five stars, but I'd still buy again.",
        "Does everything promised. Took a little getting used to, but now it's part of my routine.",
        "Good quality and fair price. Shipping was quick too."],
    3: ["It's fine. Does what it says, but I expected slightly better finish for the money.",
        "Average. Works, no complaints, but nothing to get excited about."],
    2: ["Didn't hold up to regular use. Returning it was easy at least.",
        "Felt cheap in hand. Might be okay for occasional use, not daily."],
}

FLOW = ["placed", "packed", "shipped", "out_for_delivery", "delivered"]

PRODUCTS_PER_SUB = 22


INR_FACTOR = 80  # USD catalog ranges -> Indian price points


def psych_inr(x):
    """Round an already-INR amount to a psychological price ending in 9."""
    if x >= 20:
        return max(19, round(x / 10) * 10 - 1)
    return max(9, round(x))


def to_inr(usd):
    """Scale a USD catalog price to a psychological INR price.

    Whole rupees ending in 9 (Rs.1,299) above Rs.100; below that, whole
    rupees ending in 9 too (Rs.49, Rs.99).
    """
    x = usd * INR_FACTOR
    if x >= 20:
        return max(19, round(x / 10) * 10 - 1)
    return max(9, round(x))


def gen_price(lo, hi):
    return to_inr(random.uniform(lo, hi))


def gen_rating():
    rating = min(5.0, max(2.6, random.gauss(4.15, 0.45)))
    return round(rating, 1)


def gen_rating_count():
    r = random.random()
    if r < 0.30:
        return random.randint(3, 40)
    if r < 0.75:
        return random.randint(41, 300)
    return random.randint(301, 1500)


def gen_stock():
    r = random.random()
    if r < 0.07:
        return 0
    if r < 0.15:
        return random.randint(1, 5)
    return random.randint(5, 260)


def seed():
    db.drop_all()
    db.create_all()
    print("· database recreated")

    used_slugs = set()

    def unique_slug_local(text):
        base = slugify(text)
        slug, n = base, 1
        while slug in used_slugs:
            n += 1
            slug = f"{base}-{n}"
        used_slugs.add(slug)
        return slug

    # ---------------------------------------------------------- categories
    root_cats, sub_cats = {}, {}
    for root_name, theme, _price, subs in ROOTS:
        root_slug = slugify(root_name)
        assert root_slug not in used_slugs, f"root slug clash: {root_slug}"
        used_slugs.add(root_slug)
        root = Category(name=root_name, slug=root_slug, parent_id=None)
        db.session.add(root)
        db.session.flush()
        root_cats[root_name] = root
        for sub_name, _types in subs:
            sub_slug = slugify(sub_name)
            assert sub_slug not in used_slugs, f"sub slug clash: {sub_slug}"
            used_slugs.add(sub_slug)
            sub = Category(name=sub_name, slug=sub_slug, parent_id=root.id)
            db.session.add(sub)
            db.session.flush()
            sub_cats[sub.slug] = sub
    n_cats = len(root_cats) + len(sub_cats)
    print(f"· {n_cats} categories ({len(root_cats)} roots, {len(sub_cats)} subs)")
    assert n_cats >= 250, "need 250+ categories"

    # ---------------------------------------------------------- hero products
    products = {}
    for (name, brand, price, deal, stock, sub_slug, imgs, desc, featured) in HEROES:
        price, deal = to_inr(price), (to_inr(deal) if deal else None)
        p = Product(
            name=name, slug=unique_slug_local(name), brand=brand, price=price,
            deal_price=deal, stock=stock, category_id=sub_cats[sub_slug].id,
            description=desc, is_deal=bool(deal), is_featured=featured,
            rating=gen_rating(), rating_count=gen_rating_count(),
            primary_image_url=f"/static/images/{imgs[0]}.svg",
        )
        db.session.add(p)
        db.session.flush()
        products[name] = p
        for idx, img in enumerate(imgs):
            db.session.add(ProductImage(
                product_id=p.id, url=f"/static/images/{img}.svg", alt=name,
                is_primary=(idx == 0), sort_order=idx))

    # ---------------------------------------------------------- synthetic catalog
    n_products = len(products)
    chunk = []
    for root_name, theme, (lo, hi), subs in ROOTS:
        brands = random.sample(BRANDS, 10)
        for sub_name, types in subs:
            sub = sub_cats[slugify(sub_name)]
            for i in range(PRODUCTS_PER_SUB):
                brand = random.choice(brands)
                series = random.choice(SERIES)
                model = random.choice(MODELS)
                ptype = random.choice(types)
                name = f"{brand} {series} {model} {ptype}"
                price = gen_price(lo, hi)
                is_deal = random.random() < 0.06
                deal_price = psych_inr(price * random.uniform(0.55, 0.90)) if is_deal else None
                feat = random.sample(FEATURES[theme], 2)
                description = (f"{ptype} by {brand}. Built with {feat[0]} and {feat[1]} — "
                               f"plus fast shipping, 30-day returns and a 2-year ShopLinq guarantee.")
                created = utcnow() - timedelta(days=random.randint(1, 540),
                                               hours=random.randint(0, 23))
                p = Product(
                    name=name, slug=unique_slug_local(name), brand=brand,
                    price=price, deal_price=deal_price, stock=gen_stock(),
                    category_id=sub.id, description=description,
                    is_deal=is_deal, is_featured=random.random() < 0.10,
                    rating=gen_rating(), rating_count=gen_rating_count(),
                    primary_image_url=f"/static/images/cat-{theme}-{(i % 3) + 1}.svg",
                    created_date=created,
                )
                chunk.append(p)
                n_products += 1
                if len(chunk) >= 500:
                    db.session.add_all(chunk)
                    db.session.flush()
                    chunk = []
    if chunk:
        db.session.add_all(chunk)
        db.session.flush()
    print(f"· {n_products} products")
    assert n_products >= 5000, "need 5000+ products"

    # ---------------------------------------------------------- people
    admin = Customer(name="Avery Admin", email="admin@shoplinq.com", is_admin=True)
    admin.set_password("adminpass123")
    demo = Customer(name="Demo Demo", email="demo@shoplinq.com")
    demo.set_password("demopass123")
    db.session.add_all([admin, demo])
    db.session.flush()

    addr = Address(
        customer_id=demo.id, label="Home", full_name="Demo Demo",
        line1="42 Marine Drive", city="Mumbai", state="Maharashtra",
        postal_code="400020", country="India", phone="+91 98200 12345",
        is_default=True)
    db.session.add(addr)
    db.session.add(PaymentMethod(
        customer_id=demo.id, card_brand="Visa", last4="4242",
        exp_month=12, exp_year=2030, is_default=True))
    db.session.flush()

    reviewers = {}
    for rname in ["Maya Chen", "Jonas Weber", "Priya Nair", "Liam O'Brien", "Sofia Rossi"]:
        u = Customer(name=rname, email=f"{rname.split()[0].lower()}@shoplinq.com")
        u.set_password("reviewerpass123")
        db.session.add(u)
        reviewers[rname] = u
    db.session.flush()

    # synthetic reviewers + shoppers
    first = ["Alex", "Sam", "Riley", "Jordan", "Casey", "Quinn", "Morgan", "Avery",
             "Robin", "Dana", "Ellis", "Harper", "Rowan", "Sasha", "Toni", "Vera",
             "Wren", "Yuri", "Zara", "Ivan", "Lena", "Marco", "Nadia", "Omar"]
    last = ["Nguyen", "Park", "Silva", "Kowalski", "Dubois", "Haddad", "Moreau",
            "Ricci", "Novak", "Weiss", "Okafor", "Lindqvist", "Fischer", "Rahman",
            "Costa", "Petit", "Vargas", "Ito", "Bauer", "Mendez"]
    synth_reviewers = []
    for i in range(25):
        u = Customer(name=f"{first[i % len(first)]} {last[i % len(last)]}",
                     email=f"shopper{i + 1}@shoplinq.com")
        u.set_password("password123")
        db.session.add(u)
        synth_reviewers.append(u)
    db.session.flush()

    # ---------------------------------------------------------- reviews
    n_reviews = 0
    for product_name, entries in REVIEWS.items():
        p = products[product_name]
        for (rname, rating, title, body) in entries:
            db.session.add(Review(
                product_id=p.id, customer_id=reviewers[rname].id,
                rating=rating, title=title, body=body))
            n_reviews += 1
    db.session.flush()

    # sample reviews on popular synthetic products
    popular = (Product.query.order_by(Product.rating_count.desc())
               .limit(260).all())
    reviewed_pairs = set()
    for p in popular:
        for _ in range(random.randint(2, 4)):
            rating = random.choices([5, 4, 3, 2], weights=[55, 30, 11, 4])[0]
            author = random.choice(synth_reviewers)
            if (p.id, author.id) in reviewed_pairs:
                continue
            reviewed_pairs.add((p.id, author.id))
            db.session.add(Review(
                product_id=p.id, customer_id=author.id, rating=rating,
                title=random.choice(REVIEW_TITLES[rating]),
                body=random.choice(REVIEW_BODIES[rating]),
                created_date=utcnow() - timedelta(days=random.randint(1, 300))))
            n_reviews += 1
    db.session.flush()
    print(f"· {n_reviews} reviews")

    for (product_name, q, a, author) in QA:
        db.session.add(ProductQA(
            product_id=products[product_name].id, question=q, answer=a,
            author=author))
    for code, pct, min_spend in PROMOS:
        db.session.add(PromoCode(code=code, discount_percent=pct, min_spend=min_spend))
    db.session.flush()
    print(f"· {len(QA)} Q&A entries, {len(PROMOS)} promo codes")

    # ---------------------------------------------------------- orders
    def make_order(customer, items, status, days_ago, address, method="upi",
                   promo=None, discount=0.0):
        order = Order(
            customer_id=customer.id,
            order_number=f"SL{utcnow().strftime('%Y%m%d')}-{random.randint(10000, 99999)}",
            status=status,
            subtotal=round(sum(p.effective_price * q for p, q in items), 2),
            tax=0, shipping_fee=0, total=0,
            delivery_method="express" if random.random() < 0.2 else "standard",
            promo_code=promo, discount=discount,
            ship_name=address["full_name"], ship_line1=address["line1"],
            ship_city=address["city"], ship_state=address["state"],
            ship_postal_code=address["postal_code"],
            ship_country=address["country"], ship_phone=address.get("phone"),
            placed_date=utcnow() - timedelta(days=days_ago,
                                             hours=random.randint(0, 12)),
        )
        subtotal = order.subtotal
        order.discount = round(discount, 2)
        taxable = max(subtotal - order.discount, 0)
        order.tax = 0  # GST is included in listed prices
        order.shipping_fee = 0 if taxable >= 999 else 79
        order.total = round(taxable + order.shipping_fee, 2)
        db.session.add(order)
        db.session.flush()
        for p, q in items:
            db.session.add(OrderItem(
                order_id=order.id, product_id=p.id, product_name=p.name,
                product_slug=p.slug, image_url=p.primary_image_url,
                unit_price=p.effective_price, quantity=q))
        shipping = Shipping(
            order_id=order.id,
            tracking_number="SLX" + f"{random.randint(100000, 999999)}",
            status="placed",
            estimated_delivery=order.placed_date + timedelta(days=5))
        upto = FLOW.index(status) + 1 if status in FLOW else 1
        for i, step in enumerate(FLOW[:upto]):
            shipping.record(step, when=order.placed_date + timedelta(days=i))
        db.session.add(shipping)
        paid = (method in ("upi", "card", "netbanking", "wallet")) or (status == "delivered")
        if method == "card":
            brand, last4 = "Visa", "4242"
        elif method == "upi":
            brand, last4 = "UPI", None
        elif method == "netbanking":
            brand, last4 = "HDFC Bank", None
        elif method == "wallet":
            brand, last4 = "Paytm Wallet", None
        else:
            brand, last4 = None, None
        db.session.add(Payment(
            order_id=order.id, method=method,
            status="paid" if paid else "pending",
            amount=order.total, card_brand=brand, last4=last4,
            paid_date=order.placed_date if paid else None))
        return order

    demo_addr = addr.as_dict()
    make_order(demo, [(products["Aurora X5 5G Smartphone"], 1),
                      (products["EchoWave Buds Air"], 1)],
               "delivered", 14, demo_addr)
    make_order(demo, [(products["VortexAir Fryer 5L"], 1),
                      (products["Lumina Vitamin C Serum"], 2),
                      (products["Deep Work Habits"], 1)],
               "out_for_delivery", 6, demo_addr, method="cod")
    make_order(demo, [(products["Stratus Book 14\" Ultrabook"], 1)],
               "shipped", 2, demo_addr)
    for name in ["Pulse Boom Mini Speaker", "Solstice Wrap Dress",
                 "BlockWorks Space Station Kit"]:
        db.session.add(WishlistItem(customer_id=demo.id, product_id=products[name].id))
    db.session.add(Cart(customer_id=demo.id))

    # a realistic order history across shoppers + the past 6 months
    sample_products = Product.query.filter(Product.stock > 0).order_by(
        Product.rating_count.desc()).limit(400).all()
    statuses_by_age = ["delivered", "delivered", "delivered", "out_for_delivery",
                      "shipped", "packed", "placed"]
    n_orders = 3
    for i in range(30):
        buyer = random.choice(synth_reviewers)
        buyer_addr = {
            "full_name": buyer.name, "line1": f"{random.randint(1, 99)} MG Road",
            "city": random.choice(["Mumbai", "Delhi", "Bengaluru", "Chennai",
                                   "Hyderabad", "Pune", "Kolkata", "Jaipur"]),
            "state": random.choice(["Maharashtra", "Karnataka", "Delhi",
                                    "Tamil Nadu", "Telangana", "West Bengal",
                                    "Rajasthan"]),
            "postal_code": f"{random.randint(110001, 700099)}",
            "country": "India", "phone": f"+91 9{random.randint(100000000, 999999999)}",
        }
        items = [(p, random.randint(1, 3))
                 for p in random.sample(sample_products, random.randint(1, 3))]
        days_ago = random.randint(3, 170)
        status = (statuses_by_age[0] if days_ago > 30
                  else random.choice(statuses_by_age))
        method = random.choice(["upi", "upi", "card", "netbanking", "wallet", "cod"])
        make_order(buyer, items, status, days_ago, buyer_addr, method=method)
        n_orders += 1
    db.session.flush()
    print(f"· {n_orders} orders across customers (up to 6 months of history)")

    db.session.commit()
    cache_clear()
    print("\nSeed complete! Accounts:")
    print("  admin: admin@shoplinq.com / adminpass123")
    print("  demo:  demo@shoplinq.com  / demopass123")


if __name__ == "__main__":
    with app.app_context():
        seed()
