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
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = "velora_ultra_secure_gym_secret_key_2026"

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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# आपका नया Google Webhook URL (Render से 100% गारंटेड ईमेल भेजने के लिए)
GOOGLE_MAIL_WEBHOOK = os.environ.get(
    "MAIL_WEBHOOK_URL",
    "https://script.google.com/macros/s/AKfycbxTbmhpLEeTK1i0Jb9X7gMGDt6-tJ_QaNnjnQo9tPNWR5TXBKUYR3Et8RsTX4S-ztUwcg/exec"
)

SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

DB_FILE = "inquiries.db"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def mask_email(email):
    if "@" in email:
        user, domain = email.split("@", 1)
        prefix = user[:2] if len(user) >= 2 else user[:1]
        return f"{prefix}****@{domain}"
    return email

def send_otp_background(to_email, otp_code):
    print("\n" + "=" * 48)
    print(f"🔑 [Total Gym 2FA] Your OTP code is: {otp_code}")
    print(f"📧 Destination: {to_email}")
    print("=" * 48 + "\n")

    # 1. Google Webhook के ज़रिए सीधे ईमेल भेजना (HTTPS - Render पर 100% काम करेगा)
    if GOOGLE_MAIL_WEBHOOK:
        try:
            payload = json.dumps({
                "to": to_email,
                "subject": f"Total Gym Security OTP: {otp_code}",
                "body": f"Hello,\n\nYour Total Gym Admin verification OTP is: {otp_code}\n\nValid for 5 minutes.\n\n- Total Gym Security"
            }).encode("utf-8")
            
            req = urllib.request.Request(
                GOOGLE_MAIL_WEBHOOK,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                print(f"✅ OTP email successfully delivered to {to_email} via Google Webhook!")
                return
        except Exception as e:
            print(f"⚠️ Webhook Email Note: {e}")

    # 2. बैकअप के लिए SMTP (लोकल लैपटॉप के लिए)
    if SMTP_EMAIL and SMTP_PASSWORD:
        try:
            msg = MIMEText(f"Hello,\n\nYour Total Gym Admin verification OTP is: {otp_code}\n\nValid for 5 minutes.\n\n- Total Gym Security")
            msg["Subject"] = f"Total Gym Security OTP: {otp_code}"
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
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

# सर्वर शुरू होते ही डेटाबेस और टेबल तुरंत तैयार करना
init_db()

@app.route("/")
def home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "Total Gym Website Home"

@app.route("/<path:filename>")
def serve_file(filename):
    return send_from_directory(".", filename)

# चैटबॉट API
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()

    if not user_msg:
        return jsonify({"reply": "Please ask a question."}), 400

    system_instructions = "You are Total Gym Assistant. Be helpful and polite. Keep words like Fees, Timing, Membership in English."
    if os.path.exists("instructions.txt"):
        with open("instructions.txt", "r", encoding="utf-8") as f:
            system_instructions = f.read()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if api_key and api_key != "यहाँ_अपनी_असली_OpenAI_API_Key_डालें":
        try:
            req_data = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_msg}
                ],
                "temperature": 0.7,
                "max_tokens": 300
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
            )

            with urllib.request.urlopen(req, timeout=12) as response:
                result = json.loads(response.read().decode("utf-8"))
                reply = result["choices"][0]["message"]["content"]
                return jsonify({"reply": reply})

        except Exception as e:
            print(f"Chatbot API Note: {e}")

    lower = user_msg.lower()
    if any(k in lower for k in ["timing", "time", "open", "समय"]):
        reply = "Total Gym का Timing:\n• Monday to Saturday: 6:00 AM – 10:00 PM\n• Sunday: 8:00 AM – 6:00 PM\nFacility Tours: Tuesday to Saturday (10:00 AM – 7:00 PM)"
    elif any(k in lower for k in ["price", "cost", "fee", "fees", "membership", "plan", "कीमत"]):
        reply = "हमारे Membership Plans हैं:\n1. Studio: ₹4,999/month\n2. Performance: ₹7,999/month\n3. Elite Private: ₹11,999/month\n\nAap website par 'Book your tour now' button se free tour book kar sakte hain!"
    elif any(k in lower for k in ["location", "address", "कहाँ", "पता", "kaha"]):
        reply = "Total Gym Ghodbunder Road, Thane West, Mumbai mein located hai."
    elif any(k in lower for k in ["program", "class", "training", "workout"]):
        reply = "हमारे 3 Core Training Programs हैं:\n1. Forge Strength (Barbell strength & progressive overload)\n2. Length & Load (Mobility & loaded stretching)\n3. Aether Conditioning (Zone-2 cardio & endurance)"
    else:
        reply = "Namaste! Total Gym mein aapka welcome hai. Main aapki kya help kar sakta hoon? Aap mujhse Timing, Fees, Membership Plans ya Training Programs ke baare mein pooch sakte hain."

    return jsonify({"reply": reply})

