from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, send_from_directory
import sqlite3
import datetime
import os
import re
import random
import time
import threading
import smtplib
import json
import urllib.request
import urllib.error
from email.mime.text import MIMEText

# क्लाउड डेटाबेस (PostgreSQL) सपोर्ट
try:
    import psycopg2
except ImportError:
    psycopg2 = None

app = Flask(__name__)
app.secret_key = "avengers_fitness_club_secret_key_2026"
# ==============================================================================
# 🔒 13-DAY CLIENT DEMO LICENSE LOCK (DEVELOPER: ADARSH SHRIVASTAVA)
# Render Environment Variable 'DEMO_MODE' से कंट्रोल होता है:
# 1. 'ACTIVE'  -> 16 अक्टूबर 2026 तक खुला, फिर ऑटोमैटिक लॉक
# 2. 'OFF'     -> लाइफटाइम परमानेंट अनलॉक (पेमेंट मिलने के बाद)
# 3. 'LOCKED'  -> तुरंत किसी भी समय वेबसाइट बंद करने के लिए
# ==============================================================================
DEMO_EXPIRY_DATE = datetime.date(2026, 10, 16)

@app.before_request
def check_client_demo_license():
    # एडमिन लॉगिन और जरूरी फाइल्स पर ताला नहीं लगेगा
    if request.path.startswith("/admin") or request.path.startswith("/static"):
        return None

    # आदर्श की सीक्रेट मास्टर चाबी (?unlock=somu@69)
    if request.args.get("unlock") == "somu@69":
        session["dev_unlocked"] = True
    if session.get("dev_unlocked"):
        return None

    # Render से मोड चेक करना (डिफ़ॉल्ट 'ACTIVE' रहेगा)
    mode = os.environ.get("DEMO_MODE", "ACTIVE").strip().upper()

    if mode in ["OFF", "UNLOCKED", "LIFETIME"]:
        return None

    today = datetime.date.today()
    if mode == "LOCKED" or (mode == "ACTIVE" and today > DEMO_EXPIRY_DATE):
        lock_html = """
        <!DOCTYPE html>
        <html lang="hi">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Demo Access Expired | Avengers Fitness Club</title>
            <style>
                body { background: #080808; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
                .card { background: linear-gradient(145deg, #1c1a17, #100f0d); border: 2px solid #d4af37; border-radius: 20px; padding: 40px 25px; text-align: center; max-width: 460px; width: 100%; box-shadow: 0 10px 40px rgba(212,175,55,0.25); }
                .icon { font-size: 54px; margin-bottom: 12px; }
                h1 { color: #e5c07b; font-size: 22px; margin-bottom: 12px; letter-spacing: 0.8px; text-transform: uppercase; }
                p { color: #ccc; font-size: 14px; line-height: 1.6; margin: 0 0 16px; }
                .contact-box { background: rgba(212,175,55,0.1); border: 1px dashed #d4af37; border-radius: 12px; padding: 14px; margin-top: 20px; }
                .contact-box span { color: #ffd700; font-weight: bold; font-size: 16px; display: block; margin-top: 4px; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">🔒</div>
                <h1>Demo Preview Expired</h1>
                <p>Avengers Fitness Club Website की 13-days की demo trial अवधि पूरी हो चुकी है।</p>
                <p>Website और AI System का <strong>Complete lifetime access</strong> Activate कराने के लिए कृपया main developer से संपर्क करें।</p>
                <div class="contact-box">
                    <p style="margin:0; font-size:12px; color:#aaa;">Official Web Developer:</p>
                    <span>Adarsh Shrivastava (Gmail-aadarshshrivastava008@gmail.com</span>
                </div>
            </div>
        </body>
        </html>
        """
        return render_template_string(lock_html), 403

# .env फ़ाइल से क्रेडेंशियल्स लोड करना
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "velora@123")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "aadarshshrivastava008@gmail.com")

# Groq / Llama 3 API Key
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

