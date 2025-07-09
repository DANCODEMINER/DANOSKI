import os
import smtplib
import random
import bcrypt
import psycopg2
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from flask import Flask, request, jsonify
from flask_cors import CORS
import pytz

# === CONFIG ===
EMAIL_FROM = "adchainminer@gmail.com"
EMAIL_PASSWORD = "zfvn fves admc cgwr"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SITE_NAME = "Adchain Miner"
DATABASE_URL = os.getenv("DATABASE_URL")  # Make sure to set this env var in your deployment

app = Flask(__name__)
CORS(app)

# === DB SETUP ===

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name TEXT,
            country TEXT,
            email TEXT UNIQUE,
            password TEXT,
            pin TEXT,
            hash_rate INTEGER DEFAULT 0,
            mined_btc NUMERIC DEFAULT 0,
            withdrawn_btc NUMERIC DEFAULT 0,
            wallet_address TEXT,
            verified BOOLEAN DEFAULT FALSE,
            timezone TEXT,
            suspended BOOLEAN DEFAULT FALSE,
            deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS user_logs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        action TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
''')

    # Admins table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # OTPs table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS otps (
            id SERIAL PRIMARY KEY,
            email TEXT,
            code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            for_admin BOOLEAN DEFAULT FALSE
        );
    ''')

    # Withdrawals table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            amount NUMERIC,
            wallet TEXT,
            status TEXT DEFAULT 'pending',
            fee NUMERIC DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # System settings table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            id SERIAL PRIMARY KEY,
            auto_withdraw_date DATE
        );
    ''')

    # User hash sessions table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_hash_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            hash_amount INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # Mining settings table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mining_settings (
            hash_per_ad INTEGER,
            btc_per_hash NUMERIC
        );
    ''')

    # Central wallet table (live Bitcoin wallet balance tracking)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS central_wallet (
            id SERIAL PRIMARY KEY,
            btc_balance NUMERIC DEFAULT 0
        );
    ''')

    # Wallet settings table (withdrawal fees, etc.)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS wallet_settings (
            id SERIAL PRIMARY KEY,
            withdraw_fee_btc NUMERIC DEFAULT 0
        );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS user_logs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        action TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
''')

    conn.commit()
    cur.close()
    conn.close()

# === UTILITIES ===

def send_otp(email, code):
    subject = f"{SITE_NAME} OTP Verification"
    body = f"Your OTP code is: {code}"
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = email

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(EMAIL_FROM, EMAIL_PASSWORD)
    server.send_message(msg)
    server.quit()

def generate_otp():
    return str(random.randint(100000, 999999))

def log_user_action(user_id, action):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_logs (user_id, action) VALUES (%s, %s)",
        (user_id, action)
    )
    conn.commit()
    cur.close()
    conn.close()

def strong_password(pw):
    import re
    if len(pw) < 6:
        return False
    if not re.search(r'[a-z]', pw):
        return False
    if not re.search(r'[A-Z]', pw):
        return False
    if not re.search(r'[0-9]', pw):
        return False
    if not re.search(r'[^a-zA-Z0-9]', pw):
        return False
    return True

def get_all_timezones():
    return pytz.all_timezones

def convert_utc_to_local(dt, timezone_str):
    utc = pytz.utc
    local_tz = pytz.timezone(timezone_str)
    return dt.replace(tzinfo=utc).astimezone(local_tz)

# === ROUTES ===

