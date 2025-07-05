import os
import smtplib
import random
import bcrypt
import psycopg2
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from flask import Flask, request, jsonify
from flask_cors import CORS

# === CONFIG ===
EMAIL_FROM = "adchainminer@gmail.com"
EMAIL_PASSWORD = "zfvn fves admc cgwr"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SITE_NAME = "Adchain Miner"
DATABASE_URL = os.getenv("DATABASE_URL")

app = Flask(__name__)
CORS(app)

# === DB SETUP ===
def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS users (
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );''')

    cur.execute('''CREATE TABLE IF NOT EXISTS admins (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );''')

    cur.execute('''CREATE TABLE IF NOT EXISTS otps (
        id SERIAL PRIMARY KEY,
        email TEXT,
        code TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        for_admin BOOLEAN DEFAULT FALSE
    );''')

    cur.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        amount NUMERIC,
        wallet TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );''')

    cur.execute('''CREATE TABLE IF NOT EXISTS system_settings (
        id SERIAL PRIMARY KEY,
        auto_withdraw_date DATE
    );''')

    cur.execute('''CREATE TABLE IF NOT EXISTS user_hash_sessions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        hash_amount INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );''')

    cur.execute('''CREATE TABLE IF NOT EXISTS mining_settings (
        hash_per_ad INTEGER,
        btc_per_hash NUMERIC
    );''')

    conn.commit()
    cur.close()
    conn.close()

# === UTILS ===
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

def strong_password(pw):
    import re
    return len(pw) >= 6 and re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"[0-9]", pw) and re.search(r"[^a-zA-Z0-9]", pw)

# === USER SIGNUP ===
@app.route("/user/signup", methods=["POST"])
def user_signup():
    data = request.json
    full_name = data.get("full_name")
    country = data.get("country")
    email = data.get("email")
    password = data.get("password")

    if not strong_password(password):
        return jsonify({"error": "Weak password. Use alphanumeric and symbol (min 6 chars)."}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    otp = generate_otp()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO otps (email, code) VALUES (%s, %s)", (email, otp))
    conn.commit()
    cur.close()
    conn.close()

    send_otp(email, otp)
    return jsonify({"message": "OTP sent to email."})

@app.route("/user/verify-otp", methods=["POST"])
def verify_otp():
    data = request.json
    email = data.get("email")
    otp_input = data.get("otp")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE email = %s ORDER BY id DESC LIMIT 1", (email,))
    row = cur.fetchone()
    if not row or row[0] != otp_input:
        return jsonify({"error": "Invalid OTP."}), 400

    return jsonify({"message": "OTP verified. Proceed to set PIN."})

@app.route("/user/create-account", methods=["POST"])
def create_account():
    data = request.json
    full_name = data.get("full_name")
    country = data.get("country")
    email = data.get("email")
    password = data.get("password")
    pin = data.get("pin")

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (full_name, country, email, password, pin, verified) VALUES (%s, %s, %s, %s, %s, TRUE)",
                (full_name, country, email, hashed, pin))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Account created successfully."})

# === USER LOGIN ===
@app.route("/user/login", methods=["POST"])
def user_login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and bcrypt.checkpw(password.encode(), user[0].encode()):
        return jsonify({"message": "Login successful."})
    return jsonify({"error": "Invalid credentials."}), 401

# === USER FORGOT PASSWORD & RESET PIN ===
@app.route("/user/forgot-password", methods=["POST"])
def forgot_password():
    data = request.json
    email = data.get("email")
    otp = generate_otp()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO otps (email, code) VALUES (%s, %s)", (email, otp))
    conn.commit()
    cur.close()
    conn.close()
    send_otp(email, otp)
    return jsonify({"message": "OTP sent to reset PIN."})

@app.route("/user/reset-pin", methods=["POST"])
def reset_pin():
    data = request.json
    email = data.get("email")
    otp_input = data.get("otp")
    new_pin = data.get("pin")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE email = %s ORDER BY id DESC LIMIT 1", (email,))
    row = cur.fetchone()
    if not row or row[0] != otp_input:
        return jsonify({"error": "Invalid OTP."}), 400

    cur.execute("UPDATE users SET pin = %s WHERE email = %s", (new_pin, email))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "PIN reset successfully."})