# जिम का UPI ID
GYM_UPI_ID = os.environ.get("GYM_UPI_ID", "avengersfitness@upi")
GYM_NAME = os.environ.get("GYM_NAME", "Avengers Fitness Club")

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
                print(f"✅ OTP email successfully delivered to {to_email} via Google Webhook!")
                return
        except urllib.error.HTTPError as e:
            if e.code in [200, 302]:
                print(f"✅ OTP email successfully delivered to {to_email} via Google Webhook!")
                return
            print(f"⚠️ Webhook Email Note: {e}")
        except Exception as e:
            print(f"⚠️ Webhook Email Note: {e}")

    if SMTP_EMAIL and SMTP_PASSWORD:
        try:
            msg = MIMEText(f"Hello,\n\nYour Avengers Fitness Club Admin verification OTP is: {otp_code}\n\nValid for 5 minutes.\n\n- Avengers Fitness Club Security")
            msg["Subject"] = f"Avengers Fitness Club Security OTP: {otp_code}"
            msg["From"] = SMTP_EMAIL
            msg["To"] = to_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.send_message(msg)
            print(f"✅ OTP email delivered via SMTP to {to_email}!")
        except Exception as e:
            print(f"⚠️ SMTP Note: {e}")

def trigger_otp(to_email, otp_code):
    t = threading.Thread(target=send_otp_background, args=(to_email, otp_code), daemon=True)
    t.start()

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
        conn.commit()
        conn.close()
        print("✅ Database tables successfully connected and initialized!")
    except Exception as e:
        print(f"⚠️ Database initialization note: {e}")

init_db()

@app.route("/")
def home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "Avengers Fitness Club Website Home"

@app.route("/<path:filename>")
def serve_file(filename):
    return send_from_directory(".", filename)

# ==================== प्रिया AI चैटबॉट और वॉयस कॉल API ====================
# चैटबॉट और वॉयस कॉल API (Top Priority Lead & Pass Flow)
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()

    if not user_msg:
        return jsonify({"reply": "नमस्ते! मैं प्रिया बोल रही हूँ। बताइए, मैं आपकी क्या मदद कर सकती हूँ?"}), 200

    lower = user_msg.lower()

    # 1. अगर क्लाइंट ने मना किया ("नहीं / No")
    no_phrases = ["नहीं", "नही", "nahi", "nahin", "नहीं चाहिए", "नहीं बनवाना", "रहने दो", "बाद में", "not now"]
    has_no = any(p in lower for p in no_phrases) or bool(re.search(r"\bno\b", lower))
    if has_no:
        reply = "कोई बात नहीं! एवेंजर्स फिटनेस क्लब में कॉल करने और बात करने के लिए आपका बहुत-बहुत धन्यवाद। जब भी आपको समय मिले, आप एक बार हमारे जिम में जरूर विजिट कीजिएगा। आपका दिन शुभ हो!"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 2. फ्री गेस्ट पास बुकिंग / विज़िट डेट ("हाँ", "कल", "tomorrow", "after tomorrow", "gate pass", "बुक")
    pass_booking_triggers = [
        "कल", "kal", "tomorrow", "parso", "परसों", "narso", "नरसों", "after tomorrow", "day after tomorrow",
        "बुक कर", "book kar", "पास बना", "pass bana", "pass book", "पास बुक", "gate pass", "गेस्ट पास", "गेट पास",
        "फ्री पास", "free pass"
    ]
    has_booking = any(b in lower for b in pass_booking_triggers)
# नई लाइन (New Code):
    has_pure_yes = bool(re.search(r"\b(yes|haan|ha)\b", lower)) or bool(re.search(r"(?:^|[\s,।!?])(हाँ|हां)(?:$|[\s,।!?])", lower))

# जब क्लाइंट पास बुक करने या आने का दिन बोले -> सीधे दोनों इनपुट बॉक्स दिखाएं
    if has_booking or has_pure_yes:
        # 1. दिन (Day) पहचानना
        if "after tomorrow" in lower or "परसों" in lower or "parso" in lower:
            day = "परसों (Day After Tomorrow)"
        elif "नरसों" in lower or "narso" in lower:
            day = "नरसों (In 3 Days)"
        elif "आज" in lower or "aaj" in lower or "today" in lower:
            day = "आज (Today)"
        else:
            day = "कल (Tomorrow)"

        # 2. समय (Time) पहचानना और दिन के साथ जोड़ना
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