@app.route("/user/send-otp", methods=["POST"])
def send_otp_route():
    data = request.json
    email = data.get("email")
    otp = generate_otp()
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO otps (email, code)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET code = EXCLUDED.code, created_at = CURRENT_TIMESTAMP
        """, (email, otp))
        conn.commit()
        cur.close()
        conn.close()
        send_otp(email, otp)
        return jsonify({"message": "OTP sent successfully."})
    except Exception as e:
        print("OTP error:", e)
        return jsonify({"error": "Failed to send OTP."}), 500


@app.route("/user/verify-otp", methods=["POST"])
def verify_otp():
    data = request.json
    email = data.get("email")
    otp = data.get("otp")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and row[0] == otp:
        return jsonify({"message": "OTP verified."})
    return jsonify({"error": "Invalid OTP."}), 400


@app.route("/user/create-account", methods=["POST"])
def create_account():
    data = request.json
    full_name = data.get("full_name")
    country = data.get("country")
    email = data.get("email")
    password = data.get("password")
    pin = data.get("pin")

    if not all([full_name, country, email, password, pin]):
        return jsonify({"error": "All fields required."}), 400

    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "Email already registered."}), 409

    try:
        cur.execute("""
            INSERT INTO users (full_name, country, email, password, pin, email_verified)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """, (full_name, country, email, hashed_password, pin))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Create account error:", e)
        return jsonify({"error": "Account creation failed."}), 500
    finally:
        cur.close()
        conn.close()

    return jsonify({"message": "Account created successfully."})


@app.route("/user/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and bcrypt.checkpw(password.encode(), row[0].encode()):
        return jsonify({"message": "Login successful."})
    return jsonify({"error": "Invalid credentials."}), 401


@app.route("/user/verify-login-pin", methods=["POST"])
def verify_login_pin():
    data = request.json
    email = data.get("email")
    pin = data.get("pin")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT pin FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and row[0] == pin:
        return jsonify({"message": "PIN verified."})
    return jsonify({"error": "Incorrect PIN."}), 401


@app.route("/user/forgot-password", methods=["POST"])
def forgot_password():
    data = request.json
    email = data.get("email")
    otp = generate_otp()

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO otps (email, code)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET code = EXCLUDED.code, created_at = CURRENT_TIMESTAMP
        """, (email, otp))
        conn.commit()
        cur.close()
        conn.close()

        send_otp(email, otp)
        return jsonify({"message": "OTP sent."})
    except Exception as e:
        print("Forgot password error:", e)
        return jsonify({"error": "Could not send OTP."}), 500


@app.route("/user/verify-password-otp", methods=["POST"])
def verify_password_otp():
    data = request.json
    email = data.get("email")
    otp = data.get("otp")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and row[0] == otp:
        return jsonify({"message": "OTP verified."})
    return jsonify({"error": "Invalid OTP."}), 400


@app.route("/user/reset-password", methods=["POST"])
def reset_password():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Password reset successful."})


