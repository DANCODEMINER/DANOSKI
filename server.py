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

# === USER SIGNUP ===





# === MINING / AD WATCHING ===

@app.route("/user/watch-ad", methods=["POST"])
def watch_ad():
    data = request.json
    email = data.get("email")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({"error": "User not found."}), 404

    user_id = user[0]
    
    log_user_action(user_id, "Watched ad")
    
    cur.execute("SELECT hash_per_ad, btc_per_hash FROM mining_settings LIMIT 1")
    setting = cur.fetchone()
    if not setting:
        cur.close()
        conn.close()
        return jsonify({"error": "Mining not configured."}), 500

    hash_per_ad, btc_per_hash = setting
    # Insert hash session
    cur.execute("INSERT INTO user_hash_sessions (user_id, hash_amount) VALUES (%s, %s)", (user_id, hash_per_ad))
    # Update mined btc balance
    cur.execute("UPDATE users SET mined_btc = mined_btc + %s WHERE id = %s", (btc_per_hash * hash_per_ad, user_id))
    conn.commit()
    cur.close()
    conn.close()

    # Placeholder: integrate with Ads Provider API here to send/display ads

    return jsonify({"message": "Ad watched. Hash rate rewarded."})

@app.route("/user/hash-sessions", methods=["GET"])
def hash_sessions():
    email = request.args.get("email")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, timezone FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({"error": "User not found."}), 404

    user_id, tz = user

    cur.execute("SELECT hash_amount, timestamp FROM user_hash_sessions WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
    sessions = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for hash_amount, ts in sessions:
        local_ts = ts.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz))
        result.append({
            "hash": hash_amount,
            "timestamp": local_ts.strftime("%Y-%m-%d %H:%M:%S")
        })

    return jsonify(result)

# === ADMIN OTP REQUEST ===
@app.route("/admin/request-otp", methods=["POST"])
def admin_request_otp():
    otp = generate_otp()
    central_admin_email = EMAIL_FROM  # "adchainminer@gmail.com"
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO otps (email, code, for_admin) VALUES (%s, %s, TRUE)", (central_admin_email, otp))
    conn.commit()
    cur.close()
    conn.close()
    send_otp(central_admin_email, otp)
    return jsonify({"message": "OTP sent to central admin email."})

# === ADMIN SIGNUP (with OTP verification) ===
@app.route("/admin/signup", methods=["POST"])
def admin_signup():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    otp_input = data.get("otp")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE email = %s AND for_admin = TRUE ORDER BY id DESC LIMIT 1", (EMAIL_FROM,))
    row = cur.fetchone()
    if not row or row[0] != otp_input:
        cur.close()
        conn.close()
        return jsonify({"error": "Invalid or missing OTP."}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    try:
        cur.execute("INSERT INTO admins (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"error": "Failed to create admin."}), 500

    cur.close()
    conn.close()
    return jsonify({"message": "Admin created successfully."})

# === ADMIN LOGIN ===
@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT password FROM admins WHERE username = %s", (username,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and bcrypt.checkpw(password.encode(), row[0].encode()):
        return jsonify({"message": "Admin login successful."})
    return jsonify({"error": "Invalid admin credentials."}), 401

# === ADMIN SET MINING SETTINGS ===
@app.route("/admin/set-mining-rate", methods=["POST"])
def set_mining_rate():
    data = request.json
    hash_per_ad = int(data.get("hash_per_ad"))
    btc_per_hash = float(data.get("btc_per_hash"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM mining_settings")
    cur.execute("INSERT INTO mining_settings (hash_per_ad, btc_per_hash) VALUES (%s, %s)", (hash_per_ad, btc_per_hash))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Mining rate updated."})

# === WITHDRAWALS ===

@app.route("/user/withdraw", methods=["POST"])
def withdraw():
    data = request.json
    email = data.get("email")
    amount = float(data.get("amount"))
    wallet = data.get("wallet")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, mined_btc FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "User not found."}), 404
    user_id, mined = row

    if mined < amount:
        cur.close()
        conn.close()
        return jsonify({"error": "Insufficient balance."}), 400

    cur.execute("SELECT auto_withdraw_date FROM system_settings ORDER BY id DESC LIMIT 1")
    setting = cur.fetchone()
    today = datetime.now().date()
    status = 'approved' if setting and setting[0] == today else 'pending'

    cur.execute("INSERT INTO withdrawals (user_id, amount, wallet, status) VALUES (%s, %s, %s, %s)",
                (user_id, amount, wallet, status))
    cur.execute("UPDATE users SET withdrawn_btc = withdrawn_btc + %s, mined_btc = mined_btc - %s WHERE id = %s",
                (amount, amount, user_id))

    # ✅ FIXED: Proper indentation here
    log_user_action(user_id, f"Requested withdrawal of {amount} BTC to {wallet}")

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": f"Withdrawal {status}."})
    

@app.route("/admin/pending-withdrawals", methods=["GET"])
def pending_withdrawals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT w.id, u.email, w.amount, w.wallet FROM withdrawals w JOIN users u ON w.user_id = u.id WHERE w.status = 'pending'")
    pending = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{"id": w[0], "email": w[1], "amount": float(w[2]), "wallet": w[3]} for w in pending])

# === ADMIN USER MANAGEMENT ===

@app.route("/admin/suspend-user", methods=["POST"])
def suspend_user():
    data = request.json
    email = data.get("email")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET suspended = TRUE WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": f"{email} suspended."})


@app.route("/admin/reactivate-user", methods=["POST"])
def reactivate_user():
    data = request.json
    email = data.get("email")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET suspended = FALSE WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": f"{email} reactivated."})


@app.route("/admin/delete-user", methods=["POST"])
def delete_user():
    data = request.json
    email = data.get("email")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET deleted = TRUE WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": f"{email} soft deleted."})