# 3. समय और टाइमिंग (Timing सवाल - पहले चेक होगा)
    timing_words = ["timing", "time", "open", "समय", "घंटे", "टाइम", "खुलता", "टाइमिंग", "schedule", "बजे"]
    if any(k in lower for k in timing_words):
        reply = "एवेंजर्स फिटनेस क्लब सोमवार से शनिवार सुबह 5:30 से रात 10:45 तक और रविवार को सुबह 7 से दोपहर 2 बजे तक खुला रहता है। आप अपने वर्कआउट के लिए कभी भी आ सकते हैं!"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 4. पसंदीदा समय का जवाब (Morning, Afternoon, Evening Motivation)
    morning_words = ["morning", "सुबह", "मॉर्निंग", "subah", "saverey", "savere"]
    afternoon_words = ["afternoon", "दोपहर", "दुपहर", "dopahar"]
    evening_words = ["evening", "शाम", "रात", "इवनिंग", "shaam", "sham", "night"]

    if any(k in lower for k in morning_words):
        reply = "बहुत बढ़िया! सुबह का समय वर्कआउट के लिए सबसे बेस्ट होता है, उस समय पूरा जिम फ्रेश एनर्जी और शानदार पॉजिटिव वाइब्स से भरा होता है। क्या आप कल सुबह का 1-डे फ्री गेस्ट पास बनवाना चाहते हैं?"
        return jsonify({"reply": reply, "show_pass_form": False})

    elif any(k in lower for k in afternoon_words):
        reply = "शानदार चॉइस! दोपहर के समय जिम में काफी शांत और रिलैक्स माहौल रहता है, जिससे आप बिना किसी भीड़ के सभी Being Strong मशीनों पर आसानी से वर्कआउट कर सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    elif any(k in lower for k in evening_words):
        reply = "अरे वाह! शाम का समय दिनभर की थकान मिटाने और एनर्जेटिक वर्कआउट के लिए एकदम परफेक्ट है। उस समय हमारे जिम में बहुत ही मोटिवेटिंग वाइब होती है।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 5. पता और लोकेशन (Address बटन / सवाल)
    if any(k in lower for k in ["location", "address", "एड्रेस", "एड्रैस", "लोकेशन", "कहाँ", "पता", "kaha", "landmark", "किधर"]):
        reply = "एवेंजर्स फिटनेस क्लब का पता है: शॉप नंबर 2, भुकेंद्र बस स्टॉप, पोखरण रोड नंबर 1, उपवन लेक और येउर गेट के पास, ठाणे वेस्ट। आप यहाँ बहुत आसानी से पहुँच सकते हैं।"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 6. फीस और पैकेज (Fees बटन / सवाल)
    if any(k in lower for k in ["price", "cost", "fee", "fees", "membership", "plan", "offer", "फीस", "पैसा", "कीमत", "चार्ज", "रेट"]):
        reply = "हमारा सबसे लोकप्रिय एनुअल स्पेशल प्लान केवल 11,999 रुपये प्रति वर्ष का है, जिसमें बीइंग स्ट्रांग मशीनें और स्टीम बाथ शामिल हैं। मंथली प्लान 2,499 रुपये का है। क्या मैं आपके लिए एक दिन का फ्री गेस्ट पास बुक कर दूँ?"
        return jsonify({"reply": reply, "show_pass_form": False})

    # 7. मशीनें और सुविधाएं (Equipment बटन / सवाल)
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

    # 16. अन्य सामान्य सवालों के लिए Groq AI
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
# वॉयस कॉल स्क्रीन से मैनुअल पास बुक करने की API
@app.route("/api/book-voice-pass", methods=["POST"])
def book_voice_pass():
    data = request.get_json(silent=True) or request.form or {}
    name = data.get("name", "").strip() or "Voice Call Guest"
    phone = data.get("phone", "").strip() or "Via Voice Call"
    visit_day = data.get("visit_day", "कल (Tomorrow)").strip()
    
    clean_user = "".join([c for c in name if c.isalnum()]).lower() or "guest"
    email = data.get("email", "").strip() or f"{clean_user}@guest.avengersfitness.com"
    pass_note = f"1-Day Free Guest Pass [Visit Scheduled: {visit_day}]"
    now_ist = datetime.datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
        cursor.execute(f"""
            INSERT INTO inquiries (name, email, phone, message, created_at)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        """, (name, email, phone, pass_note, now_ist))
        conn.commit()
        conn.close()
        print(f"✅ Voice pass booked for {name} ({phone}) on {visit_day}!")
    except Exception as err:
        print(f"⚠️ Voice Pass DB Error: {err}")

    reply = f"बधाई हो {name} जी! आपका एक दिन का फ्री गेस्ट पास {visit_day} के लिए सफलतापूर्वक बुक हो गया है। आप जब भी आएं, रिसेप्शन पर अपना मोबाइल नंबर बताकर वर्कआउट शुरू कर सकते हैं। एवेंजर्स फिटनेस क्लब में आपका स्वागत है!"
    return jsonify({"success": True, "reply": reply})