@app.route("/user/sendresetpin", methods=["POST"])
def send_reset_pin():
    data = request.json
    email = data.get("email")
    otp = generate_otp()

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO otps (email, code)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET code = EXCLUDED.code, created_at = CURRENT_TIMESTAMP
        """, (email, otp))
        conn.commit()
        cur.close()
        conn.close()

        send_otp(email, otp)
        return jsonify({"message": "OTP sent to reset PIN."})
    except Exception as e:
        print("Send reset pin error:", e)
        return jsonify({"error": "Could not send OTP."}), 500


@app.route("/user/verify-pin-otp", methods=["POST"])
def verify_pin_otp():
    data = request.json
    email = data.get("email")
    otp = data.get("otp")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and row[0] == otp:
        return jsonify({"message": "OTP verified."})
    return jsonify({"error": "Invalid OTP."}), 400


@app.route("/user/reset-pin", methods=["POST"])
def reset_pin():
    data = request.json
    email = data.get("email")
    pin = data.get("pin")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET pin = %s WHERE email = %s", (pin, email))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "PIN reset successful."})

# === MINING
@app.route("/user/save-btc-counter", methods=["POST"])
def save_btc_counter():
    email = get_email()
    btc = request.json.get("btc")
    cursor.execute("UPDATE users SET btc_counter = %s WHERE email = %s", (btc, email))
    conn.commit()
    return jsonify({"message": "BTC counter saved."})

@app.route("/user/get-btc-counter", methods=["POST"])
def get_btc_counter():
    email = get_email()
    cursor.execute("SELECT btc_counter FROM users WHERE email = %s", (email,))
    btc = cursor.fetchone()[0]
    return jsonify({"btc": btc})

# 2. Hashrate
@app.route("/user/save-hashrate", methods=["POST"])
def save_hashrate():
    email = get_email()
    hashrate = request.json.get("hashrate")
    cursor.execute("UPDATE users SET total_hashrate = %s WHERE email = %s", (hashrate, email))
    conn.commit()
    return jsonify({"message": "Hashrate saved."})

@app.route("/user/get-hashrate", methods=["POST"])
def get_hashrate():
    email = get_email()
    cursor.execute("SELECT total_hashrate FROM users WHERE email = %s", (email,))
    rate = cursor.fetchone()[0]
    return jsonify({"hashrate": rate})

# 3. Total Mined BTC
@app.route("/user/save-total-mined", methods=["POST"])
def save_total_mined():
    email = get_email()
    btc = request.json.get("btc")
    cursor.execute("UPDATE users SET total_mined = %s WHERE email = %s", (btc, email))
    conn.commit()
    return jsonify({"message": "Total mined BTC saved."})

@app.route("/user/get-total-mined", methods=["POST"])
def get_total_mined():
    email = get_email()
    cursor.execute("SELECT total_mined FROM users WHERE email = %s", (email,))
    btc = cursor.fetchone()[0]
    return jsonify({"btc": btc})

# 4. Total Withdrawn
@app.route("/user/save-total-withdrawn", methods=["POST"])
def save_total_withdrawn():
    email = get_email()
    amount = request.json.get("btc")
    cursor.execute("UPDATE users SET total_withdrawn = %s WHERE email = %s", (amount, email))
    conn.commit()
    return jsonify({"message": "Total withdrawn saved."})

@app.route("/user/get-total-withdrawn", methods=["POST"])
def get_total_withdrawn():
    email = get_email()
    cursor.execute("SELECT total_withdrawn FROM users WHERE email = %s", (email,))
    total = cursor.fetchone()[0]
    return jsonify({"btc": total})

# 5. Active Sessions
@app.route("/user/save-active-sessions", methods=["POST"])
def save_active_sessions():
    email = get_email()
    count = request.json.get("count")
    cursor.execute("UPDATE users SET active_sessions = %s WHERE email = %s", (count, email))
    conn.commit()
    return jsonify({"message": "Active sessions saved."})

@app.route("/user/get-active-sessions", methods=["POST"])
def get_active_sessions():
    email = get_email()
    cursor.execute("SELECT active_sessions FROM users WHERE email = %s", (email,))
    count = cursor.fetchone()[0]
    return jsonify({"sessions": count})

# 6. Next Withdrawal Date
@app.route("/user/save-next-withdrawal", methods=["POST"])
def save_next_withdrawal():
    email = get_email()
    date = request.json.get("date")
    cursor.execute("UPDATE users SET next_withdrawal = %s WHERE email = %s", (date, email))
    conn.commit()
    return jsonify({"message": "Next withdrawal date saved."})

@app.route("/user/get-next-withdrawal", methods=["POST"])
def get_next_withdrawal():
    email = get_email()
    cursor.execute("SELECT next_withdrawal FROM users WHERE email = %s", (email,))
    date = cursor.fetchone()[0]
    return jsonify({"next_date": date})

# 7. Dashboard Messages
@app.route("/user/save-message", methods=["POST"])
def save_message():
    msg = request.json.get("message")
    cursor.execute("INSERT INTO messages (text, created_at) VALUES (%s, %s)", (msg, datetime.now()))
    conn.commit()
    return jsonify({"message": "Message saved."})

@app.route("/user/get-messages", methods=["GET"])
def get_messages():
    cursor.execute("SELECT text FROM messages ORDER BY created_at DESC LIMIT 10")
    messages = [row[0] for row in cursor.fetchall()]
    return jsonify({"messages": messages})

# 8. My Rank
@app.route("/user/save-rank", methods=["POST"])
def save_rank():
    email = get_email()
    rank = request.json.get("rank")
    cursor.execute("UPDATE users SET rank = %s WHERE email = %s", (rank, email))
    conn.commit()
    return jsonify({"message": "Rank saved."})

@app.route("/user/get-my-rank", methods=["POST"])
def get_my_rank():
    email = get_email()
    cursor.execute("SELECT rank FROM users WHERE email = %s", (email,))
    rank = cursor.fetchone()[0]
    return jsonify({"rank": rank})

# 9. My BTC (30d)
@app.route("/user/save-my-btc", methods=["POST"])
def save_my_btc():
    email = get_email()
    btc = request.json.get("btc")
    cursor.execute("UPDATE users SET btc_30d = %s WHERE email = %s", (btc, email))
    conn.commit()
    return jsonify({"message": "BTC (30d) saved."})

@app.route("/user/get-my-btc", methods=["POST"])
def get_my_btc():
    email = get_email()
    cursor.execute("SELECT btc_30d FROM users WHERE email = %s", (email,))
    btc = cursor.fetchone()[0]
    return jsonify({"btc": btc})

# 10. My Hashrate
@app.route("/user/save-my-hashrate", methods=["POST"])
def save_my_hashrate():
    email = get_email()
    hashrate = request.json.get("hashrate")
    cursor.execute("UPDATE users SET my_hashrate = %s WHERE email = %s", (hashrate, email))
    conn.commit()
    return jsonify({"message": "My hashrate saved."})

@app.route("/user/get-my-hashrate", methods=["POST"])
def get_my_hashrate():
    email = get_email()
    cursor.execute("SELECT my_hashrate FROM users WHERE email = %s", (email,))
    hr = cursor.fetchone()[0]
    return jsonify({"hashrate": hr})

@app.route("/user/watch-ad", methods=["POST"])
def watch_ad():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Example logic: boost hashrate and log session
    hashrate_boost = 10  # Or any value based on your reward logic
    duration = 60  # seconds (you can increase this to minutes if needed)

    # Store a new mining session record
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO hash_sessions (email, power, duration, date)
        VALUES (%s, %s, %s, NOW())
    """, (email, hashrate_boost, duration))
    
    # Optionally update user's current hashrate (or track it elsewhere)
    cur.execute("""
        UPDATE users SET hashrate = hashrate + %s WHERE email = %s
    """, (hashrate_boost, email))

    conn.commit()
    cur.close()

    return jsonify({"message": f"Ad watched. Hashrate +{hashrate_boost} Th/s for {duration} sec."})

