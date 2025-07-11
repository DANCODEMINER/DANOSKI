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

    # Admin-defined hashrate per ad
    hashrate_value = 100  # You can change this later to dynamic/admin-configurable

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
    cur.execute("SELECT title, content, created_at FROM messages ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()

    messages = [
        {
            "title": row[0],
            "content": row[1],
            "created_at": row[2].isoformat()
        }
        for row in rows
    ]

    return jsonify(messages)

@app.post("/admin/add-message")
def add_message():
    data = request.get_json()
    title = data.get("title")
    content = data.get("content")

    if not title or not content:
        return jsonify({"error": "Title and content are required."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (title, content) VALUES (%s, %s)", (title, content))
    conn.commit()
    conn.close()

    return jsonify({"message": "Announcement posted successfully."})

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

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))
        otp_store[username] = otp

        # Send OTP to central email
        msg = Message("Admin Signup OTP",
                      sender=EMAIL_FROM,
                      recipients=[EMAIL_FROM])
        msg.body = f"OTP for new admin '{username}': {otp}"
        mail.send(msg)

        return jsonify({"message": "OTP sent to admin email"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/admin/verify-otp")
def verify_admin_otp():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        otp = data.get("otp")

        if not username or not password or not otp:
            return jsonify({"error": "All fields are required"}), 400

        saved_otp = otp_store.get(username)
        if not saved_otp or otp != saved_otp:
            return jsonify({"error": "Invalid or expired OTP"}), 400

        # Check if username already exists
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM admins WHERE username = %s", (username,))
        if cur.fetchone():
            conn.close()
            return jsonify({"error": "Username already exists"}), 400

        # Create admin
        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        cur.execute("INSERT INTO admins (username, password) VALUES (%s, %s)", (username, hashed_pw))
        conn.commit()
        conn.close()

        del otp_store[username]  # Cleanup

        return jsonify({"message": "Admin account created successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === RUN SERVER ===
if __name__ == "__main__":
    import pytz  # required for timezone logic in mining functions
    init_db()    # make sure all tables are created
    app.run(host="0.0.0.0", port=5000)