# फ़ॉर्म सबमिशन API
@app.route("/api/inquire", methods=["POST"])
def inquire():
    data = request.get_json(silent=True) or request.form
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    message = data.get("message", "").strip()

    now_ist = datetime.datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inquiries (name, email, phone, message, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, email, phone, message, now_ist))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "status": "success", "message": "Thank you! Your tour inquiry has been received."}), 201

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Total Gym - Admin Login</title>
    <style>
        body { background-color: #0b0b0b; color: #fff; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #141416; padding: 40px; border-radius: 12px; border: 1px solid #2a2a2e; width: 340px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); }
        h2 { color: #e5a93c; text-align: center; margin-top: 0; font-size: 24px; letter-spacing: 1px; }
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
        <h2>TOTAL GYM ADMIN</h2>
        <div class="sub">Step 1: Security Credentials</div>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST" action="/admin/login">
            <label>Username</label>
            <input type="text" name="username" required autofocus autocomplete="off">
            <label>Password</label>
            <input type="password" name="password" required>
            <button type="submit">Continue to 2FA →</button>
        </form>
        <a href="/" class="back-link">← Back to Total Gym Website</a>
    </div>
</body>
</html>
"""

OTP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Total Gym - 2-Factor Authentication</title>
    <style>
        body { background-color: #0b0b0b; color: #fff; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .otp-card { background: #141416; padding: 40px; border-radius: 12px; border: 1px solid #2a2a2e; width: 340px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); text-align: center; }
        .shield-icon { font-size: 40px; margin-bottom: 10px; }
        h2 { color: #e5a93c; margin: 0 0 10px 0; font-size: 22px; }
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

# व्यवस्थित एडमिन डैशबोर्ड
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Inquiry Submissions (Admin)</title>
    <style>
        body { background-color: #0d0d0f; color: #e5e5e5; font-family: 'Segoe UI', sans-serif; padding: 30px 40px; margin: 0; }
        .container { max-width: 1380px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #202025; }
        .header a.back-link { color: #e5a93c; text-decoration: none; font-size: 13px; margin-bottom: 6px; display: inline-block; }
        .header a.back-link:hover { text-decoration: underline; }
        .header h1 { color: #e5a93c; margin: 0; font-size: 26px; font-weight: 600; }
        .btn-logout { background: #2b1111; color: #ff8b8b; padding: 8px 18px; border-radius: 6px; border: 1px solid #4a1f1f; text-decoration: none; font-size: 13px; font-weight: bold; }
        .btn-logout:hover { background: #5a2020; color: #fff; }
        .badge { background: #231c11; color: #e5a93c; border: 1px solid #4a3818; padding: 6px 12px; border-radius: 6px; font-size: 12px; margin-right: 15px; }
        
        .table-card { background: #131316; border-radius: 10px; overflow: hidden; border: 1px solid #25252b; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        table { width: 100%; border-collapse: collapse; text-align: left; table-layout: auto; }
        th { background: #1a1a20; color: #e5a93c; padding: 16px 18px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; border-bottom: 1px solid #2a2a32; }
        td { padding: 16px 18px; border-bottom: 1px solid #1c1c22; font-size: 14px; vertical-align: middle; }
        tr:hover { background: #17171d; }
        
        .col-id { color: #888; font-weight: bold; width: 50px; }
        .col-name { color: #ffffff; font-weight: 600; width: 180px; }
        .col-phone { color: #e5a93c; font-weight: 600; width: 160px; white-space: nowrap; }
        .col-email a { color: #6495ed; text-decoration: none; }
        .col-email a:hover { text-decoration: underline; }
        .col-msg { color: #d0d0d0; line-height: 1.5; }
        .col-time { color: #888; font-size: 13px; white-space: nowrap; width: 190px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <a href="/" class="back-link">← Back to Total Gym Website</a>
                <h1>Inquiry Submissions (Admin)</h1>
            </div>
            <div>
                <span class="badge">🛡️ 2FA Verified Session</span>
                <a href="/admin/logout" class="btn-logout">Logout</a>
            </div>
        </div>

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
                    {% for item_id, item_name, item_phone, item_email, item_msg, item_time in rows %}
                    <tr>
                        <td class="col-id">#{{ item_id }}</td>
                        <td class="col-name">{{ item_name }}</td>
                        <td class="col-phone">{{ item_phone or '—' }}</td>
                        <td class="col-email"><a href="mailto:{{ item_email }}">{{ item_email }}</a></td>
                        <td class="col-msg">{{ item_msg }}</td>
                        <td class="col-time">{{ item_time }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" style="text-align: center; color: #666; padding: 40px;">No inquiries found yet.</td>
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
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, phone, email, message, created_at FROM inquiries ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return render_template_string(DASHBOARD_HTML, rows=rows)
    
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
    print("Total Gym Server running on http://127.0.0.1:8080")
    print("Admin view protected with 2FA at http://127.0.0.1:8080/admin")
    app.run(host="127.0.0.1", port=8080, debug=True, threaded=True)