@app.route("/user/withdraw-now", methods=["POST"])
def withdraw_now():
    data = request.get_json()
    email = data.get("email")
    btc = float(data.get("btc", 0))
    wallet = data.get("wallet", "").strip()

    if not email or not btc or not wallet:
        return jsonify({"error": "Missing withdrawal information"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "User not found"}), 404

    mined = float(user.get("total_mined", 0))
    withdrawn = float(user.get("total_withdrawn", 0))

    if btc > mined:
        return jsonify({"error": "Insufficient BTC balance"}), 400

    new_mined = mined - btc
    new_withdrawn = withdrawn + btc

    # Update mined and withdrawn in DB
    update_user_balance(email, new_mined, new_withdrawn)

    # Save withdrawal record
    save_withdrawal(email=email, amount=btc, wallet=wallet, status="Pending")

    return jsonify({"message": "Withdrawal successful. BTC deducted."})

@app.post("/user/get-total-mined")
def get_total_mined():
    data = request.get_json()
    email = data.get("email")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT total_mined FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    conn.close()

    if row:
        return jsonify({"total_mined": row[0]})
    return jsonify({"total_mined": 0})

@app.post("/user/withdrawal-history")
def withdrawal_history():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT amount, wallet, status, requested_at
        FROM withdrawals
        WHERE email = %s
        ORDER BY requested_at DESC
    """, (email,))
    rows = cur.fetchall()
    conn.close()

    history = []
    for row in rows:
        history.append({
            "amount": row[0],
            "wallet": row[1],
            "status": row[2],
            "date": row[3].strftime("%Y-%m-%d %H:%M:%S")
        })

    return jsonify({"history": history})

@app.post("/user/get-profile")
def get_profile():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, country FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    conn.close()

    if row:
        return jsonify({
            "name": row[0],
            "country": row[1]
        })
    else:
        return jsonify({"error": "User not found"}), 404


# === RUN SERVER ===
if __name__ == "__main__":
    import pytz  # required for timezone logic in mining functions
    init_db()    # make sure all tables are created
    app.run(host="0.0.0.0", port=5000)