@app.route("/admin/restore-user", methods=["POST"])
def restore_user():
    data = request.json
    email = data.get("email")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET deleted = FALSE WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": f"{email} restored."})


@app.route("/admin/users-status", methods=["GET"])
def users_status():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT full_name, email, country, suspended, deleted FROM users")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "name": r[0],
            "email": r[1],
            "country": r[2],
            "status": "Suspended" if r[3] else "Deleted" if r[4] else "Active"
        } for r in rows
    ])

@app.route("/admin/user-logs", methods=["GET"])
def user_logs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.email, l.action, l.timestamp
        FROM user_logs l JOIN users u ON l.user_id = u.id
        ORDER BY l.timestamp DESC LIMIT 100
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([
        {"email": r[0], "action": r[1], "timestamp": r[2].strftime("%Y-%m-%d %H:%M:%S")}
        for r in rows
    ])

@app.route("/admin/approve-withdrawal/<int:wid>", methods=["POST"])
def approve_withdrawal(wid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status = 'approved' WHERE id = %s", (wid,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": f"Withdrawal {wid} approved."})

@app.route("/admin/reject-withdrawal/<int:wid>", methods=["POST"])
def reject_withdrawal(wid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status = 'rejected' WHERE id = %s", (wid,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": f"Withdrawal {wid} rejected."})

@app.route("/admin/approve-all-withdrawals", methods=["POST"])
def approve_all():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status = 'approved' WHERE status = 'pending'")
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "All pending withdrawals approved."})

@app.route("/admin/set-auto-withdraw-date", methods=["POST"])
def set_auto_withdraw():
    data = request.json
    date_str = data.get("date")
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM system_settings")
    cur.execute("INSERT INTO system_settings (auto_withdraw_date) VALUES (%s)", (date,))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Auto-withdraw date set."})

@app.route("/admin/remove-auto-withdraw-date", methods=["POST"])
def remove_auto_withdraw():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM system_settings")
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Auto-withdraw date removed."})

# === ADMIN USER LISTING ===
@app.route("/admin/users", methods=["GET"])
def list_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT full_name, email, country, hash_rate, mined_btc, withdrawn_btc FROM users ORDER BY hash_rate DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "name": u[0],
            "email": u[1],
            "country": u[2],
            "hash_rate": u[3],
            "mined_btc": float(u[4]),
            "withdrawn_btc": float(u[5])
        } for u in users
    ])

# === ADMIN EXPORT USERS CSV ===
@app.route("/admin/export-users", methods=["GET"])
def export_users():
    import csv
    from io import StringIO
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT full_name, country, email, hash_rate, mined_btc, withdrawn_btc FROM users")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Full Name", "Country", "Email", "Hash Rate", "Mined BTC", "Withdrawn BTC"])
    for row in rows:
        writer.writerow(row)

    return output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=users.csv'
    }

# === PLACEHOLDER FOR LIVE BITCOIN WALLET API INTEGRATION ===
# Example placeholder function
def live_wallet_api_placeholder():
    """
    This is a placeholder for the live Bitcoin wallet API integration.
    You can implement the actual API calls here later.
    """
    pass

# === PLACEHOLDER FOR ADS PROVIDER API INTEGRATION ===
# Example placeholder function
def ads_provider_api_placeholder():
    """
    This is a placeholder for the ads provider API integration.
    You can implement the actual API calls here later.
    """
    pass

from datetime import datetime, timedelta
import pytz

# === MINING SESSION TRACKING WITH 24HR EXPIRY ===
@app.route("/user/active-mining", methods=["GET"])
def active_mining():
    email = request.args.get("email")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, timezone FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({"error": "User not found."}), 404

    user_id, tz = user
    cur.execute("SELECT hash_amount, timestamp FROM user_hash_sessions WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
    now = datetime.now(pytz.timezone(tz))
    active_sessions = []

    for h, ts in cur.fetchall():
        local_ts = ts.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz))
        if now - local_ts < timedelta(hours=24):
            expire_in = str((local_ts + timedelta(hours=24)) - now)
            active_sessions.append({
                "hash": h,
                "started": local_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "expires_in": expire_in
            })

    cur.close()
    conn.close()
    return jsonify(active_sessions)

# === ENFORCE 24HR MINING LIMIT PER HASH ===
@app.route("/user/hash-total", methods=["GET"])
def hash_total():
    email = request.args.get("email")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, timezone FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "User not found."}), 404

    user_id, tz = row
    cur.execute("SELECT hash_amount, timestamp FROM user_hash_sessions WHERE user_id = %s", (user_id,))
    now = datetime.now(pytz.timezone(tz))
    total_hash = 0

    for h, ts in cur.fetchall():
        local_ts = ts.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz))
        if now - local_ts < timedelta(hours=24):
            total_hash += h

    cur.close()
    conn.close()

    # === PLACEHOLDER: Integrate Live Bitcoin Wallet API here if needed ===
    # e.g., update wallet balances, query wallet status, etc.

    return jsonify({"active_hash": total_hash})

# === PLACEHOLDER: Integrate Ad Supplier API ===
# For example, add a route or logic where users fetch or watch ads supplied by your ad provider.
# This placeholder reminds you where to add code for ad API calls.

# Example placeholder route:
@app.route("/ads/fetch", methods=["GET"])
def fetch_ads():
    # TODO: Integrate your ads provider API here to return ads for the user
    return jsonify({"message": "Ads API integration placeholder"})

from flask import send_from_directory

@app.route("/")
def home():
    return send_from_directory("static", "miner.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# === RUN SERVER ===
if __name__ == "__main__":
    import pytz  # required for timezone logic in mining functions
    init_db()    # make sure all tables are created
    app.run(host="0.0.0.0", port=5000)
