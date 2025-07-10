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
@app.route('/mine', methods=['POST'])
def mine_bitcoin():
    data = request.get_json()
    email = data.get('email')

    # 1. Validate user exists
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    user_id = user[0]

    # 2. Get admin mining config
    cur.execute("SELECT btc_per_hashrate, hashrate_per_ad FROM admin_config LIMIT 1")
    config = cur.fetchone()
    if not config:
        return jsonify({"error": "Mining config missing"}), 500

    btc_per_hashrate = config[0]
    hashrate_awarded = config[1]

    # 3. Calculate BTC earned
    btc_earned = btc_per_hashrate * hashrate_awarded

    # 4. Update total_mined
    cur.execute("UPDATE users SET total_mined = total_mined + %s WHERE id = %s", (btc_earned, user_id))

    # 5. Record session
    cur.execute("""
        INSERT INTO mining_sessions (user_id, hashrate, btc_earned)
        VALUES (%s, %s, %s)
    """, (user_id, hashrate_awarded, btc_earned))

    # 6. Get updated total mined
    cur.execute("SELECT total_mined FROM users WHERE id = %s", (user_id,))
    updated = cur.fetchone()

    conn.commit()

    return jsonify({
        "btc_earned": float(btc_earned),
        "hashrate": float(hashrate_awarded),
        "total_mined": float(updated[0])
    })

@app.route('/dashboard-stats', methods=['POST'])
def dashboard_stats():
    data = request.get_json()
    email = data.get('email')

    # Validate user
    cur.execute("SELECT total_mined FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Total mined
    total_mined = float(user[0])

    # Sum of hashrate
    cur.execute("SELECT COALESCE(SUM(hashrate), 0) FROM mining_sessions WHERE email = %s", (email,))
    total_hashrate = float(cur.fetchone()[0])

    # Count of sessions
    cur.execute("SELECT COUNT(*) FROM mining_sessions WHERE email = %s", (email,))
    active_sessions = cur.fetchone()[0]

    return jsonify({
        "total_mined": total_mined,
        "total_hashrate": total_hashrate,
        "active_sessions": active_sessions
    })

@app.route('/hash-sessions', methods=['POST'])
def get_hash_sessions():
    data = request.get_json()
    email = data.get('email')

    cur.execute("""
        SELECT id, created_at, hashrate, duration 
        FROM mining_sessions 
        WHERE email = %s 
        ORDER BY created_at DESC 
        LIMIT 10
    """, (email,))
    
    sessions = cur.fetchall()
    result = []
    for row in sessions:
        result.append({
            "id": row[0],
            "date": row[1].strftime("%Y-%m-%d %H:%M"),
            "power": f"{row[2]:.2f} Th/s",
            "duration": row[3] or "30 sec"
        })
    
    return jsonify(result)

@app.route('/userleaderboard', methods=['POST'])
def leaderboard():
    data = request.get_json()
    email = data.get('email')

    # Fetch Top 10 Miners
    cur.execute("""
        SELECT username, total_mined, country 
        FROM users 
        ORDER BY total_mined DESC 
        LIMIT 10
    """)
    top_rows = cur.fetchall()
    top_miners = []
    for idx, row in enumerate(top_rows, 1):
        top_miners.append({
            "rank": idx,
            "username": row[0],
            "btc": float(row[1]),
            "country": row[2]
        })

    # Fetch user's rank
    cur.execute("""
        SELECT email, total_mined 
        FROM users 
        ORDER BY total_mined DESC
    """)
    all_users = cur.fetchall()
    
    user_rank = next((i + 1 for i, u in enumerate(all_users) if u[0] == email), None)
    user_btc = next((u[1] for u in all_users if u[0] == email), 0)

    # Optional: get username too
    cur.execute("SELECT username FROM users WHERE email = %s", (email,))
    username = cur.fetchone()[0]

    return jsonify({
        "top_miners": top_miners,
        "my_rank": user_rank,
        "my_btc": float(user_btc),
        "my_username": username
    })

@app.route('/user-info', methods=['POST'])
def user_info():
    data = request.get_json()
    email = data.get('email')

    cur.execute("SELECT username, country FROM users WHERE email = %s", (email,))
    result = cur.fetchone()

    if not result:
        return jsonify({"error": "User not found"}), 404

    username, country = result

    # Optional: extract first name from username if needed
    first_name = username.split()[0] if ' ' in username else username

    # Generate flag image URL using country name
    country_flag = f"https://flagsapi.com/{country}/flat/64.png"

    return jsonify({
        "username": username,
        "first_name": first_name,
        "country": country,
        "flag_url": country_flag
    })

@app.route('/hash-sessions', methods=['POST'])
def get_hash_sessions():
    data = request.get_json()
    email = data.get('email')

    cur.execute("""
        SELECT id, created_at, hashrate, duration 
        FROM mining_sessions 
        WHERE email = %s 
        ORDER BY created_at DESC 
        LIMIT 10
    """, (email,))
    
    sessions = cur.fetchall()

    session_list = []
    for session in sessions:
        session_list.append({
            "id": session[0],
            "date": session[1].strftime("%Y-%m-%d %H:%M"),
            "hashrate": session[2],
            "duration": session[3] if session[3] else "N/A"
        })

    return jsonify(session_list)

@app.route('/leaderboard', methods=['POST'])
def get_leaderboard():
    data = request.get_json()
    email = data.get('email')

    # Top 10 miners in the past 30 days
    cur.execute("""
        SELECT email, SUM(btc_earned) AS total_btc, SUM(hashrate) AS total_hashrate
        FROM mining_sessions
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY email
        ORDER BY total_btc DESC
        LIMIT 10
    """)
    top_miners = cur.fetchall()

    leaderboard = []
    for i, miner in enumerate(top_miners, start=1):
        leaderboard.append({
            "rank": i,
            "email": miner[0],
            "btc": float(miner[1]),
            "hashrate": float(miner[2])
        })

    # Get current user's rank
    cur.execute("""
        SELECT email, SUM(btc_earned) AS total_btc
        FROM mining_sessions
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY email
        ORDER BY total_btc DESC
    """)
    all_ranks = cur.fetchall()

    my_rank = "--"
    my_btc = 0.0
    for i, user in enumerate(all_ranks, start=1):
        if user[0] == email:
            my_rank = i
            my_btc = float(user[1])
            break

    # Get hashrate
    cur.execute("""
        SELECT SUM(hashrate) FROM mining_sessions
        WHERE email = %s AND created_at >= NOW() - INTERVAL '30 days'
    """, (email,))
    result = cur.fetchone()
    my_hashrate = float(result[0]) if result[0] else 0.0

    return jsonify({
        "top_miners": leaderboard,
        "my_rank": my_rank,
        "my_btc": my_btc,
        "my_hashrate": my_hashrate
    })

@app.route('/profile', methods=['POST'])
def get_profile():
    data = request.get_json()
    email = data.get('email')

    cur.execute("SELECT username, email, country, join_date FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "name": user[0],
        "email": user[1],
        "country": user[2],
        "join_date": user[3].strftime("%B %d, %Y") if user[3] else "N/A"
    })


# === RUN SERVER ===
if __name__ == "__main__":
    import pytz  # required for timezone logic in mining functions
    init_db()    # make sure all tables are created
    app.run(host="0.0.0.0", port=5000)