# === MINING ===
@app.route("/user/watch-ad", methods=["POST"])
def watch_ad():
    data = request.json
    email = data.get("email")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        return jsonify({"error": "User not found."}), 404

    user_id = user[0]
    cur.execute("SELECT hash_per_ad, btc_per_hash FROM mining_settings LIMIT 1")
    setting = cur.fetchone()
    if not setting:
        return jsonify({"error": "Mining not configured."}), 500

    hash_per_ad, btc_per_hash = setting
    cur.execute("INSERT INTO user_hash_sessions (user_id, hash_amount) VALUES (%s, %s)", (user_id, hash_per_ad))
    cur.execute("UPDATE users SET mined_btc = mined_btc + %s WHERE id = %s", (btc_per_hash * hash_per_ad, user_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Ad watched. Hash rate rewarded."})

@app.route("/user/hash-sessions", methods=["GET"])
def hash_sessions():
    email = request.args.get("email")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        return jsonify({"error": "User not found."}), 404
    user_id = user[0]

    cur.execute("SELECT hash_amount, timestamp FROM user_hash_sessions WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
    sessions = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{"hash": s[0], "timestamp": s[1].strftime("%Y-%m-%d %H:%M:%S")} for s in sessions])

# === ADMIN SIGNUP (OTP REQUIRED) ===
@app.route("/admin/request-otp", methods=["POST"])
def admin_request_otp():
    otp = generate_otp()
    cur_email = "adchainminer@gmail.com"  # central admin email
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO otps (email, code, for_admin) VALUES (%s, %s, TRUE)", (cur_email, otp))
    conn.commit()
    cur.close()
    conn.close()
    send_otp(cur_email, otp)
    return jsonify({"message": "OTP sent to central admin email."})

@app.route("/admin/signup", methods=["POST"])
def admin_signup():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    otp_input = data.get("otp")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE email = %s AND for_admin = TRUE ORDER BY id DESC LIMIT 1", ("adchainminer@gmail.com",))
    row = cur.fetchone()
    if not row or row[0] != otp_input:
        return jsonify({"error": "Invalid or missing OTP."}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    cur.execute("INSERT INTO admins (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Admin created successfully."})

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

# === ADMIN MINING SETTINGS ===
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
        return jsonify({"error": "User not found."}), 404
    user_id, mined = row
    if mined < amount:
        return jsonify({"error": "Insufficient balance."}), 400

    cur.execute("SELECT auto_withdraw_date FROM system_settings ORDER BY id DESC LIMIT 1")
    setting = cur.fetchone()
    today = datetime.now().date()
    status = 'approved' if setting and setting[0] == today else 'pending'

    cur.execute("INSERT INTO withdrawals (user_id, amount, wallet, status) VALUES (%s, %s, %s, %s)",
                (user_id, amount, wallet, status))
    cur.execute("UPDATE users SET withdrawn_btc = withdrawn_btc + %s, mined_btc = mined_btc - %s WHERE id = %s",
                (amount, amount, user_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": f"Withdrawal {status}."})

@app.route("/admin/pending-withdrawals", methods=["GET"])
def pending_withdrawals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT w.id, u.email, w.amount, w.wallet FROM withdrawals w JOIN users u ON w.user_id = u.id WHERE w.status = 'pending'")
    pending = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{"id": w[0], "email": w[1], "amount": float(w[2]), "wallet": w[3]} for w in pending])

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

@app.route("/admin/users", methods=["GET"])
def list_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT full_name, email, country, hash_rate, mined_btc, withdrawn_btc FROM users ORDER BY hash_rate DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "name": u[0], "email": u[1], "country": u[2],
        "hash_rate": u[3], "mined_btc": float(u[4]), "withdrawn_btc": float(u[5])
    } for u in users])

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

# === RUN ===
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
