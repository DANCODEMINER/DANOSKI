=== UPDATED FULL BACKEND START (Part 1 of 4) ===

import os import smtplib import random import bcrypt import psycopg2 from datetime import datetime, timedelta from email.mime.text import MIMEText from flask import Flask, request, jsonify from flask_cors import CORS from pytz import timezone, utc import pytz

=== CONFIG ===

EMAIL_FROM = "adchainminer@gmail.com" EMAIL_PASSWORD = "zfvn fves admc cgwr" SMTP_SERVER = "smtp.gmail.com" SMTP_PORT = 587 SITE_NAME = "Adchain Miner" DATABASE_URL = os.getenv("DATABASE_URL")

app = Flask(name) CORS(app)

=== DB SETUP ===

def get_db(): return psycopg2.connect(DATABASE_URL)

def init_db(): conn = get_db() cur = conn.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name TEXT,
    country TEXT,
    email TEXT UNIQUE,
    password TEXT,
    pin TEXT,
    timezone TEXT,
    hash_rate INTEGER DEFAULT 0,
    mined_btc NUMERIC DEFAULT 0,
    withdrawn_btc NUMERIC DEFAULT 0,
    wallet_address TEXT,
    verified BOOLEAN DEFAULT FALSE,
    suspended BOOLEAN DEFAULT FALSE,
    deleted BOOLEAN DEFAULT FALSE,
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
    fee NUMERIC DEFAULT 0,
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
    mined_btc NUMERIC,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);''')

cur.execute('''CREATE TABLE IF NOT EXISTS mining_settings (
    hash_per_ad INTEGER,
    btc_per_hash NUMERIC
);''')

cur.execute('''CREATE TABLE IF NOT EXISTS wallet_settings (
    withdraw_fee_btc NUMERIC DEFAULT 0
);''')

cur.execute('''CREATE TABLE IF NOT EXISTS central_wallet (
    id SERIAL PRIMARY KEY,
    btc_balance NUMERIC DEFAULT 0
);''')

conn.commit()
cur.close()
conn.close()

=== UTILS ===

def send_otp(email, code): subject = f"{SITE_NAME} OTP Verification" body = f"Your OTP code is: {code}" msg = MIMEText(body) msg['Subject'] = subject msg['From'] = EMAIL_FROM msg['To'] = email server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT) server.starttls() server.login(EMAIL_FROM, EMAIL_PASSWORD) server.send_message(msg) server.quit()

def generate_otp(): return str(random.randint(100000, 999999))

def strong_password(pw): import re return len(pw) >= 6 and re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"[0-9]", pw) and re.search(r"[^a-zA-Z0-9]", pw)

def convert_utc_to_local(utc_dt, tz_str): return utc.localize(utc_dt).astimezone(timezone(tz_str))

def get_all_timezones(): return pytz.all_timezones

def send_btc(from_wallet, to_wallet, amount): # TODO: integrate real blockchain wallet API return True

=== UPDATED FULL BACKEND START (Part 2 of 4) ===

=== USER SIGNUP WITH TIMEZONE DETECTION ===

@app.route("/user/timezones", methods=["GET"]) def get_timezones(): return jsonify(get_all_timezones())

@app.route("/user/signup", methods=["POST"]) def user_signup(): data = request.json full_name = data.get("full_name") country = data.get("country") email = data.get("email") password = data.get("password") tz = data.get("timezone")

if not strong_password(password):
    return jsonify({"error": "Weak password. Use alphanumeric and symbol (min 6 chars)."}), 400

conn = get_db()
cur = conn.cursor()
cur.execute("SELECT * FROM users WHERE email = %s", (email,))
if cur.fetchone():
    return jsonify({"error": "Email already exists."}), 400

otp = generate_otp()
cur.execute("INSERT INTO otps (email, code) VALUES (%s, %s)", (email, otp))
conn.commit()
cur.close()
conn.close()

send_otp(email, otp)
return jsonify({"message": "OTP sent to email."})

@app.route("/user/verify-otp", methods=["POST"]) def verify_otp(): data = request.json email = data.get("email") otp_input = data.get("otp")

conn = get_db()
cur = conn.cursor()
cur.execute("SELECT code FROM otps WHERE email = %s ORDER BY id DESC LIMIT 1", (email,))
row = cur.fetchone()
if not row or row[0] != otp_input:
    return jsonify({"error": "Invalid OTP."}), 400

return jsonify({"message": "OTP verified. Proceed to set PIN."})

@app.route("/user/create-account", methods=["POST"]) def create_account(): data = request.json full_name = data.get("full_name") country = data.get("country") email = data.get("email") password = data.get("password") pin1 = data.get("pin1") pin2 = data.get("pin2") tz = data.get("timezone")

if pin1 != pin2:
    return jsonify({"error": "PINs do not match."}), 400

hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
conn = get_db()
cur = conn.cursor()
cur.execute("INSERT INTO users (full_name, country, email, password, pin, timezone, verified) VALUES (%s, %s, %s, %s, %s, %s, TRUE)",
            (full_name, country, email, hashed, pin1, tz))
conn.commit()
cur.close()
conn.close()

return jsonify({"message": "Account created successfully."})

=== DAILY MINING LOG TRACKING ===

@app.route("/user/daily-mining", methods=["GET"]) def get_daily_mining(): email = request.args.get("email") conn = get_db() cur = conn.cursor() cur.execute("SELECT id, timezone FROM users WHERE email = %s", (email,)) row = cur.fetchone() if not row: return jsonify({"error": "User not found."}), 404 user_id, tz = row

cur.execute("SELECT timestamp, mined_btc FROM user_hash_sessions WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
records = cur.fetchall()
cur.close()
conn.close()

logs = {}
for ts, amount in records:
    local_day = convert_utc_to_local(ts, tz).strftime('%Y-%m-%d')
    logs[local_day] = logs.get(local_day, 0) + float(amount)

return jsonify([{"date": k, "total_mined": v} for k, v in sorted(logs.items(), reverse=True)])

=== WITHDRAWAL HISTORY ===

@app.route("/user/withdrawals", methods=["GET"]) def withdrawal_history(): email = request.args.get("email") conn = get_db() cur = conn.cursor() cur.execute("SELECT id FROM users WHERE email = %s", (email,)) row = cur.fetchone() if not row: return jsonify({"error": "User not found."}), 404 user_id = row[0]

cur.execute("SELECT amount, fee, status, created_at FROM withdrawals WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
rows = cur.fetchall()
cur.close()
conn.close()

return jsonify([{
    "amount": float(r[0]),
    "fee": float(r[1]),
    "status": r[2],
    "timestamp": r[3].strftime("%Y-%m-%d %H:%M:%S")
} for r in rows])

=== UPDATED FULL BACKEND START (Part 3 of 4) ===

=== ADMIN USER MANAGEMENT ===

@app.route("/admin/suspend-user", methods=["POST"]) def suspend_user(): data = request.json email = data.get("email") conn = get_db() cur = conn.cursor() cur.execute("UPDATE users SET suspended = TRUE WHERE email = %s", (email,)) conn.commit() cur.close() conn.close() return jsonify({"message": "User suspended."})

@app.route("/admin/restore-user", methods=["POST"]) def restore_user(): data = request.json email = data.get("email") conn = get_db() cur = conn.cursor() cur.execute("UPDATE users SET suspended = FALSE, deleted = FALSE WHERE email = %s", (email,)) conn.commit() cur.close() conn.close() return jsonify({"message": "User restored."})

@app.route("/admin/delete-user", methods=["POST"]) def delete_user(): data = request.json email = data.get("email") conn = get_db() cur = conn.cursor() cur.execute("UPDATE users SET deleted = TRUE WHERE email = %s", (email,)) conn.commit() cur.close() conn.close() return jsonify({"message": "User soft-deleted."})

=== WITHDRAWAL WITH MAX AND FEE ===

@app.route("/user/withdraw", methods=["POST"]) def withdraw(): data = request.json email = data.get("email") amount = data.get("amount")  # can be "MAX" wallet = data.get("wallet")

conn = get_db()
cur = conn.cursor()
cur.execute("SELECT id, mined_btc, timezone FROM users WHERE email = %s AND suspended = FALSE AND deleted = FALSE", (email,))
row = cur.fetchone()
if not row:
    return jsonify({"error": "User not found or suspended."}), 404
user_id, mined, tz = row

# get withdrawal fee (default 0)
cur.execute("SELECT withdraw_fee_btc FROM wallet_settings LIMIT 1")
fee_row = cur.fetchone()
fee = float(fee_row[0]) if fee_row else 0

if amount == "MAX":
    amount = float(mined)
else:
    amount = float(amount)

total_to_send = amount - fee
if total_to_send <= 0 or mined < amount:
    return jsonify({"error": "Invalid or insufficient balance."}), 400

# get central wallet balance
cur.execute("SELECT btc_balance FROM central_wallet LIMIT 1")
wallet_row = cur.fetchone()
central_balance = float(wallet_row[0]) if wallet_row else 0

# get today's date in user's timezone
user_now = datetime.now(pytz.timezone(tz))
today_local = user_now.date()

# get auto-withdraw date
cur.execute("SELECT auto_withdraw_date FROM system_settings ORDER BY id DESC LIMIT 1")
setting = cur.fetchone()
status = 'approved' if setting and setting[0] == today_local and central_balance >= amount else 'pending'

cur.execute("INSERT INTO withdrawals (user_id, amount, wallet, status, fee) VALUES (%s, %s, %s, %s, %s)",
            (user_id, amount, wallet, status, fee))
cur.execute("UPDATE users SET withdrawn_btc = withdrawn_btc + %s, mined_btc = mined_btc - %s WHERE id = %s",
            (amount, amount, user_id))
if status == 'approved':
    cur.execute("UPDATE central_wallet SET btc_balance = btc_balance - %s", (amount,))
conn.commit()
cur.close()
conn.close()

return jsonify({"message": f"Withdrawal {status}. Fee: {fee}"})

=== ADMIN SET WITHDRAW FEE ===

@app.route("/admin/set-withdraw-fee", methods=["POST"]) def set_withdraw_fee(): data = request.json fee = float(data.get("fee")) conn = get_db() cur = conn.cursor() cur.execute("DELETE FROM wallet_settings") cur.execute("INSERT INTO wallet_settings (withdraw_fee_btc) VALUES (%s)", (fee,)) conn.commit() cur.close() conn.close() return jsonify({"message": f"Fee updated to {fee} BTC"})

=== ADMIN UPDATE WALLET BALANCE ===

@app.route("/admin/update-central-wallet", methods=["POST"]) def update_wallet_balance(): data = request.json amount = float(data.get("amount")) conn = get_db() cur = conn.cursor() cur.execute("DELETE FROM central_wallet") cur.execute("INSERT INTO central_wallet (btc_balance) VALUES (%s)", (amount,)) conn.commit() cur.close() conn.close() return jsonify({"message": "Central wallet updated."})

=== FINAL BACKEND UPDATES (Part 4 of 4) ===

=== MINING SESSION TRACKING WITH 24HR EXPIRY ===

@app.route("/user/active-mining", methods=["GET"]) def active_mining(): email = request.args.get("email") conn = get_db() cur = conn.cursor() cur.execute("SELECT id, timezone FROM users WHERE email = %s", (email,)) user = cur.fetchone() if not user: return jsonify({"error": "User not found."}), 404 user_id, tz = user

cur.execute("SELECT hash_amount, timestamp FROM user_hash_sessions WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
now = datetime.now(pytz.timezone(tz))
active_sessions = []

for h, ts in cur.fetchall():
    local_ts = ts.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz))
    if now - local_ts < timedelta(hours=24):
        expire_in = str((local_ts + timedelta(hours=24)) - now)
        active_sessions.append({"hash": h, "started": local_ts.strftime("%Y-%m-%d %H:%M:%S"), "expires_in": expire_in})

cur.close()
conn.close()
return jsonify(active_sessions)

=== ENFORCE 24HR MINING LIMIT PER HASH ===

@app.route("/user/hash-total", methods=["GET"]) def hash_total(): email = request.args.get("email") conn = get_db() cur = conn.cursor() cur.execute("SELECT id, timezone FROM users WHERE email = %s", (email,)) row = cur.fetchone() if not row: return jsonify({"error": "User not found."}), 404 user_id, tz = row

cur.execute("SELECT hash_amount, timestamp FROM user_hash_sessions WHERE user_id = %s", (user_id,))
now = datetime.now(pytz.timezone(tz))
total_hash = 0

for h, ts in cur.fetchall():
    local_ts = ts.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz))
    if now - local_ts < timedelta(hours=24):
        total_hash += h

cur.close()
conn.close()
return jsonify({"active_hash": total_hash})

=== DATABASE SCHEMA FINALIZATION ===

Ensure the following is in init_db:

- users table has: timezone TEXT, suspended BOOLEAN DEFAULT FALSE, deleted BOOLEAN DEFAULT FALSE

- withdrawals table has: fee NUMERIC DEFAULT 0

- central_wallet table: btc_balance NUMERIC

- wallet_settings table: withdraw_fee_btc NUMERIC

=== UTILITIES ===

def get_all_timezones(): import pytz return pytz.all_timezones

def convert_utc_to_local(dt, timezone_str): import pytz utc = pytz.utc local_tz = pytz.timezone(timezone_str) return dt.replace(tzinfo=utc).astimezone(local_tz)

=== END OF FINAL PART ===

# === RUN SERVER ===
if __name__ == "__main__":
    import pytz
    init_db()
    app.run(host="0.0.0.0", port=5000)
