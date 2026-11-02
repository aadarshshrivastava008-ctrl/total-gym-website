from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, send_from_directory
import sqlite3
import datetime
import os
import random
import time
import threading
import smtplib
import json
import urllib.request
import urllib.error
import urllib.parse
import re
from email.mime.text import MIMEText

try:
    import psycopg2
except ImportError:
    psycopg2 = None

app = Flask(__name__)
app.secret_key = "avengers_fitness_club_secret_key_2026"

# .env फ़ाइल से क्रेडेंशियल्स लोड करना
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as env_f:
        for line in env_f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "velora@123")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "aadarshshrivastava008@gmail.com")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

# आपका टेस्टेड WhatsApp नंबर (Testing & Orders के लिए)
STORE_WHATSAPP_NUMBER = os.environ.get("STORE_WHATSAPP_NUMBER", "917999423916")
GYM_UPI_ID = os.environ.get("GYM_UPI_ID", "avengersfitness@upi")
GYM_NAME = os.environ.get("GYM_NAME", "Avengers Fitness Club")

# Google Mail Webhook URL
GOOGLE_MAIL_WEBHOOK = os.environ.get(
    "MAIL_WEBHOOK_URL",
    "https://script.google.com/macros/s/AKfycbxTbmhpLEeTK1i0Jb9X7gMGDt6-tJ_QaNnjnQo9tPNWR5TxBKUYR3Et8RsTX4S-ztUwcg/exec"
)

SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

DB_FILE = "inquiries.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_db_connection():
    if DATABASE_URL and psycopg2:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect(DB_FILE)

def mask_email(email):
    if "@" in email:
        user, domain = email.split("@", 1)
        prefix = user[:2] if len(user) >= 2 else user[:1]
        return f"{prefix}****@{domain}"
    return email

