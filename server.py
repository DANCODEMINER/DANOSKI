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
from decimal import Decimal

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

    # USERS TABLE
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        full_name VARCHAR(100) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        country VARCHAR(100) NOT NULL,
        password TEXT NOT NULL,
        pin VARCHAR(4) NOT NULL,
        btc_balance NUMERIC(16, 8) DEFAULT 0.0,
        total_earned NUMERIC(16, 8) DEFAULT 0.0,
        last_mined TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        suspended BOOLEAN DEFAULT FALSE,
        deleted BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")

    # HASHRATES TABLE
    cur.execute("""
    DROP TABLE IF EXISTS hashrates;
    CREATE TABLE hashrates (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        hashrate INTEGER NOT NULL,
        created_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL
    );
    """)

    # WITHDRAWALS TABLE
    cur.execute("""
    DROP TABLE IF EXISTS withdrawals;
    CREATE TABLE withdrawals (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        amount NUMERIC(16, 8) NOT NULL,
        wallet TEXT NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # MESSAGES TABLE
    cur.execute("""
    DROP TABLE IF EXISTS messages;
    CREATE TABLE messages (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # ADMINS TABLE (OPTIONAL)
    cur.execute("""
    DROP TABLE IF EXISTS admins;
    CREATE TABLE admins (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password TEXT NOT NULL
    );
    """)

    # OTP TABLE
    cur.execute("""
    DROP TABLE IF EXISTS otps;
    CREATE TABLE otps (
        id SERIAL PRIMARY KEY,
        email VARCHAR(100) NOT NULL,
        code VARCHAR(6) NOT NULL,
        purpose VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()   
    
            

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
            INSERT INTO users (full_name, country, email, password, pin)
            VALUES (%s, %s, %s, %s, %s)
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

@app.route("/user/signup", methods=["POST"])
def user_signup():
    data = request.json
    name = data.get("full_name")  # Changed from full_name
    country = data.get("country")
    email = data.get("email")
    password = data.get("password")

    if not strong_password(password):
        return jsonify({"error": "Weak password. Use alphanumeric and symbol (min 6 chars)."}), 400

    # Check if email already exists
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "Email already registered."}), 400

    otp = generate_otp()

    # Save OTP for this email
    cur.execute("INSERT INTO otps (email, code) VALUES (%s, %s)", (email, otp))
    conn.commit()
    cur.close()
    conn.close()

    # Send OTP email
    send_otp(email, otp)
    return jsonify({"message": "OTP sent to email."})

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
@app.post("/user/claim-hashrate")
def claim_hashrate():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db()
    cur = conn.cursor()

    # Get user ID
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    user_id = result[0]

    # ✅ Fetch admin-defined hashrate from settings table
    cur.execute("SELECT value FROM settings WHERE key = 'hashrate_per_ad'")
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Hashrate setting not found"}), 500

    hashrate_value = int(row[0])

    now = datetime.utcnow()
    expires_at = now + timedelta(hours=24)

    # Insert hashrate entry
    cur.execute("""
        INSERT INTO hashrates (user_id, hashrate, created_at, expires_at)
        VALUES (%s, %s, %s, %s)
    """, (user_id, hashrate_value, now, expires_at))

    conn.commit()
    conn.close()

    return jsonify({
        "message": f"{hashrate_value} H/s granted for 24 hours.",
        "hashrate": hashrate_value,
        "expires_at": expires_at.isoformat()
    }), 200

@app.get("/user/dashboard")
def user_dashboard():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db()
    cur = conn.cursor()

    # Get user data
    cur.execute("SELECT id, btc_balance, total_earned, last_mined FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    user_id, btc_balance, total_earned, last_mined = row

    # Get total active hashrate
    now = datetime.utcnow()
    cur.execute("""
        SELECT COALESCE(SUM(hashrate), 0) FROM hashrates
        WHERE user_id = %s AND expires_at > %s
    """, (user_id, now))
    hashrate = cur.fetchone()[0]

    conn.close()

    return jsonify({
        "btc_balance": float(btc_balance),
        "total_earned": float(total_earned),
        "hashrate": hashrate,
        "last_mined": last_mined.isoformat()
    }), 200

@app.post("/user/mine-sync")
def mine_sync():
    try:
        data = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({"error": "Email is required"}), 400

        conn = get_db()
        cur = conn.cursor()

        # Get user info
        cur.execute("SELECT id, btc_balance, total_earned, last_mined FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "User not found"}), 404

        user_id, btc_balance, total_earned, last_mined = user
        now = datetime.utcnow()
        seconds_elapsed = Decimal(str((now - last_mined).total_seconds()))

        # Get active hashrate
        cur.execute("""
            SELECT COALESCE(SUM(hashrate), 0) FROM hashrates
            WHERE user_id = %s AND expires_at > %s
        """, (user_id, now))
        hashrate = cur.fetchone()[0]

        # Mining formula: BTC = hashrate * seconds * factor
        mining_factor = Decimal("0.00000001")
        mined_btc = Decimal(str(hashrate)) * seconds_elapsed * mining_factor

        new_balance = btc_balance + mined_btc
        new_total = total_earned + mined_btc

        cur.execute("""
            UPDATE users
            SET btc_balance = %s, total_earned = %s, last_mined = %s
            WHERE id = %s
        """, (new_balance, new_total, now, user_id))

        conn.commit()
        conn.close()

        return jsonify({
            "mined_btc": float(round(mined_btc, 8)),
            "new_balance": float(round(new_balance, 8)),
            "hashrate": hashrate
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.post("/user/withdraw")
def user_withdraw():
    try:
        data = request.get_json()
        email = data.get("email")
        amount = Decimal(str(data.get("amount", 0)))
        wallet = data.get("wallet")

        if not email or not wallet or amount <= 0:
            return jsonify({"error": "All fields are required."}), 400

        conn = get_db()
        cur = conn.cursor()

        # Get user and balance
        cur.execute("SELECT id, btc_balance FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "User not found"}), 404

        user_id, balance = row

        if amount > balance:
            conn.close()
            return jsonify({"error": "Insufficient balance."}), 400

        # Deduct balance and insert withdrawal record
        new_balance = balance - amount

        cur.execute("UPDATE users SET btc_balance = %s WHERE id = %s", (new_balance, user_id))
        cur.execute("""
            INSERT INTO withdrawals (user_id, amount, wallet, status, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, amount, wallet, 'pending', datetime.utcnow()))

        conn.commit()
        conn.close()

        return jsonify({"message": "Withdrawal request submitted.", "new_balance": float(new_balance)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.get("/user/messages")
def get_messages():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT title, content, created_at FROM messages ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({})  # No announcement available

    return jsonify({
        "title": row[0],
        "content": row[1],
        "created_at": row[2].isoformat()
    })

@app.get("/user/hashrates")
def get_active_hashrates():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db()
    cur = conn.cursor()

    # Get user ID
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    user_id = result[0]

    # DELETE expired hashrates for this user
    cur.execute("DELETE FROM hashrates WHERE user_id = %s AND expires_at <= NOW()", (user_id,))

    # Get all non-expired hashrates
    cur.execute("""
        SELECT hashrate, expires_at
        FROM hashrates
        WHERE user_id = %s
        ORDER BY expires_at
    """, (user_id,))

    rows = cur.fetchall()
    conn.commit()
    conn.close()

    hashrates = [{
        "hashrate": r[0],
        "expires_at": r[1].isoformat()
    } for r in rows]

    return jsonify(hashrates)

@app.post("/user/update-btc")
def update_btc_balance():
    data = request.get_json()
    email = data.get("email")
    btc_balance = data.get("btc_balance")

    if not email or btc_balance is None:
        return jsonify({"error": "Missing fields"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET btc_balance = %s
        WHERE email = %s
    """, (btc_balance, email))
    conn.commit()
    conn.close()

    return jsonify({"message": "Balance updated."})

@app.get("/user/get-balance")
def get_user_balance():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT btc_balance FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    conn.close()

    if row:
        return jsonify({"btc_balance": float(row[0])})
    else:
        return jsonify({"error": "User not found"}), 404

@app.get("/user/withdrawals")
def get_withdrawals():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    user_id = result[0]

    cur.execute("""
        SELECT amount, wallet, status, created_at
        FROM withdrawals
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    withdrawals = [{
        "amount": float(r[0]),
        "wallet": r[1],
        "status": r[2],
        "created_at": r[3].isoformat()
    } for r in rows]

    return jsonify(withdrawals), 200

@app.post("/admin/send-otp")
def send_admin_otp():
    try:
        data = request.get_json()
        username = data.get("username")

        if not username:
            return jsonify({"error": "Username is required"}), 400

        otp = generate_otp()

        # Save OTP in your DB (same as your user route)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO otps (email, code)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET code = EXCLUDED.code, created_at = CURRENT_TIMESTAMP
        """, (username, otp))
        conn.commit()
        cur.close()
        conn.close()

        # Send OTP email to central admin email (your EMAIL_FROM)
        send_otp(EMAIL_FROM, otp)

        return jsonify({"message": "OTP sent to admin email"}), 200

    except Exception as e:
        print("Admin OTP error:", e)
        return jsonify({"error": "Failed to send OTP."}), 500
        
@app.post("/admin/verify-otp")
def verify_admin_otp():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        otp = data.get("otp")

        if not username or not password or not otp:
            return jsonify({"error": "All fields are required"}), 400

        conn = get_db()
        cur = conn.cursor()

        # Fetch saved OTP from DB
        cur.execute("SELECT code, created_at FROM otps WHERE email = %s", (username,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "OTP not found or expired"}), 400

        saved_otp, created_at = row

        # Optional: check OTP expiration (e.g., 5 minutes)
        if datetime.utcnow() - created_at > timedelta(minutes=5):
            conn.close()
            return jsonify({"error": "OTP expired"}), 400

        if otp != saved_otp:
            conn.close()
            return jsonify({"error": "Invalid OTP"}), 400

        # Check if username already exists
        cur.execute("SELECT id FROM admins WHERE username = %s", (username,))
        if cur.fetchone():
            conn.close()
            return jsonify({"error": "Username already exists"}), 400

        # Create admin user with hashed password
        hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("utf-8")
        cur.execute("INSERT INTO admins (username, password) VALUES (%s, %s)", (username, hashed_pw))
        conn.commit()

        # Delete used OTP from DB
        cur.execute("DELETE FROM otps WHERE email = %s", (username,))
        conn.commit()

        cur.close()
        conn.close()

        return jsonify({"message": "Admin account created successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/admin/login")
def admin_login():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT password FROM admins WHERE username = %s", (username,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "Admin not found"}), 404

        stored_hash = row[0]
        if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
            return jsonify({"error": "Incorrect password"}), 401

        return jsonify({"message": "Login successful"}), 200

    except Exception as e:
        print("Login error:", e)
        return jsonify({"error": "Internal server error"}), 500

@app.post("/admin/send-reset-otp")
def send_reset_otp():
    try:
        data = request.get_json()
        username = data.get("username")

        if not username:
            return jsonify({"error": "Username is required"}), 400

        # Generate OTP
        otp = generate_otp()

        # Store OTP in otps table
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO otps (email, code)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET code = EXCLUDED.code, created_at = CURRENT_TIMESTAMP
        """, (username, otp))
        conn.commit()
        cur.close()
        conn.close()

        # Send OTP to admin email
        send_otp(EMAIL_FROM, otp)

        return jsonify({"message": "OTP sent to admin email"}), 200

    except Exception as e:
        print("Reset OTP error:", e)
        return jsonify({"error": "Failed to send reset OTP"}), 500

@app.post("/admin/verify-reset-otp")
def verify_reset_otp():
    try:
        data = request.get_json()
        username = data.get("username")
        otp = data.get("otp")

        if not username or not otp:
            return jsonify({"error": "Username and OTP are required"}), 400

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT code, created_at FROM otps WHERE email = %s", (username,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "OTP not found"}), 400

        saved_otp, created_at = row
        if otp != saved_otp:
            conn.close()
            return jsonify({"error": "Invalid OTP"}), 400

        # Check if OTP expired (optional)
        if datetime.utcnow() - created_at > timedelta(minutes=10):
            conn.close()
            return jsonify({"error": "OTP expired"}), 400

        conn.close()
        return jsonify({"message": "OTP verified"}), 200

    except Exception as e:
        print("OTP verify error:", e)
        return jsonify({"error": "OTP verification failed"}), 500

@app.post("/admin/update-password")
def update_admin_password():
    try:
        data = request.get_json()
        username = data.get("username")
        new_password = data.get("new_password")

        if not username or not new_password:
            return jsonify({"error": "Username and new password required"}), 400

        hashed_pw = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode("utf-8")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE admins SET password = %s WHERE username = %s", (hashed_pw, username))

        # Clean up OTP after successful reset
        cur.execute("DELETE FROM otps WHERE email = %s", (username,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Password updated successfully"}), 200

    except Exception as e:
        print("Password update error:", e)
        return jsonify({"error": "Failed to update password"}), 500

@app.get("/admin/users")
def get_all_users():
    try:
        conn = get_db()
        cur = conn.cursor()

        # Query to fetch user details
        cur.execute("""
            SELECT id, email, btc_balance, total_earned, hashrate, last_mined
            FROM users
        """)
        users = cur.fetchall()
        conn.close()

        # Return users as JSON
        return jsonify([{
            "id": user[0],
            "email": user[1],
            "btc_balance": float(user[2]),
            "total_earned": float(user[3]),
            "hashrate": user[4],
            "last_mined": user[5].isoformat() if user[5] else None
        } for user in users])

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/admin/withdrawals")
def admin_get_withdrawals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.email, w.amount, w.wallet, w.status, w.created_at
        FROM withdrawals w
        JOIN users u ON w.user_id = u.id
        ORDER BY w.created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    result = [
        {
            "email": row[0],
            "amount": float(row[1]),
            "wallet": row[2],
            "status": row[3],
            "created_at": row[4].isoformat()
        }
        for row in rows
    ]
    return jsonify(result)

@app.get("/admin/withdrawals")
def view_withdrawals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT w.id, u.email, w.amount, w.wallet, w.status, w.created_at
        FROM withdrawals w
        JOIN users u ON w.user_id = u.id
        ORDER BY w.created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    withdrawals = [{
        "id": row[0],
        "email": row[1],
        "amount": float(row[2]),
        "wallet": row[3],
        "status": row[4],
        "created_at": row[5].isoformat()
    } for row in rows]

    return jsonify(withdrawals)

@app.post("/admin/update-withdrawal")
def update_withdrawal():
    data = request.get_json()
    withdrawal_id = data.get("id")
    status = data.get("status")

    if status not in ["approved", "rejected"]:
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status = %s WHERE id = %s", (status, withdrawal_id))
    conn.commit()
    conn.close()

    return jsonify({"message": f"Withdrawal {status}."})

@app.post("/admin/add-message")
def add_message():
    data = request.get_json()
    title = data.get("title")
    content = data.get("content")

    if not title or not content:
        return jsonify({"error": "Title and content are required."}), 400

    conn = get_db()
    cur = conn.cursor()

    # Clear existing message (so only one is always present)
    cur.execute("DELETE FROM messages")

    # Insert new message
    cur.execute("INSERT INTO messages (title, content, created_at) VALUES (%s, %s, %s)",
                (title, content, datetime.utcnow()))

    conn.commit()
    conn.close()

    return jsonify({"message": "Announcement posted successfully."})

@app.delete("/admin/delete-message")
def delete_message():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM messages")
    conn.commit()
    conn.close()

    return jsonify({"message": "Announcement deleted successfully."})

@app.post("/admin/set-hashrate")
def set_hashrate():
    try:
        data = request.get_json()
        value = int(data.get("value"))

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO settings (key, value)
            VALUES ('hashrate_per_ad', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (value,))

        conn.commit()
        conn.close()

        return jsonify({"message": f"Hashrate per ad updated to {value} H/s."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/admin/get-hashrate")
def get_hashrate():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = 'hashrate'")
    row = cur.fetchone()
    conn.close()

    if row:
        return jsonify({"hashrate": int(row[0])})
    else:
        return jsonify({"hashrate": 100})  # default fallback

# === RUN SERVER ===
if __name__ == "__main__":
    import pytz  # required for timezone logic in mining functions
    init_db()    # make sure all tables are created
    app.run(host="0.0.0.0", port=5000)