# सामान्य फ़ॉर्म सबमिशन API
@app.route("/api/inquire", methods=["POST"])
def inquire():
    data = request.get_json(silent=True) or request.form
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

# ऑनलाइन UPI पेमेंट (UTR) सबमिशन API
@app.route("/api/pay-upi", methods=["POST"])
def pay_upi():
    data = request.get_json(silent=True) or request.form
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    plan_name = data.get("plan_name", "Gym Membership").strip()
    amount = data.get("amount", "0").strip()
    utr_no = data.get("utr_no", "").strip()

    if not utr_no or len(utr_no) < 6:
        return jsonify({"success": False, "message": "Please enter a valid 12-digit UTR/UPI Reference Number."}), 400

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
        return jsonify({"success": True, "status": "success", "message": "Payment recorded successfully! Your membership will be activated after UTR verification."}), 201
    except Exception as e:
        print(f"⚠️ Pay-UPI DB Error: {e}")
        return jsonify({"success": False, "message": "Database error"}), 500

# एडमिन द्वारा पेमेंट वेरिफाई करने का रूट
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
        print(f"⚠️ Verify Payment DB Error: {e}")
    return redirect("/admin")

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Avengers Fitness Club - Admin Login</title>
    <style>
        body { background-color: #0b0b0b; color: #fff; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #141416; padding: 40px; border-radius: 12px; border: 1px solid #2a2a2e; width: 340px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); }
        h2 { color: #e5a93c; text-align: center; margin-top: 0; font-size: 20px; letter-spacing: 0.8px; }
        .sub { text-align: center; color: #777; font-size: 13px; margin-bottom: 20px; }
        .error { background: #4a1515; color: #ff8b8b; padding: 10px; border-radius: 6px; font-size: 13px; text-align: center; margin-bottom: 15px; }
        label { display: block; font-size: 13px; color: #a0a0a0; margin-bottom: 6px; }
        input[type="text"], input[type="password"] { width: 100%; padding: 12px; box-sizing: border-box; background: #202024; border: 1px solid #333; border-radius: 6px; color: #fff; margin-bottom: 18px; outline: none; }
        input:focus { border-color: #e5a93c; }
        button { width: 100%; padding: 12px; background: #e5a93c; border: none; border-radius: 6px; font-weight: bold; color: #000; cursor: pointer; font-size: 15px; }
        button:hover { background: #f5b94c; }
        .back-link { display: block; text-align: center; margin-top: 15px; color: #777; text-decoration: none; font-size: 13px; }
        .back-link:hover { color: #e5a93c; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>AVENGERS FITNESS CLUB</h2>
        <div class="sub">Step 1: Security Credentials</div>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST" action="/admin/login">
            <label>Username</label>
            <input type="text" name="username" required autofocus autocomplete="off">
            <label>Password</label>
            <input type="password" name="password" required>
            <button type="submit">Continue to 2FA →</button>
        </form>
        <a href="/" class="back-link">← Back to Avengers Fitness Club</a>
    </div>
</body>
</html>
"""

OTP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Avengers Fitness Club - 2-Factor Authentication</title>
    <style>
        body { background-color: #0b0b0b; color: #fff; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .otp-card { background: #141416; padding: 40px; border-radius: 12px; border: 1px solid #2a2a2e; width: 340px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); text-align: center; }
        .shield-icon { font-size: 40px; margin-bottom: 10px; }
        h2 { color: #e5a93c; margin: 0 0 10px 0; font-size: 20px; }
        p { color: #a0a0a0; font-size: 13px; line-height: 1.5; margin-bottom: 20px; }
        .email-badge { color: #e5a93c; font-weight: bold; background: #231c11; padding: 3px 8px; border-radius: 4px; }
        .error { background: #4a1515; color: #ff8b8b; padding: 10px; border-radius: 6px; font-size: 13px; text-align: center; margin-bottom: 15px; }
        .success { background: #15381d; color: #75e08a; padding: 10px; border-radius: 6px; font-size: 13px; text-align: center; margin-bottom: 15px; }
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

# व्यवस्थित एडमिन डैशबोर्ड (Inquiries + UPI Payments with Email Column)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Avengers Fitness Club - Admin Portal</title>
    <style>
        body { background-color: #0d0d0f; color: #e5e5e5; font-family: 'Segoe UI', sans-serif; padding: 30px 40px; margin: 0; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #202025; }
        .header a.back-link { color: #e5a93c; text-decoration: none; font-size: 13px; margin-bottom: 6px; display: inline-block; }
        .header a.back-link:hover { text-decoration: underline; }
        .header h1 { color: #e5a93c; margin: 0; font-size: 22px; font-weight: 600; }
        .btn-logout { background: #2b1111; color: #ff8b8b; padding: 8px 18px; border-radius: 6px; border: 1px solid #4a1f1f; text-decoration: none; font-size: 13px; font-weight: bold; }
        .btn-logout:hover { background: #5a2020; color: #fff; }
        .badge { background: #231c11; color: #e5a93c; border: 1px solid #4a3818; padding: 6px 12px; border-radius: 6px; font-size: 12px; margin-right: 15px; }
        
        .section-title { color: #e5a93c; font-size: 18px; font-weight: bold; margin: 30px 0 15px 0; display: flex; align-items: center; gap: 10px; }
        .table-card { background: #131316; border-radius: 10px; overflow: hidden; border: 1px solid #25252b; box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom: 30px; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { background: #1a1a20; color: #e5a93c; padding: 14px 18px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; border-bottom: 1px solid #2a2a32; }
        td { padding: 14px 18px; border-bottom: 1px solid #1c1c22; font-size: 14px; vertical-align: middle; }
        tr:hover { background: #17171d; }
        
        .badge-status { background: #3d2c0d; color: #f5b94c; padding: 5px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; border: 1px solid #7a5410; display: inline-block; }
        .badge-verified { background: #15381d; color: #75e08a; padding: 5px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; border: 1px solid #236330; display: inline-block; }
        .btn-verify { background: #1b5e20; color: #fff; border: 1px solid #2e7d32; padding: 6px 14px; border-radius: 5px; font-size: 12px; font-weight: bold; cursor: pointer; transition: 0.2s; margin-left: 8px; vertical-align: middle; }
        .btn-verify:hover { background: #2e7d32; }
        .utr-code { font-family: monospace; font-size: 15px; color: #5ce1e6; font-weight: bold; letter-spacing: 1px; }
        .amount-tag { color: #75e08a; font-weight: bold; font-size: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <a href="/" class="back-link">← Back to Avengers Fitness Club Website</a>
                <h1>Avengers Fitness Club Management Portal</h1>
            </div>
            <div>
                <span class="badge">🛡️ 2FA Verified</span>
                <a href="/admin/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <!-- 1. ऑनलाइन UPI पेमेंट्स टेबल (EMAIL कॉलम के साथ) -->
        <div class="section-title">💳 Online UPI Payments & Memberships (UTR Submissions)</div>
        <div class="table-card">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>NAME</th>
                        <th>PHONE</th>
                        <th>EMAIL</th>
                        <th>PLAN</th>
                        <th>AMOUNT</th>
                        <th>UTR NUMBER</th>
                        <th>STATUS / ACTION</th>
                        <th>SUBMITTED AT</th>
                    </tr>
                </thead>
                <tbody>
                    {% for p_id, p_name, p_phone, p_email, p_plan, p_amount, p_utr, p_status, p_time in payments %}
                    <tr>
                        <td>#{{ p_id }}</td>
                        <td style="font-weight: bold; color: #fff;">{{ p_name }}</td>
                        <td style="color: #e5a93c;">{{ p_phone }}</td>
                        <td><a href="mailto:{{ p_email }}" style="color: #6495ed; text-decoration: none;">{{ p_email or '—' }}</a></td>
                        <td>{{ p_plan }}</td>
                        <td class="amount-tag">₹{{ p_amount }}</td>
                        <td class="utr-code">{{ p_utr }}</td>
                        <td>
                            {% if p_status == 'Verified / Paid' %}
                                <span class="badge-verified">🟢 Verified / Paid</span>
                            {% else %}
                                <span class="badge-status">🟡 {{ p_status }}</span>
                                <form method="POST" action="/admin/verify-payment/{{ p_id }}" style="display:inline;">
                                    <button type="submit" class="btn-verify" onclick="return confirm('क्या आपने बैंक खाते में पैसे चेक कर लिए हैं? इसे Verified मार्क करें?')">✅ Mark Verified</button>
                                </form>
                            {% endif %}
                        </td>
                        <td style="color: #888;">{{ p_time }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="9" style="text-align: center; color: #666; padding: 30px;">No online payments submitted yet.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <!-- 2. सामान्य इन्क्वायरी टेबल -->
        <div class="section-title">📩 General Tour & Membership Inquiries</div>
        <div class="table-card">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>NAME</th>
                        <th>PHONE</th>
                        <th>EMAIL</th>
                        <th>MESSAGE</th>
                        <th>SUBMITTED AT</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item_id, item_name, item_phone, item_email, item_msg, item_time in inquiries %}
                    <tr>
                        <td>#{{ item_id }}</td>
                        <td style="font-weight: bold; color: #fff;">{{ item_name }}</td>
                        <td style="color: #e5a93c;">{{ item_phone or '—' }}</td>
                        <td><a href="mailto:{{ item_email }}" style="color: #6495ed; text-decoration: none;">{{ item_email }}</a></td>
                        <td>{{ item_msg }}</td>
                        <td style="color: #888;">{{ item_time }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" style="text-align: center; color: #666; padding: 30px;">No inquiries found yet.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route("/admin")
def admin_portal():
    if session.get("logged_in"):
        inquiries_rows = []
        payments_rows = []
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, phone, email, message, created_at FROM inquiries ORDER BY id DESC")
            inquiries_rows = cursor.fetchall()

            cursor.execute("SELECT id, name, phone, email, plan_name, amount, utr_no, status, created_at FROM payments ORDER BY id DESC")
            payments_rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            print(f"⚠️ Admin fetch DB error: {e}")
        return render_template_string(DASHBOARD_HTML, inquiries=inquiries_rows, payments=payments_rows)
    
    if session.get("pending_2fa"):
        return render_template_string(OTP_HTML, masked_email=mask_email(ADMIN_EMAIL))
    
    return render_template_string(LOGIN_HTML)

# Step 1: Username & Password
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

# Step 2: OTP चेक
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

# OTP Resend
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

if __name__ == "__main__":
    init_db()
    print("Avengers Fitness Club Server running on http://127.0.0.1:8080")
    print("Admin view protected with 2FA at http://127.0.0.1:8080/admin")
    app.run(host="127.0.0.1", port=8080, debug=True, threaded=True)