def send_otp_background(to_email, otp_code):
    print("\n" + "=" * 48)
    print(f"🔑 [Avengers Fitness Club 2FA] Your OTP code is: {otp_code}")
    print(f"📧 Destination: {to_email}")
    print("=" * 48 + "\n")

    if GOOGLE_MAIL_WEBHOOK:
        try:
            payload = json.dumps({
                "to": to_email,
                "subject": f"Avengers Fitness Club Security OTP: {otp_code}",
                "body": f"Hello,\n\nYour Avengers Fitness Club Admin verification OTP is: {otp_code}\n\nValid for 5 minutes.\n\n- Avengers Fitness Club Security"
            }).encode("utf-8")
            
            req = urllib.request.Request(
                GOOGLE_MAIL_WEBHOOK,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                print(f"✅ OTP email successfully delivered to {to_email} via Webhook!")
                return
        except Exception as e:
            print(f"⚠️ Webhook Email Note: {e}")

    if SMTP_EMAIL and SMTP_PASSWORD:
        try:
            msg = MIMEText(f"Hello,\n\nYour Avengers Fitness Club Admin verification OTP is: {otp_code}\n\nValid for 5 minutes.")
            msg['Subject'] = f"Avengers Fitness Club Security OTP: {otp_code}"
            msg['From'] = SMTP_EMAIL
            msg['To'] = to_email

            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            print(f"✅ OTP delivered via SMTP to {to_email}")
        except Exception as e:
            print(f"⚠️ SMTP Note: {e}")

def trigger_otp(to_email, otp_code):
    thread = threading.Thread(target=send_otp_background, args=(to_email, otp_code))
    thread.daemon = True
    thread.start()

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if DATABASE_URL and psycopg2:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inquiries (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    phone TEXT,
                    message TEXT,
                    created_at TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    phone TEXT,
                    email TEXT,
                    plan_name TEXT,
                    amount TEXT,
                    utr_no TEXT,
                    status TEXT,
                    created_at TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS supplement_orders (
                    id SERIAL PRIMARY KEY,
                    order_number TEXT,
                    customer_name TEXT,
                    customer_phone TEXT,
                    product_name TEXT,
                    brand TEXT,
                    flavor TEXT,
                    weight_size TEXT,
                    quantity INTEGER,
                    total_amount INTEGER,
                    delivery_type TEXT,
                    address TEXT,
                    payment_method TEXT,
                    status TEXT,
                    created_at TEXT
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inquiries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    email TEXT,
                    phone TEXT,
                    message TEXT,
                    created_at TEXT
                )
            ''')
            cursor.execute("PRAGMA table_info(inquiries)")
            cols = [c[1] for c in cursor.fetchall()]
            if "phone" not in cols:
                cursor.execute("ALTER TABLE inquiries ADD COLUMN phone TEXT")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    phone TEXT,
                    email TEXT,
                    plan_name TEXT,
                    amount TEXT,
                    utr_no TEXT,
                    status TEXT,
                    created_at TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS supplement_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT,
                    customer_name TEXT,
                    customer_phone TEXT,
                    product_name TEXT,
                    brand TEXT,
                    flavor TEXT,
                    weight_size TEXT,
                    quantity INTEGER,
                    total_amount INTEGER,
                    delivery_type TEXT,
                    address TEXT,
                    payment_method TEXT,
                    status TEXT,
                    created_at TEXT
                )
            ''')
        conn.commit()
        conn.close()
        print("✅ Database successfully connected and initialized!")
    except Exception as e:
        print(f"⚠️ Database initialization note: {e}")

init_db()

# ==========================================
# 💊 AVENGERS SUPPLEMENT STORE PRODUCTS
# ==========================================
STORE_PRODUCTS = [
    {
        "id": "on-whey-gold",
        "name": "Optimum Nutrition (ON) Gold Standard 100% Whey",
        "brand": "Optimum Nutrition",
        "category": "whey",
        "category_name": "Whey Protein",
        "price": 5499,
        "mrp": 6999,
        "discount": "21% OFF",
        "rating": "4.9",
        "reviews": 340,
        "badge": "🏆 Best Seller",
        "tag": "100% Authentic with Glanbia Holo-Tag",
        "sizes": ["1 Kg (₹2,999)", "2 Kg (₹5,499)", "5 Lbs (₹6,199)"],
        "flavors": ["Double Rich Chocolate", "Vanilla Ice Cream", "Cafe Mocha", "Delicious Strawberry"],
        "image": "https://images.unsplash.com/photo-1579722821273-0f6c7d44362f?w=600&auto=format&fit=crop&q=80",
        "desc": "24g Pure Whey Protein, 5.5g BCAAs, 4g Glutamine per scoop. World #1 Whey protein."
    },
    {
        "id": "mb-biozyme-whey",
        "name": "MuscleBlaze Biozyme Performance Whey Protein",
        "brand": "MuscleBlaze",
        "category": "whey",
        "category_name": "Whey Protein",
        "price": 4199,
        "mrp": 5299,
        "discount": "20% OFF",
        "rating": "4.8",
        "reviews": 210,
        "badge": "⚡ High Absorption",
        "tag": "Enhanced Absorption Formula (EAF®)",
        "sizes": ["1 Kg (₹2,299)", "2 Kg (₹4,199)"],
        "flavors": ["Rich Chocolate", "Magical Mango", "Kesar Kulfi", "Chocolate Hazelnut"],
        "image": "https://images.unsplash.com/photo-1593095948071-474c5cc2989d?w=600&auto=format&fit=crop&q=80",
        "desc": "25g Protein per scoop with 50% higher protein absorption for Indian bodies."
    },
    {
        "id": "dymatize-iso100",
        "name": "Dymatize ISO100 Hydrolyzed 100% Whey Isolate",
        "brand": "Dymatize",
        "category": "whey",
        "category_name": "Whey Protein",
        "price": 8499,
        "mrp": 10499,
        "discount": "19% OFF",
        "rating": "5.0",
        "reviews": 180,
        "badge": "💎 Ultra-Pure Isolate",
        "tag": "Fast Digesting • Zero Fat & Sugar",
        "sizes": ["5 Lbs / 2.3 Kg (₹8,499)"],
        "flavors": ["Gourmet Chocolate", "Fudge Brownie", "Birthday Cake"],
        "image": "https://images.unsplash.com/photo-1579722821273-0f6c7d44362f?w=600&auto=format&fit=crop&q=80",
        "desc": "25g Hydrolyzed 100% Whey Protein Isolate. Top tier competitive bodybuilding choice."
    },
    {
        "id": "being-strong-whey",
        "name": "Being Strong 100% Whey Protein (Salman Khan Brand)",
        "brand": "Being Strong",
        "category": "whey",
        "category_name": "Whey Protein",
        "price": 4899,
        "mrp": 6299,
        "discount": "22% OFF",
        "rating": "4.9",
        "reviews": 420,
        "badge": "⭐ Gym Partner Brand",
        "tag": "Official Avengers Equipment Partner Brand",
        "sizes": ["1 Kg (₹2,699)", "2 Kg (₹4,899)"],
        "flavors": ["Belgian Chocolate", "Alphonso Mango", "Malai Kulfi"],
        "image": "https://images.unsplash.com/photo-1593095948071-474c5cc2989d?w=600&auto=format&fit=crop&q=80",
        "desc": "26g Premium Protein with Added Digestive Enzymes. Authentic Being Strong Seal."
    },
    {
        "id": "c4-preworkout",
        "name": "Cellucor C4 Original Explosive Pre-Workout",
        "brand": "Cellucor",
        "category": "preworkout",
        "category_name": "Pre-Workout & Energy",
        "price": 2199,
        "mrp": 2899,
        "discount": "24% OFF",
        "rating": "4.8",
        "reviews": 195,
        "badge": "🔥 Explosive Energy",
        "tag": "America #1 Pre-Workout • Explosive Pumps",
        "sizes": ["30 Servings (₹2,199)", "60 Servings (₹3,799)"],
        "flavors": ["Icy Blue Razz", "Fruit Punch", "Watermelon"],
        "image": "https://images.unsplash.com/photo-1546483875-ad9014c88eba?w=600&auto=format&fit=crop&q=80",
        "desc": "150mg Caffeine, 1.6g Beta-Alanine, 1g Creatine Nitrate for insane gym pumps."
    },
    {
        "id": "psychotic-preworkout",
        "name": "Insane Labz Psychotic High-Stim Pre-Workout",
        "brand": "Insane Labz",
        "category": "preworkout",
        "category_name": "Pre-Workout & Energy",
        "price": 2499,
        "mrp": 3299,
        "discount": "24% OFF",
        "rating": "4.9",
        "reviews": 160,
        "badge": "⚡ Hardcore Focus",
        "tag": "AMPiberry Extreme Energy Formula",
        "sizes": ["35 Servings (₹2,499)"],
        "flavors": ["Cotton Candy", "Watermelon", "Gummy Candy"],
        "image": "https://images.unsplash.com/photo-1546483875-ad9014c88eba?w=600&auto=format&fit=crop&q=80",
        "desc": "Advanced stimulant formula for intense laser focus, strength, and endurance."
    },
    {
        "id": "labrada-mass-gainer",
        "name": "Labrada Muscle Mass Gainer",
        "brand": "Labrada",
        "category": "gainer",
        "category_name": "Mass Gainers",
        "price": 3699,
        "mrp": 4899,
        "discount": "24% OFF",
        "rating": "4.7",
        "reviews": 280,
        "badge": "💪 Bulking Formula",
        "tag": "1260 Calories • 52g Protein Per Serving",
        "sizes": ["3 Kg (₹3,699)", "5 Kg (₹5,699)"],
        "flavors": ["Chocolate", "Vanilla", "Strawberry"],
        "image": "https://images.unsplash.com/photo-1579722821273-0f6c7d44362f?w=600&auto=format&fit=crop&q=80",
        "desc": "Perfect for hardgainers looking to build solid muscle mass and strength."
    },
    {
        "id": "mb-creatine-creamp",
        "name": "MuscleBlaze CreAMP Micronized Creatine Monohydrate",
        "brand": "MuscleBlaze",
        "category": "creatine",
        "category_name": "Creatine & BCAA",
        "price": 999,
        "mrp": 1499,
        "discount": "33% OFF",
        "rating": "4.9",
        "reviews": 510,
        "badge": "⚡ 100% Pure Creatine",
        "tag": "CreAMP™ Absorption Technology",
        "sizes": ["250g (₹999)", "400g (₹1,449)"],
        "flavors": ["Unflavored (Easy mix)"],
        "image": "https://images.unsplash.com/photo-1593095948071-474c5cc2989d?w=600&auto=format&fit=crop&q=80",
        "desc": "3g Pure Creatine Monohydrate per scoop. Increases ATP energy and muscle power."
    },
    {
        "id": "xtend-bcaa",
        "name": "Scivation XTEND Original 7g BCAA + Electrolytes",
        "brand": "Scivation",
        "category": "creatine",
        "category_name": "Creatine & BCAA",
        "price": 2199,
        "mrp": 2799,
        "discount": "21% OFF",
        "rating": "4.8",
        "reviews": 230,
        "badge": "🛡️ Muscle Recovery",
        "tag": "7g BCAAs in 2:1:1 Ratio • Zero Sugar",
        "sizes": ["30 Servings (₹2,199)"],
        "flavors": ["Blue Raspberry", "Watermelon Explosion", "Mango Madness"],
        "image": "https://images.unsplash.com/photo-1546483875-ad9014c88eba?w=600&auto=format&fit=crop&q=80",
        "desc": "Prevents muscle breakdown during heavy lifting and speeds up post-workout recovery."
    },
    {
        "id": "hydroxycut-fat-burner",
        "name": "MuscleTech Hydroxycut Hardcore Elite Fat Burner",
        "brand": "MuscleTech",
        "category": "health",
        "category_name": "Health & Fat Burners",
        "price": 1899,
        "mrp": 2499,
        "discount": "24% OFF",
        "rating": "4.7",
        "reviews": 145,
        "badge": "🔥 Thermogenic Shred",
        "tag": "Green Coffee Extract + Yohimbe Formula",
        "sizes": ["110 Rapid-Release Capsules (₹1,899)"],
        "flavors": ["Capsules"],
        "image": "https://images.unsplash.com/photo-1579722821273-0f6c7d44362f?w=600&auto=format&fit=crop&q=80",
        "desc": "Supports fast metabolism, thermogenesis and calorie burn during fat loss."
    },
    {
        "id": "mb-fish-oil-triple",
        "name": "MuscleBlaze Triple Strength Omega-3 Fish Oil (1000mg)",
        "brand": "MuscleBlaze",
        "category": "health",
        "category_name": "Health & Fat Burners",
        "price": 749,
        "mrp": 999,
        "discount": "25% OFF",
        "rating": "4.9",
        "reviews": 310,
        "badge": "❤️ Heart & Joint Care",
        "tag": "Enteric Coated • Zero Fishy Aftertaste",
        "sizes": ["60 Softgels (₹749)"],
        "flavors": ["Softgels"],
        "image": "https://images.unsplash.com/photo-1593095948071-474c5cc2989d?w=600&auto=format&fit=crop&q=80",
        "desc": "Joint and heart protection for heavy lifters with 560mg EPA + 400mg DHA."
    },
    {
        "id": "avengers-pro-shaker",
        "name": "Avengers Fitness Club Pro Hurricane Shaker (700ml)",
        "brand": "Avengers Gear",
        "category": "accessories",
        "category_name": "Gym Accessories",
        "price": 299,
        "mrp": 499,
        "discount": "40% OFF",
        "rating": "5.0",
        "reviews": 480,
        "badge": "🥤 Official Club Merch",
        "tag": "Leak-Proof • BPA Free • Stainless Blender Ball",
        "sizes": ["700 ml Capacity (₹299)"],
        "flavors": ["Black & Gold Avengers Edition"],
        "image": "https://images.unsplash.com/photo-1546483875-ad9014c88eba?w=600&auto=format&fit=crop&q=80",
        "desc": "Leak-proof high-grade shaker bottle designed for smooth, lump-free protein shakes."
    }
]

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Avengers Fitness Club Admin Login</title>
    <style>
        body { background: #0d0d0f; color: #fff; font-family: 'Segoe UI', sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .login-card { background: #16161a; padding: 35px 30px; border-radius: 12px; border: 1px solid #292932; width: 340px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h2 { color: #e5a93c; margin-bottom: 20px; font-size: 22px; }
        input { width: 100%; padding: 12px; margin-bottom: 15px; box-sizing: border-box; background: #202026; border: 1px solid #3a3a46; border-radius: 6px; color: #fff; outline: none; }
        input:focus { border-color: #e5a93c; }
        button { width: 100%; padding: 12px; background: #e5a93c; border: none; border-radius: 6px; font-weight: bold; color: #000; cursor: pointer; font-size: 15px; }
        button:hover { background: #f5b94c; }
        .error { color: #ff6b6b; font-size: 13px; margin-bottom: 12px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>Admin Security Access</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST" action="/admin/login">
            <input type="text" name="username" placeholder="Username" required autofocus autocomplete="off">
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Sign In & Send OTP</button>
        </form>
    </div>
</body>
</html>
"""

OTP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>2FA Security Check (Avengers Fitness Club)</title>
    <style>
        body { background: #0d0d0f; color: #fff; font-family: 'Segoe UI', sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .otp-card { background: #16161a; padding: 35px 30px; border-radius: 12px; border: 1px solid #292932; width: 360px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        .shield-icon { font-size: 40px; margin-bottom: 10px; color: #e5a93c; }
        h2 { color: #fff; margin: 0 0 10px; font-size: 20px; }
        p { color: #888; font-size: 13px; margin-bottom: 20px; line-height: 1.5; }
        .email-badge { color: #e5a93c; font-weight: bold; }
        .error { color: #ff6b6b; font-size: 13px; margin-bottom: 12px; }
        .success { color: #2ecc71; font-size: 13px; margin-bottom: 12px; }
        input[type="text"] { width: 100%; padding: 14px; box-sizing: border-box; background: #202024; border: 1px solid #444; border-radius: 6px; color: #e5a93c; font-size: 24px; text-align: center; letter-spacing: 8px; font-weight: bold; margin-bottom: 18px; outline: none; }
        input:focus { border-color: #e5a93c; }
        button { width: 100%; padding: 12px; background: #e5a93c; border: none; border-radius: 6px; font-weight: bold; color: #000; cursor: pointer; font-size: 15px; }
        button:hover { background: #f5b94c; }
        .resend-box { margin-top: 15px; font-size: 13px; color: #777; }
        .resend-box a { color: #e5a93c; text-decoration: none; font-weight: 500; }
        .resend-box a:hover { text-decoration: underline; }
        .cancel-link { display: block; margin-top: 15px; color: #666; text-decoration: none; font-size: 12px; }
        .cancel-link:hover { color: #aaa; }
    </style>
</head>
<body>
    <div class="otp-card">
        <div class="shield-icon">🛡️</div>
        <h2>Two-Factor Verification</h2>
        <p>A 6-digit verification code has been sent to:<br><span class="email-badge">{{ masked_email }}</span></p>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        {% if msg %}<div class="success">{{ msg }}</div>{% endif %}
        <form method="POST" action="/admin/verify-otp">
            <input type="text" name="otp" maxlength="6" placeholder="••••••" autofocus required autocomplete="off">
            <button type="submit">Verify & Enter Dashboard</button>
        </form>
        <div class="resend-box">
            Didn't receive code? <a href="/admin/resend-otp">Resend OTP</a>
        </div>
        <a href="/admin/logout" class="cancel-link">Cancel & Return to Login</a>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Avengers Fitness Club Admin Portal</title>
    <style>
        body { background-color: #0d0d0f; color: #e5e5e5; font-family: 'Segoe UI', sans-serif; padding: 25px 35px; margin: 0; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #202025; }
        .header h1 { color: #e5a93c; margin: 0; font-size: 22px; font-weight: 600; }
        .btn-logout { background: #2b1111; color: #ff8b8b; padding: 8px 18px; border-radius: 6px; border: 1px solid #4a1f1f; text-decoration: none; font-size: 13px; font-weight: bold; }
        .badge { background: #231c11; color: #e5a93c; border: 1px solid #4a3818; padding: 6px 12px; border-radius: 6px; font-size: 12px; margin-right: 15px; }

        .tabs-nav { display: flex; gap: 12px; margin-bottom: 20px; }
        .tab-btn { background: #181820; color: #aaa; border: 1px solid #292934; padding: 10px 22px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s; }
        .tab-btn.active { background: #e5a93c; color: #000; border-color: #e5a93c; }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .table-card { background: #131316; border-radius: 10px; overflow: hidden; border: 1px solid #25252b; box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom: 30px; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { background: #1a1a20; color: #e5a93c; padding: 14px 16px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; border-bottom: 1px solid #2a2a32; }
        td { padding: 14px 16px; border-bottom: 1px solid #1c1c22; font-size: 13px; vertical-align: middle; }
        tr:hover { background: #17171d; }

        .btn-action { background: #1b3820; color: #4ade80; border: 1px solid #285e32; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; }
        .btn-action:hover { background: #24522d; }
        .badge-delivered { background: #112818; color: #4ade80; border: 1px solid #234c2d; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .badge-pending { background: #2d2411; color: #e5a93c; border: 1px solid #4d3e18; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <a href="/" style="color: #aaa; text-decoration: none; font-size: 13px; display: inline-block; margin-bottom: 5px;">← Back to Gym Website</a>
                <h1>Avengers Fitness Club Admin Portal</h1>
            </div>
            <div>
                <span class="badge">🛡️ 2FA Verified Session</span>
                <a href="/admin/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="tabs-nav">
            <button class="tab-btn active" onclick="showTab('tab-supplements', this)">💊 Supplement Orders ({{ orders|length }})</button>
            <button class="tab-btn" onclick="showTab('tab-inquiries', this)">💬 Tour Inquiries ({{ rows|length }})</button>
            <button class="tab-btn" onclick="showTab('tab-payments', this)">💳 Membership Payments ({{ payments|length }})</button>
        </div>

        <!-- 1. SUPPLEMENT ORDERS TAB -->
        <div id="tab-supplements" class="tab-content active">
            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>ORDER NO</th>
                            <th>CUSTOMER</th>
                            <th>PHONE</th>
                            <th>PRODUCT & FLAVOR</th>
                            <th>QTY & TOTAL</th>
                            <th>DELIVERY & ADDRESS</th>
                            <th>PAYMENT</th>
                            <th>STATUS</th>
                            <th>ACTION</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for ord in orders %}
                        <tr>
                            <td style="color: #e5a93c; font-weight: bold;">#{{ ord[1] }}</td>
                            <td style="color: #fff; font-weight: 600;">{{ ord[2] }}</td>
                            <td><a href="https://wa.me/91{{ ord[3] }}" target="_blank" style="color: #25d366; text-decoration: none; font-weight: 600;">💬 {{ ord[3] }}</a></td>
                            <td>{{ ord[4] }}<br><small style="color: #888;">{{ ord[6] }} • {{ ord[7] }}</small></td>
                            <td style="color: #e5a93c; font-weight: bold;">₹{{ ord[9] }} <span style="font-weight: normal; color: #888;">(Qty: {{ ord[8] }})</span></td>
                            <td>{{ ord[10] }}<br><small style="color: #aaa;">{{ ord[11] }}</small></td>
                            <td style="color: #aaa; font-size: 12px;">{{ ord[12] }}</td>
                            <td>
                                {% if ord[13] == 'Delivered / Completed' %}
                                <span class="badge-delivered">✓ Delivered</span>
                                {% else %}
                                <span class="badge-pending">⏳ {{ ord[13] }}</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if ord[13] != 'Delivered / Completed' %}
                                <form method="POST" action="/admin/update-order-status/{{ ord[0] }}">
                                    <button type="submit" class="btn-action">Mark Delivered</button>
                                </form>
                                {% else %}
                                <span style="color: #555;">Completed</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="9" style="text-align: center; color: #666; padding: 40px;">No supplement orders recorded yet.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- 2. INQUIRIES TAB -->
        <div id="tab-inquiries" class="tab-content">
            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th><th>NAME</th><th>PHONE</th><th>EMAIL</th><th>MESSAGE</th><th>DATE</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in rows %}
                        <tr>
                            <td style="color: #888;">#{{ r[0] }}</td>
                            <td style="color: #fff; font-weight: 600;">{{ r[1] }}</td>
                            <td style="color: #e5a93c; font-weight: 600;">{{ r[2] or '—' }}</td>
                            <td><a href="mailto:{{ r[3] }}" style="color: #6495ed; text-decoration: none;">{{ r[3] }}</a></td>
                            <td style="color: #d0d0d0;">{{ r[4] }}</td>
                            <td style="color: #888; font-size: 12px;">{{ r[5] }}</td>
                        </tr>
                        {% else %}
                        <tr><td colspan="6" style="text-align: center; color: #666; padding: 40px;">No inquiries found.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- 3. PAYMENTS TAB -->
        <div id="tab-payments" class="tab-content">
            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th><th>NAME</th><th>PHONE</th><th>PLAN</th><th>AMOUNT</th><th>UTR NUMBER</th><th>STATUS</th><th>DATE</th><th>ACTION</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for p in payments %}
                        <tr>
                            <td style="color: #888;">#{{ p[0] }}</td>
                            <td style="color: #fff; font-weight: 600;">{{ p[1] }}</td>
                            <td style="color: #e5a93c; font-weight: 600;">{{ p[2] }}</td>
                            <td>{{ p[4] }}</td>
                            <td style="color: #e5a93c; font-weight: bold;">₹{{ p[5] }}</td>
                            <td style="font-family: monospace; font-weight: bold; color: #2ecc71;">{{ p[6] }}</td>
                            <td>{{ p[7] }}</td>
                            <td style="color: #888; font-size: 12px;">{{ p[8] }}</td>
                            <td>
                                {% if p[7] != 'Verified / Paid' %}
                                <form method="POST" action="/admin/verify-payment/{{ p[0] }}">
                                    <button type="submit" class="btn-action">Verify Payment</button>
                                </form>
                                {% else %}
                                <span style="color: #4ade80;">✓ Verified</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="9" style="text-align: center; color: #666; padding: 40px;">No payments recorded yet.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        function showTab(tabId, btn) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
        }
    </script>
</body>
</html>
"""

STORE_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Avengers Nutrition & Supplement Store | 100% Authentic Gym Supplements</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; }
        body { background-color: #0c0c0f; color: #f0f0f5; padding-bottom: 60px; }
        
        /* Header */
        header { background: #131317; border-bottom: 1px solid #23232c; position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 20px rgba(0,0,0,0.6); }
        .nav-container { max-width: 1280px; margin: 0 auto; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; }
        .brand-box a { text-decoration: none; color: #e5a93c; font-size: 20px; font-weight: 800; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px; }
        .back-gym { color: #aaa; text-decoration: none; font-size: 13px; display: flex; align-items: center; gap: 5px; transition: color 0.2s; }
        .back-gym:hover { color: #e5a93c; }
        
        .header-actions { display: flex; align-items: center; gap: 15px; }
        .btn-wa-help { background: #25d366; color: #fff; text-decoration: none; font-weight: 600; font-size: 13px; padding: 8px 16px; border-radius: 20px; display: flex; align-items: center; gap: 6px; }
        .btn-wa-help:hover { background: #20ba59; }

        /* Trust Banner */
        .trust-banner { max-width: 1280px; margin: 20px auto; padding: 0 20px; }
        .trust-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 15px; }
        .trust-card { background: #15151b; border: 1px solid #23232c; border-radius: 10px; padding: 14px 18px; display: flex; align-items: center; gap: 12px; }
        .trust-icon { font-size: 24px; }
        .trust-text h4 { font-size: 14px; color: #e5a93c; font-weight: 600; }
        .trust-text p { font-size: 12px; color: #999; }

        /* Search & Filter Bar */
        .controls-section { max-width: 1280px; margin: 25px auto 15px; padding: 0 20px; }
        .search-box { position: relative; margin-bottom: 20px; }
        .search-box input { width: 100%; padding: 14px 20px 14px 45px; background: #17171f; border: 1px solid #2a2a36; border-radius: 30px; color: #fff; font-size: 15px; outline: none; transition: border-color 0.2s; }
        .search-box input:focus { border-color: #e5a93c; }
        .search-icon { position: absolute; left: 18px; top: 50%; transform: translateY(-50%); color: #777; font-size: 16px; }

        .category-pills { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; scrollbar-width: none; }
        .category-pills::-webkit-scrollbar { display: none; }
        .pill-btn { background: #17171e; color: #bbb; border: 1px solid #262633; padding: 8px 18px; border-radius: 20px; font-size: 13px; font-weight: 500; cursor: pointer; white-space: nowrap; transition: all 0.2s; }
        .pill-btn:hover, .pill-btn.active { background: #e5a93c; color: #000; border-color: #e5a93c; font-weight: 600; }

        /* Products Grid */
        .products-section { max-width: 1280px; margin: 0 auto; padding: 10px 20px; }
        .products-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
        
        .product-card { background: #141419; border: 1px solid #23232c; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s; position: relative; }
        .product-card:hover { transform: translateY(-4px); border-color: #e5a93c; box-shadow: 0 10px 25px rgba(229,169,60,0.15); }
        
        .card-badge { position: absolute; top: 12px; left: 12px; background: #e5a93c; color: #000; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 12px; z-index: 2; }
        .product-img-box { width: 100%; height: 210px; background: #1c1c24; overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; }
        .product-img-box img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }
        .product-card:hover .product-img-box img { transform: scale(1.05); }

        .card-content { padding: 18px; display: flex; flex-direction: column; flex-grow: 1; }
        .brand-tag { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-bottom: 4px; }
        .product-title { font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 8px; line-height: 1.4; height: 42px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
        .rating-box { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #e5a93c; margin-bottom: 12px; }
        .rating-box span.count { color: #777; font-size: 11px; }

        .price-row { display: flex; align-items: baseline; gap: 8px; margin-top: auto; margin-bottom: 15px; }
        .current-price { font-size: 20px; font-weight: 700; color: #e5a93c; }
        .mrp-price { font-size: 13px; color: #777; text-decoration: line-through; }
        .discount-tag { font-size: 12px; color: #2ecc71; font-weight: 600; }

        .btn-order { background: linear-gradient(135deg, #e5a93c, #f5b94c); color: #000; border: none; padding: 12px; border-radius: 8px; font-weight: 700; font-size: 14px; cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 6px; transition: opacity 0.2s; }
        .btn-order:hover { opacity: 0.9; }

        /* Modal */
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); backdrop-filter: blur(5px); z-index: 1000; display: none; align-items: center; justify-content: center; padding: 20px; }
        .modal-card { background: #16161d; border: 1px solid #2d2d3b; border-radius: 14px; width: 100%; max-width: 540px; max-height: 90vh; overflow-y: auto; padding: 25px; position: relative; color: #fff; box-shadow: 0 15px 40px rgba(0,0,0,0.7); }
        .modal-close { position: absolute; top: 18px; right: 18px; font-size: 24px; color: #888; cursor: pointer; border: none; background: none; }
        .modal-close:hover { color: #fff; }

        .modal-prod-summary { display: flex; gap: 15px; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #262633; }
        .modal-prod-img { width: 70px; height: 70px; border-radius: 8px; object-fit: cover; background: #222; }
        
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
        .form-group select, .form-group input { width: 100%; padding: 11px 14px; background: #1f1f2a; border: 1px solid #333344; border-radius: 8px; color: #fff; font-size: 14px; outline: none; }
        .form-group select:focus, .form-group input:focus { border-color: #e5a93c; }

        .radio-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 5px; }
        .radio-card { border: 1px solid #333344; border-radius: 8px; padding: 12px; cursor: pointer; background: #1b1b24; transition: all 0.2s; }
        .radio-card.selected { border-color: #e5a93c; background: #262215; }
        .radio-card h5 { font-size: 13px; color: #e5a93c; margin-bottom: 2px; }
        .radio-card p { font-size: 11px; color: #888; line-height: 1.3; }

        .qty-box { display: flex; align-items: center; gap: 12px; margin-top: 5px; }
        .btn-qty { width: 34px; height: 34px; background: #2a2a3a; border: none; border-radius: 6px; color: #fff; font-size: 18px; cursor: pointer; }
        .qty-val { font-size: 16px; font-weight: 600; width: 30px; text-align: center; }

        .total-box { background: #111115; border: 1px dashed #e5a93c; border-radius: 8px; padding: 14px 18px; margin: 20px 0; display: flex; justify-content: space-between; align-items: center; }
        .total-box span.title { font-size: 14px; color: #aaa; }
        .total-box span.amount { font-size: 22px; font-weight: 800; color: #e5a93c; }

        .btn-confirm-order { background: linear-gradient(135deg, #25d366, #128c7e); color: #fff; width: 100%; border: none; padding: 14px; border-radius: 8px; font-weight: 700; font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .btn-confirm-order:hover { opacity: 0.95; }

        /* Success Card */
        .success-box { text-align: center; padding: 20px 10px; display: none; }
        .success-icon { font-size: 55px; margin-bottom: 12px; }
        .order-id-badge { background: #22222c; color: #e5a93c; padding: 6px 14px; border-radius: 20px; display: inline-block; font-size: 14px; font-weight: 700; margin: 10px 0 15px; }
        .btn-wa-launch { background: #25d366; color: #fff; text-decoration: none; padding: 14px 20px; border-radius: 8px; font-weight: 700; display: inline-flex; align-items: center; gap: 8px; margin-top: 15px; width: 100%; justify-content: center; }
    </style>
</head>
<body>

    <header>
        <div class="nav-container">
            <div class="brand-box">
                <a href="/store">💊 AVENGERS NUTRITION</a>
                <a href="/" class="back-gym">← Back to Avengers Fitness Club Website</a>
            </div>
            <div class="header-actions">
                <a href="https://wa.me/917999423916?text=Hi%20Avengers%20Fitness!%20I%20want%20to%20inquire%20about%20supplements." target="_blank" class="btn-wa-help">
                    💬 WhatsApp Support
                </a>
            </div>
        </div>
    </header>

    <div class="trust-banner">
        <div class="trust-grid">
            <div class="trust-card">
                <div class="trust-icon">🛡️</div>
                <div class="trust-text">
                    <h4>100% Authentic</h4>
                    <p>Official Importer Hologram & GST Bill</p>
                </div>
            </div>
            <div class="trust-card">
                <div class="trust-icon">🏢</div>
                <div class="trust-text">
                    <h4>Free Gym Desk Pickup</h4>
                    <p>Collect at Upvan, Pokharan Rd 1</p>
                </div>
            </div>
            <div class="trust-card">
                <div class="trust-icon">🚚</div>
                <div class="trust-text">
                    <h4>Home Delivery</h4>
                    <p>Fast doorstep delivery in Thane West</p>
                </div>
            </div>
            <div class="trust-card">
                <div class="trust-icon">⚡</div>
                <div class="trust-text">
                    <h4>Member Prices</h4>
                    <p>Up to 40% OFF for Gym Members</p>
                </div>
            </div>
        </div>
    </div>

    <section class="controls-section">
        <div class="search-box">
            <span class="search-icon">🔍</span>
            <input type="text" id="searchInput" placeholder="Search protein, creatine, pre-workout, brands..." onkeyup="filterItems()">
        </div>
        <div class="category-pills">
            <button class="pill-btn active" onclick="filterCategory('all', this)">🌟 All Supplements</button>
            <button class="pill-btn" onclick="filterCategory('whey', this)">🥛 Whey Protein</button>
            <button class="pill-btn" onclick="filterCategory('preworkout', this)">🔥 Pre-Workout</button>
            <button class="pill-btn" onclick="filterCategory('gainer', this)">💪 Mass Gainers</button>
            <button class="pill-btn" onclick="filterCategory('creatine', this)">⚡ Creatine & BCAA</button>
            <button class="pill-btn" onclick="filterCategory('health', this)">❤️ Health & Fat Burners</button>
            <button class="pill-btn" onclick="filterCategory('accessories', this)">🥤 Shakers & Gear</button>
        </div>
    </section>

    <section class="products-section">
        <div class="products-grid" id="productsGrid">
            {% for p in products %}
            <div class="product-card" data-category="{{ p.category }}" data-name="{{ p.name.lower() }}" data-brand="{{ p.brand.lower() }}">
                {% if p.badge %}
                <span class="card-badge">{{ p.badge }}</span>
                {% endif %}
                <div class="product-img-box">
                    <img src="{{ p.image }}" alt="{{ p.name }}" loading="lazy" onerror="this.src='https://images.unsplash.com/photo-1579722821273-0f6c7d44362f?w=600'">
                </div>
                <div class="card-content">
                    <span class="brand-tag">{{ p.brand }}</span>
                    <h3 class="product-title">{{ p.name }}</h3>
                    <div class="rating-box">
                        ⭐ {{ p.rating }} <span class="count">({{ p.reviews }} reviews)</span>
                    </div>
                    <div class="price-row">
                        <span class="current-price">₹{{ p.price }}</span>
                        <span class="mrp-price">₹{{ p.mrp }}</span>
                        <span class="discount-tag">{{ p.discount }}</span>
                    </div>
                    <button class="btn-order" onclick="openOrderModal({{ loop.index0 }})">
                        🛒 Quick Order / खरीदें
                    </button>
                </div>
            </div>
            {% endfor %}
        </div>
    </section>

    <!-- ORDER BOOKING MODAL -->
    <div class="modal-overlay" id="orderModal">
        <div class="modal-card">
            <button class="modal-close" onclick="closeOrderModal()">×</button>
            
            <div id="modalFormContainer">
                <div class="modal-prod-summary">
                    <img id="mImg" class="modal-prod-img" src="" alt="Product">
                    <div>
                        <span id="mBrand" style="font-size: 11px; color: #888; text-transform: uppercase;"></span>
                        <h4 id="mTitle" style="font-size: 15px; color: #e5a93c;"></h4>
                        <span id="mBasePrice" style="font-size: 16px; font-weight: 700; color: #fff;"></span>
                    </div>
                </div>

                <div class="form-group">
                    <label>Select Size / Weight (वज़न चुनें):</label>
                    <select id="mSizeSelect" onchange="updatePrice()"></select>
                </div>

                <div class="form-group">
                    <label>Select Flavor (फ्लेवर चुनें):</label>
                    <select id="mFlavorSelect"></select>
                </div>

                <div class="form-group">
                    <label>Quantity (मात्रा):</label>
                    <div class="qty-box">
                        <button class="btn-qty" onclick="changeQty(-1)">-</button>
                        <span class="qty-val" id="mQty">1</span>
                        <button class="btn-qty" onclick="changeQty(1)">+</button>
                    </div>
                </div>

                <div class="form-group">
                    <label>Delivery Method (डिलीवरी का प्रकार):</label>
                    <div class="radio-cards">
                        <div class="radio-card selected" id="delGym" onclick="setDelivery('Gym Desk Pickup')">
                            <h5>🏢 Gym Desk Pickup</h5>
                            <p>Free • Collect at Front-Desk</p>
                        </div>
                        <div class="radio-card" id="delHome" onclick="setDelivery('Home Delivery')">
                            <h5>🚚 Home Delivery</h5>
                            <p>Doorstep in Thane West</p>
                        </div>
                    </div>
                </div>

                <div class="form-group">
                    <label>Your Full Name (आपका नाम):</label>
                    <input type="text" id="mCustName" placeholder="e.g. Rahul Sharma" required>
                </div>

                <div class="form-group">
                    <label>WhatsApp Number (मोबाइल नंबर):</label>
                    <input type="tel" id="mCustPhone" placeholder="10-digit mobile number" maxlength="10" required>
                </div>

                <div class="form-group" id="addressGroup" style="display: none;">
                    <label>Delivery Address (पूरा पता):</label>
                    <input type="text" id="mAddress" placeholder="Flat No., Society, Pokharan Road...">
                </div>

                <div class="form-group">
                    <label>Payment Method (भुगतान का तरीका):</label>
                    <select id="mPayMethod">
                        <option value="Pay at Gym Desk (Cash / UPI on pickup)">💵 Pay at Gym Desk on Pickup (Cash / UPI)</option>
                        <option value="Online UPI Transfer (QR Code)">📱 Pay Online via UPI (Avengers QR Scanner)</option>
                        <option value="Cash on Delivery (COD)">📦 Cash on Delivery (COD)</option>
                    </select>
                </div>

                <div class="total-box">
                    <span class="title">Total Payable Amount:</span>
                    <span class="amount" id="mFinalAmount">₹0</span>
                </div>

                <button class="btn-confirm-order" onclick="submitOrder()">
                    📲 Confirm & Order via WhatsApp
                </button>
            </div>

            <!-- SUCCESS SCREEN -->
            <div id="modalSuccessContainer" class="success-box">
                <div class="success-icon">🎉</div>
                <h3 style="color: #2ecc71; margin-bottom: 5px;">Order Placed Successfully!</h3>
                <p style="color: #aaa; font-size: 13px;">आपका सप्लीमेंट ऑर्डर दर्ज कर लिया गया है।</p>
                <div class="order-id-badge" id="sOrderNo">#AV-SUP-XXXX</div>
                <p style="font-size: 13px; color: #ccc; margin-bottom: 15px;">
                    जिम ओनर को ऑर्डर कन्फर्मेशन भेजने के लिए नीचे बटन दबाएँ:
                </p>
                <a id="sWaBtn" href="#" target="_blank" class="btn-wa-launch">
                    💬 Open WhatsApp & Send Order
                </a>
                <button onclick="closeOrderModal()" style="margin-top: 20px; background: none; border: 1px solid #444; color: #aaa; padding: 8px 18px; border-radius: 6px; cursor: pointer;">
                    ← Continue Shopping
                </button>
            </div>
        </div>
    </div>

    <script>
        const productsData = {{ products | tojson }};
        let currentProd = null;
        let currentQty = 1;
        let currentDelivery = "Gym Desk Pickup";

        function filterCategory(cat, btn) {
            document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const cards = document.querySelectorAll('.product-card');
            cards.forEach(card => {
                if (cat === 'all' || card.dataset.category === cat) {
                    card.style.display = 'flex';
                } else {
                    card.style.display = 'none';
                }
            });
        }

        function filterItems() {
            const query = document.getElementById('searchInput').value.toLowerCase().trim();
            const cards = document.querySelectorAll('.product-card');
            cards.forEach(card => {
                const name = card.dataset.name;
                const brand = card.dataset.brand;
                if (name.includes(query) || brand.includes(query)) {
                    card.style.display = 'flex';
                } else {
                    card.style.display = 'none';
                }
            });
        }

        function openOrderModal(index) {
            currentProd = productsData[index];
            currentQty = 1;
            currentDelivery = "Gym Desk Pickup";

            document.getElementById('mImg').src = currentProd.image;
            document.getElementById('mBrand').innerText = currentProd.brand;
            document.getElementById('mTitle').innerText = currentProd.name;
            document.getElementById('mBasePrice').innerText = '₹' + currentProd.price;
            document.getElementById('mQty').innerText = currentQty;

            const sizeSelect = document.getElementById('mSizeSelect');
            sizeSelect.innerHTML = '';
            currentProd.sizes.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.innerText = s;
                sizeSelect.appendChild(opt);
            });

            const flavorSelect = document.getElementById('mFlavorSelect');
            flavorSelect.innerHTML = '';
            currentProd.flavors.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.innerText = f;
                flavorSelect.appendChild(opt);
            });

            setDelivery('Gym Desk Pickup');
            updatePrice();

            document.getElementById('modalFormContainer').style.display = 'block';
            document.getElementById('modalSuccessContainer').style.display = 'none';
            document.getElementById('orderModal').style.display = 'flex';
        }

        function closeOrderModal() {
            document.getElementById('orderModal').style.display = 'none';
        }

        function changeQty(delta) {
            currentQty = Math.max(1, currentQty + delta);
            document.getElementById('mQty').innerText = currentQty;
            updatePrice();
        }

        function updatePrice() {
            if (!currentProd) return;
            const sizeVal = document.getElementById('mSizeSelect').value;
            let price = currentProd.price;
            const match = sizeVal.match(/₹([0-9,]+)/);
            if (match) {
                price = parseInt(match[1].replace(',', ''));
            }
            const total = price * currentQty;
            document.getElementById('mFinalAmount').innerText = '₹' + total.toLocaleString('en-IN');
        }

        function setDelivery(type) {
            currentDelivery = type;
            const delGym = document.getElementById('delGym');
            const delHome = document.getElementById('delHome');
            const addrGroup = document.getElementById('addressGroup');

            if (type === 'Gym Desk Pickup') {
                delGym.classList.add('selected');
                delHome.classList.remove('selected');
                addrGroup.style.display = 'none';
            } else {
                delHome.classList.add('selected');
                delGym.classList.remove('selected');
                addrGroup.style.display = 'block';
            }
        }

        async function submitOrder() {
            const name = document.getElementById('mCustName').value.trim();
            const phone = document.getElementById('mCustPhone').value.trim();
            const address = document.getElementById('mAddress').value.trim();
            const flavor = document.getElementById('mFlavorSelect').value;
            const size = document.getElementById('mSizeSelect').value;
            const payMethod = document.getElementById('mPayMethod').value;

            if (!name) {
                alert('कृपया अपना नाम दर्ज करें।');
                return;
            }
            if (!phone || phone.length < 10) {
                alert('कृपया वैध 10-अंकों का WhatsApp मोबाइल नंबर दर्ज करें।');
                return;
            }
            if (currentDelivery === 'Home Delivery' && !address) {
                alert('कृपया होम डिलीवरी के लिए अपना पता दर्ज करें।');
                return;
            }

            const totalText = document.getElementById('mFinalAmount').innerText.replace('₹', '').replace(',', '');
            const totalAmount = parseInt(totalText) || currentProd.price;

            const payload = {
                product_name: currentProd.name,
                brand: currentProd.brand,
                flavor: flavor,
                weight_size: size,
                quantity: currentQty,
                total_amount: totalAmount,
                customer_name: name,
                customer_phone: phone,
                delivery_type: currentDelivery,
                address: address,
                payment_method: payMethod
            };

            try {
                const res = await fetch('/api/order-supplement', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await res.json();
                
                if (result.success) {
                    document.getElementById('modalFormContainer').style.display = 'none';
                    document.getElementById('modalSuccessContainer').style.display = 'block';
                    document.getElementById('sOrderNo').innerText = '#' + result.order_number;
                    document.getElementById('sWaBtn').href = result.whatsapp_url;
                    
                    // ओपन WhatsApp
                    window.open(result.whatsapp_url, '_blank');
                } else {
                    alert('Error: ' + result.message);
                }
            } catch (err) {
                alert('Connection error. Please try again.');
            }
        }
    </script>
</body>
</html>
"""

# ==========================================
# 🚀 FLASK ROUTES
# ==========================================

@app.route("/")
def home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "Avengers Fitness Club Website Home"

@app.route("/<path:filename>")
def serve_file(filename):
    return send_from_directory(".", filename)

# 1. सप्लीमेंट स्टोर पेज
@app.route("/store")
def supplement_store():
    return render_template_string(STORE_HTML, products=STORE_PRODUCTS)

# 2. सप्लीमेंट ऑर्डर प्लेस करने की API
@app.route("/api/order-supplement", methods=["POST"])
def order_supplement():
    data = request.get_json(silent=True) or request.form or {}
    
    product_name = data.get("product_name", "").strip()
    brand = data.get("brand", "").strip()
    flavor = data.get("flavor", "").strip()
    weight_size = data.get("weight_size", "").strip()
    quantity = int(data.get("quantity", 1))
    total_amount = int(data.get("total_amount", 0))
    customer_name = data.get("customer_name", "").strip()
    customer_phone = data.get("customer_phone", "").strip()
    delivery_type = data.get("delivery_type", "Gym Desk Pickup").strip()
    address = data.get("address", "").strip()
    payment_method = data.get("payment_method", "Pay at Gym Desk").strip()

    if not customer_name or not customer_phone or not product_name:
        return jsonify({"success": False, "message": "Please enter your name and phone number."}), 400

    order_no = f"AV-SUP-{random.randint(1000, 9999)}"
    now_ist = datetime.datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
        cursor.execute(f"""
            INSERT INTO supplement_orders (
                order_number, customer_name, customer_phone, product_name, brand,
                flavor, weight_size, quantity, total_amount, delivery_type,
                address, payment_method, status, created_at
            ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                      {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                      {placeholder}, {placeholder}, {placeholder}, {placeholder})
        """, (order_no, customer_name, customer_phone, product_name, brand,
              flavor, weight_size, quantity, total_amount, delivery_type,
              address, payment_method, "New Order", now_ist))
        conn.commit()
        conn.close()

        # WhatsApp Message Preparation (आपका टेस्टेड नंबर)
        target_number = STORE_WHATSAPP_NUMBER
        
        wa_text = f"""*🏋️ Avengers Fitness Club - New Supplement Order*
----------------------------------------
*Order ID:* #{order_no}
*Customer Name:* {customer_name}
*Customer Phone:* {customer_phone}
*Product:* {product_name} ({brand})
*Size/Weight:* {weight_size}
*Flavor:* {flavor}
*Quantity:* {quantity}
*Total Amount:* ₹{total_amount}
*Delivery Mode:* {delivery_type}
*Address:* {address if address else 'N/A (Gym Desk Pickup)'}
*Payment Method:* {payment_method}
----------------------------------------
_Please confirm my order availability._"""

        encoded_wa = urllib.parse.quote(wa_text)
        whatsapp_url = f"https://wa.me/{target_number}?text={encoded_wa}"

        return jsonify({
            "success": True,
            "order_number": order_no,
            "whatsapp_url": whatsapp_url,
            "message": "Order successfully booked!"
        }), 201

    except Exception as e:
        print(f"⚠️ Supplement Order DB Error: {e}")
        return jsonify({"success": False, "message": "Database error occurred"}), 500

# 3. प्रिया AI चैटबॉट API
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()

    if not user_msg:
        return jsonify({"reply": "नमस्ते! मैं प्रिया बोल रही हूँ। बताइए, मैं आपकी क्या मदद कर सकती हूँ?"}), 200

    lower = user_msg.lower()

    # 1. अगर क्लाइंट ने मना किया ("नहीं / No")
    no_phrases = ["नहीं", "nahi", "nahin", "nahi chahiye", "नहीं चाहिए", "नहीं बनवाना", "रहने दो", "बाद में", "not now"]
    has_no = any(p in lower for p in no_phrases) or bool(re.search(r'\\bno\\b', lower))
    if has_no:
        reply = "कोई बात नहीं! एवेंजर्स फिटनेस क्लब में कॉल करने और बात करने के लिए आपका बहुत-बहुत धन्यवाद। जब भी आपको समय मिले, आप एक बार हमारे जिम में जरूर विजिट कीजिएगा।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 2. फ्री गेस्ट पास बुकिंग / विजिट डेट
    pass_booking_triggers = [
        "कल", "kal", "tomorrow", "parso", "परसों", "narso", "नरसों", "after tomorrow", "day after tomorrow",
        "बुक कर", "book kar", "पास बना", "pass bana", "pass book", "पास बुक", "gate pass", "गेस्ट पास", "गेट पास",
        "फ्री पास", "free pass"
    ]
    has_booking = any(b in lower for b in pass_booking_triggers)
    has_pure_yes = bool(re.search(r'\\b(yes|haan|ha)\\b', lower)) or bool(re.search(r'(?:^|\\s,!?)(हाँ|हा)(?:$|\\s,!?|")', lower))

    if has_booking or has_pure_yes:
        if "after tomorrow" in lower or "परसों" in lower or "parso" in lower:
            day = "परसों (Day After Tomorrow)"
        elif "नरसों" in lower or "narso" in lower:
            day = "नरसों (In 3 Days)"
        elif "आज" in lower or "aaj" in lower or "today" in lower:
            day = "आज (Today)"
        else:
            day = "कल (Tomorrow)"

        if "सुबह" in lower or "morning" in lower:
            visit_day = f"{day} सुबह"
        elif "शाम" in lower or "evening" in lower:
            visit_day = f"{day} शाम"
        elif "दोपहर" in lower or "afternoon" in lower:
            visit_day = f"{day} दोपहर"
        else:
            visit_day = day

        reply = f"शानदार! {visit_day} के लिए आपका पास तैयार करने के लिए, कृपया नीचे दिए गए बॉक्स में अपना नाम और मोबाइल नंबर लिखकर सबमिट कर दीजिए।"
        return jsonify({
            "reply": reply,
            "show_pass_form": True,
            "visit_day": visit_day
        })

    # 3. समय और टाइमिंग
    timing_words = ["timing", "time", "open", "समय", "घंटे", "टाइम", "खुलता", "टाइमिंग", "schedule", "बजे"]
    if any(k in lower for k in timing_words):
        reply = "एवेंजर्स फिटनेस क्लब सोमवार से शनिवार सुबह 5:30 से रात 10:45 तक और रविवार को सुबह 7 से दोपहर 2 बजे तक खुला रहता है। आप अपने वर्कआउट के लिए कभी भी आ सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 4. पसंदीदा समय का जवाब
    morning_words = ["morning", "सुबह", "मॉर्निंग", "subah", "saverey", "savere"]
    afternoon_words = ["afternoon", "दोपहर", "dopahar"]
    evening_words = ["evening", "शाम", "रात", "इवनिंग", "shaam", "sham", "night"]

    if any(k in lower for k in morning_words):
        reply = "बहुत बढ़िया! सुबह का समय वर्कआउट के लिए सबसे बेस्ट होता है, उस समय पूरा जिम फ्रेश एनर्जी और शानदार पॉजिटिव वाइब्स से भरा होता है। क्या आप कल सुबह का 1-डे फ्री गेस्ट पास लेना चाहेंगे?"
        return jsonify({"reply": reply, "show_pass_form": False})
    elif any(k in lower for k in afternoon_words):
        reply = "शानदार चॉइस! दोपहर के समय जिम में काफी शांत और रिलैक्स माहौल रहता है, जिससे आप बिना किसी भीड़ के सभी Being Strong मशीनों पर आसानी से वर्कआउट कर सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})
    elif any(k in lower for k in evening_words):
        reply = "अरे वाह! शाम का समय दिमाग की थकान मिटाने और एनर्जेटिक वर्कआउट के लिए एकदम परफेक्ट है। उस समय हमारे जिम में बहुत ही मोटिवेटिंग वाइब होती है।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 5. पता और लोकेशन
    if any(k in lower for k in ["location", "address", "कहाँ", "पता", "kaha", "landmark", "किधर"]):
        reply = "एवेंजर्स फिटनेस क्लब का पता है: शॉप नंबर 2, भूकेंद्र बस स्टॉप, पोखरण रोड नंबर 1, उपवन लेक और येउर गेट के पास, ठाणे वेस्ट। आप यहाँ बहुत आसानी से पहुँच सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 6. फीस और पैकेज
    if any(k in lower for k in ["price", "cost", "fee", "fees", "membership", "plan", "offer", "फीस", "पैसा", "कीमत", "चार्ज", "रेट"]):
        reply = "हमारा सबसे लोकप्रिय एनुअल स्पेशल प्लान केवल 11,999 रुपये प्रति वर्ष का है, जिसमें बीइंग स्ट्रांग मशीनें और स्टीम बाथ शामिल हैं। मंथली प्लान 2,499 रुपये का है। क्या मैं आपके लिए एक दिन का फ्री गेस्ट पास बुक कर दूँ?"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 7. मशीनें और सुविधाएं
    if any(k in lower for k in ["equipment", "machine", "facility", "facilities", "steam", "मशीन", "मशीनें", "मशीनों", "सुविधा", "ट्रेनर", "स्टीम"]):
        reply = "हमारे पास 5,500 स्क्वायर फीट का विशाल स्पेस है, जिसमें सलमान खान की बीइंग स्ट्रांग ब्रांडेड मशीनें, क्रॉसफिट ज़ोन और स्टीम बाथ की पूरी सुविधा उपलब्ध है। आप एक बार आकर खुद देख सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 8. पहली बार जिम आने वाले (Beginner)
    if any(k in lower for k in ["पहली बार", "pehli baar", "pahli baar", "first time", "beginner", "कर पाऊंगा", "कर पाउँगा", "कर सकती हूँ", "नया हूँ", "नया हु", "start"]):
        reply = "बिल्कुल! आपको घबराने की ज़रूरत नहीं है। हमारे सर्टिफाइड ट्रेनर्स शुरुआत में आपको मशीनों का सही इस्तेमाल और बेसिक वर्कआउट खुद सिखाएंगे।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 9. बैली फैट और वजन घटाना (Belly Fat / Weight Loss)
    if any(k in lower for k in ["बैली फैट", "belly fat", "चर्बी", "charbi", "पेट", "fat loss", "weight loss", "वजन कम", "मोटापा", "motapa"]):
        reply = "सही डाइट और कार्डियो के साथ 2 से 3 महीने में शानदार बदलाव दिखने लगता है। आप कल आकर हमारे ट्रेनर से एक फ्री गाइडेंस ले सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 10. वर्कआउट से पहले और बाद का खाना (Pre & Post Workout Diet)
    if any(k in lower for k in ["पहले और बाद", "pehle aur baad", "pre workout", "post workout", "वर्कआउट से पहले", "वर्कआउट के बाद", "क्या खाना", "क्या खाएं", "kya khana", "kya khaye"]):
        reply = "वर्कआउट से पहले एक केला या हल्के कार्ब्स लें, और वर्कआउट के बाद प्रोटीन जैसे अंडे, पनीर या व्हे प्रोटीन रिकवरी के लिए सबसे बेस्ट हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 11. डाइट प्लान और पोषण (Diet Plan & Nutrition)
    if any(k in lower for k in ["डाइट प्लान", "diet plan", "डाइट चार्ट", "diet chart", "डाइट", "diet", "न्यूट्रिशन", "nutrition"]):
        reply = "जी हाँ, हमारे ट्रेनर्स आपके वजन और फिटनेस गोल के हिसाब से कस्टमाइज्ड डाइट चार्ट भी बना कर देते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 12. महिलाओं की सुरक्षा और माहौल (Women Safety)
    if any(k in lower for k in ["लड़कियों", "महिलाओं", "महिला", "ladies", "women", "female", "girls", "सेफ", "safe", "safety", "सुरक्षा", "सुरक्षित"]):
        reply = "जी बिल्कुल! हमारे यहाँ महिलाओं के लिए पूरी तरह सुरक्षित और आरामदायक माहौल, फीमेल पर्सनल ट्रेनर्स और सेपरेट वॉशरूम/लॉकर की सुविधा है।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 13. कमर दर्द और इंजरी (Back Pain & Injury)
    if any(k in lower for k in ["कमर दर्द", "back pain", "कमर", "दर्द", "pain", "इंजरी", "injury", "चोट", "घुटने"]):
        reply = "हाँ, लेकिन आपको केवल हल्की और सही फॉर्म वाली एक्सरसाइज करनी चाहिए। हमारे अनुभवी ट्रेनर्स आपकी कमर का पूरा ध्यान रखकर ही वर्कआउट प्लान करेंगे।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 14. मौसम और बारिश (Weather & Rain)
    if any(k in lower for k in ["मौसम", "weather", "बारिश", "rain", "mausam", "barish"]):
        reply = "हाँ जी! एवेंजर्स फिटनेस क्लब का इनडोर एरिया पूरी तरह एयर-कंडीशंड है, आप बेफिक्र होकर अपने वर्कआउट के लिए आ सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 15. धन्यवाद और आदर (Thank you)
    if any(k in lower for k in ["thank you", "thanks", "thank", "धन्यवाद", "शुक्रिया", "थैंक यू", "dhanyawad", "shukriya"]):
        reply = "यू आर मोस्ट वेलकम! एवेंजर्स फिटनेस क्लब में आपसे मिलकर बहुत अच्छा लगेगा। आपका दिन शुभ हो!"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 16. सप्लीमेंट स्टोर की जानकारी (Supplements Recommendation)
    if any(k in lower for k in ["सप्लीमेंट", "supplement", "whey", "protein", "प्रोटीन", "creatine", "क्रिएटीन", "pre workout", "दुकान", "shop", "सामान"]):
        reply = "हमारे पास 100% ऑरिजिनल ON Gold Standard, Dymatize, MuscleBlaze और Being Strong के सभी प्रोटीन्स, क्रिएटीन और प्री-वर्कआउट उपलब्ध हैं। आप हमारी वेबसाइट पर ऊपर 'Supplement Shop' बटन पर क्लिक करके सीधे ऑर्डर कर सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 17. अन्य सामान्य सवालों के लिए Groq AI
    api_key = (os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY", "")).strip()

    if api_key:
        try:
            system_instructions = (
                "You are Priya, a 24-year-old friendly female front-desk manager at Avengers Fitness Club, Thane West. "
                "Always speak in feminine Hindi grammar. Keep response concise (1-2 sentences) and warmly invite them to visit the gym."
            )
            req_data = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_msg}
                ],
                "temperature": 0.7,
                "max_tokens": 150
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                }
            )

            with urllib.request.urlopen(req, timeout=8) as response:
                result = json.loads(response.read().decode("utf-8"))
                reply = result["choices"][0]["message"]["content"].strip()
                return jsonify({"reply": reply, "show_pass_form": False})
        except Exception as e:
            print(f"⚠️ Groq Note: {e}")

    # सामान्य डिफ़ॉल्ट
    reply = "नमस्ते! मैं एवेंजर्स फिटनेस क्लब से प्रिया बोल रही हूँ। आप मुझसे जिम की फीस, टाइमिंग, मशीनों या लोकेशन के बारे में पूछ सकते हैं। बताइए, मैं आपकी क्या मदद कर सकती हूँ?"
    return jsonify({"reply": reply, "show_pass_form": False})

# फ़ॉर्म सबमिशन API
@app.route("/api/inquire", methods=["POST"])
def inquire():
    data = request.get_json(silent=True) or request.form or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    message = data.get("message", "").strip()

    now_ist = datetime.datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
        cursor.execute(f"""
            INSERT INTO inquiries (name, email, phone, message, created_at)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        """, (name, email, phone, message, now_ist))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "status": "success", "message": "Thank you! Avengers Fitness Club has received your tour inquiry."}), 201
    except Exception as e:
        print(f"⚠️ Inquiry DB Error: {e}")
        return jsonify({"success": False, "message": "Database error"}), 500

# UPI पेमेंट API
@app.route("/api/pay-upi", methods=["POST"])
def pay_upi():
    data = request.get_json(silent=True) or request.form or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    plan_name = data.get("plan_name", "Gym Membership").strip()
    amount = data.get("amount", "0").strip()
    utr_no = data.get("utr_no", "").strip()

    if not utr_no:
        return jsonify({"success": False, "message": "Please enter valid 12-digit UTR"}), 400

    now_ist = datetime.datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
        cursor.execute(f"""
            INSERT INTO payments (name, phone, email, plan_name, amount, utr_no, status, created_at)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        """, (name, phone, email, plan_name, amount, utr_no, "Pending Verification", now_ist))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "status": "success", "message": "Payment recorded"}), 201
    except Exception as e:
        print(f"⚠️ Payment DB Error: {e}")
        return jsonify({"success": False, "message": "Payment recording failed"}), 500

# वॉयस कॉल पास बुकिंग API
@app.route("/api/book-voice-pass", methods=["POST"])
def book_voice_pass():
    data = request.get_json(silent=True) or request.form or {}
    name = data.get("name", "").strip() or "Voice Call Guest"
    phone = data.get("phone", "").strip() or "Via Voice Call"
    visit_day = data.get("visit_day", "कल (Tomorrow)").strip()
    email = data.get("email", "").strip() or f"{clean_phone(phone)}@voice.guest"
    message = f"Free Guest Pass Requested via Priya Voice Call for: {visit_day}"

    now_ist = datetime.datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
        cursor.execute(f"""
            INSERT INTO inquiries (name, email, phone, message, created_at)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        """, (name, email, phone, message, now_ist))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "status": "success", "message": f"Pass booked for {visit_day}!"}), 201
    except Exception as e:
        print(f"⚠️ Voice Pass DB Error: {e}")
        return jsonify({"success": False, "message": "Database error"}), 500

def clean_phone(phone):
    return re.sub(r'\D', '', phone) or "guest"

# Admin Routes
@app.route("/admin")
def admin_portal():
    if session.get("logged_in"):
        rows, payments, orders = [], [], []
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, phone, email, message, created_at FROM inquiries ORDER BY id DESC")
            rows = cursor.fetchall()

            cursor.execute("SELECT id, name, phone, email, plan_name, amount, utr_no, status, created_at FROM payments ORDER BY id DESC")
            payments = cursor.fetchall()

            cursor.execute("""
                SELECT id, order_number, customer_name, customer_phone, product_name,
                       brand, flavor, weight_size, quantity, total_amount,
                       delivery_type, address, payment_method, status, created_at
                FROM supplement_orders ORDER BY id DESC
            """)
            orders = cursor.fetchall()

            conn.close()
        except Exception as e:
            print(f"⚠️ Admin fetch DB error: {e}")
        return render_template_string(DASHBOARD_HTML, rows=rows, payments=payments, orders=orders)
    
    if session.get("pending_2fa"):
        return render_template_string(OTP_HTML, masked_email=mask_email(ADMIN_EMAIL))
    
    return render_template_string(LOGIN_HTML)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        otp_code = f"{random.randint(100000, 999999)}"
        session["pending_2fa"] = True
        session["otp"] = otp_code
        session["otp_expiry"] = time.time() + 300

        trigger_otp(ADMIN_EMAIL, otp_code)
        return redirect("/admin")
    else:
        return render_template_string(LOGIN_HTML, error="Invalid Username or Password. Access Denied.")

@app.route("/admin/verify-otp", methods=["POST"])
def verify_otp():
    if not session.get("pending_2fa"):
        return redirect("/admin")

    entered_otp = request.form.get("otp", "").strip()
    saved_otp = session.get("otp")
    expiry = session.get("otp_expiry", 0)

    if time.time() > expiry:
        return render_template_string(OTP_HTML, masked_email=mask_email(ADMIN_EMAIL), error="OTP Expired. Please request a new one.")

    if entered_otp == saved_otp:
        session["logged_in"] = True
        session.pop("pending_2fa", None)
        session.pop("otp", None)
        session.pop("otp_expiry", None)
        return redirect("/admin")
    else:
        return render_template_string(OTP_HTML, masked_email=mask_email(ADMIN_EMAIL), error="Incorrect OTP. Please check and try again.")

@app.route("/admin/resend-otp")
def resend_otp():
    if not session.get("pending_2fa"):
        return redirect("/admin")
    
    otp_code = f"{random.randint(100000, 999999)}"
    session["otp"] = otp_code
    session["otp_expiry"] = time.time() + 300
    trigger_otp(ADMIN_EMAIL, otp_code)
    return render_template_string(OTP_HTML, masked_email=mask_email(ADMIN_EMAIL), msg="A new OTP has been sent!")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin")

@app.route("/admin/verify-payment/<int:payment_id>", methods=["POST"])
def verify_payment(payment_id):
    if not session.get("logged_in"):
        return redirect("/admin")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
        cursor.execute(f"UPDATE payments SET status = 'Verified / Paid' WHERE id = {placeholder}", (payment_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Verify error: {e}")
    return redirect("/admin")

@app.route("/admin/update-order-status/<int:order_id>", methods=["POST"])
def update_order_status(order_id):
    if not session.get("logged_in"):
        return redirect("/admin")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
        cursor.execute(f"UPDATE supplement_orders SET status = 'Delivered / Completed' WHERE id = {placeholder}", (order_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Update order error: {e}")
    return redirect("/admin")

if __name__ == "__main__":
    init_db()
    print("Avengers Fitness Club Server running on http://127.0.0.1:8080")
    print("Store available at http://127.0.0.1:8080/store")
    print("Admin view protected with 2FA at http://127.0.0.1:8080/admin")
    app.run(host="0.0.0.0", port=8080, debug=True, threaded=True)
