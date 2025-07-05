import http.server
import socketserver
import json
import time
import threading
import random
import os
import bcrypt
from datetime import datetime, timedelta
from email.message import EmailMessage
import smtplib
import psycopg2
from psycopg2.extras import RealDictCursor

# === Server Configuration ===
PORT = int(os.environ.get("PORT", 8000))
ROTATION_INTERVAL = 120
VISIBLE_COUNT = 10
SESSION_TIMEOUT = 3600

signup_otp_cache = {}

# === Email Config ===
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = "teamhackerjustice@gmail.com"
EMAIL_PASSWORD = "caya metk oabw ehon"

# === DB Connection ===
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable is not set.")
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
conn.autocommit = True

# === Globals ===
testimonies = []
visible_testimonies = []
rotation_index = 0
used_indexes = set()
sessions = {}
reset_codes = {}
RESET_CODE_EXPIRY = 600

STYLES = ["bold", "italic", "highlight", "shadowed", "glass", "neon"]
ANIMATIONS = ["fade-in", "slide-left", "slide-right", "zoom-in", "pop-up", "rotate"]

# === Database Setup ===
def setup_tables():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS testimonies (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                country TEXT,
                flag TEXT,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_testimonies (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                country TEXT,
                flag TEXT,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

# === Admin Functions ===
def load_admin_user(username):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM admin_users WHERE username = %s", (username,))
        return cur.fetchone()

def create_admin_user(username, password):
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    with conn.cursor() as cur:
        cur.execute("INSERT INTO admin_users (username, password) VALUES (%s, %s)", (username, hashed_pw))

def verify_password(stored_hash, password):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except Exception:
        return False

def generate_reset_code():
    return str(random.randint(100000, 999999))

def save_reset_code(username, code):
    reset_codes[username] = {
        "code": code,
        "expires": datetime.utcnow() + timedelta(seconds=RESET_CODE_EXPIRY)
    }

def send_reset_email(username, code):
    try:
        msg = EmailMessage()
        msg['Subject'] = "Hacker Justice Password Reset Code"
        msg['From'] = EMAIL_FROM
        msg['To'] = username  # Treat username as email
        msg.set_content(f"""
Hello,

Your password reset code is: {code}

If you did not request this, ignore this message.
""")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send reset email: {e}")
        return False

def verify_reset_code(username, code):
    entry = reset_codes.get(username)
    if not entry:
        return False
    if entry["expires"] < datetime.utcnow():
        del reset_codes[username]
        return False
    if entry["code"] == code:
        del reset_codes[username]
        return True
    return False

# === Testimonies ===
def load_all_testimonies():
    global testimonies
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT name, country, flag, message FROM testimonies ORDER BY created_at ASC")
        rows = cur.fetchall()
        testimonies.clear()
        for t in rows:
            testimonies.append({
                "name": t["name"],
                "country": t["country"] or "Unknown",
                "flag": t["flag"] or "",
                "message": t["message"],
                "style": random.choice(STYLES),
                "animation": random.choice(ANIMATIONS),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })

def add_pending_testimony(data):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pending_testimonies (name, country, flag, message)
            VALUES (%s, %s, %s, %s)
        """, (data.get("name"), data.get("country"), data.get("flag"), data.get("message")))

def get_pending_testimonies():
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name, country, flag, message FROM pending_testimonies ORDER BY created_at ASC")
        return cur.fetchall()

def delete_pending_testimony(testimony_id):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pending_testimonies WHERE id = %s", (testimony_id,))

def approve_testimony(testimony_id):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM pending_testimonies WHERE id = %s", (testimony_id,))
        t = cur.fetchone()
        if not t:
            return False
        cur.execute("""
            INSERT INTO testimonies (name, country, flag, message)
            VALUES (%s, %s, %s, %s)
        """, (t["name"], t["country"], t["flag"], t["message"]))
        cur.execute("DELETE FROM pending_testimonies WHERE id = %s", (testimony_id,))
        return True

# === Session Functions ===
def create_session(username):
    token = os.urandom(32).hex()
    sessions[token] = {
        "username": username,
        "expires": datetime.utcnow() + timedelta(seconds=SESSION_TIMEOUT)
    }
    return token

def validate_session(token):
    s = sessions.get(token)
    if not s:
        return False
    if s["expires"] < datetime.utcnow():
        del sessions[token]
        return False
    s["expires"] = datetime.utcnow() + timedelta(seconds=SESSION_TIMEOUT)
    return True

def get_username_from_session(token):
    s = sessions.get(token)
    return s["username"] if s else None

# === Rotation Thread ===
def update_visible_testimonies():
    global visible_testimonies, rotation_index, used_indexes
    n = len(testimonies)
    if n == 0:
        visible_testimonies = []
        return
    if len(used_indexes) >= n:
        used_indexes.clear()
        rotation_index = 0
    visible_testimonies = []
    added = 0
    i = rotation_index
    while added < VISIBLE_COUNT and len(used_indexes) < n:
        idx = i % n
        if idx not in used_indexes:
            t = testimonies[idx].copy()
            t["style"] = random.choice(STYLES)
            t["animation"] = random.choice(ANIMATIONS)
            t["timestamp"] = datetime.utcnow().isoformat() + "Z"
            visible_testimonies.append(t)
            used_indexes.add(idx)
            added += 1
        i += 1
    rotation_index = i % n

def rotate_testimonies():
    while True:
        update_visible_testimonies()
        time.sleep(ROTATION_INTERVAL)

def send_email(to, subject, body):
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = to
        msg.set_content(body)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False

# === HTTP Handler ===
class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Cookie')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def parse_cookies(self):
        cookie_header = self.headers.get('Cookie')
        cookies = {}
        if cookie_header:
            items = cookie_header.split(';')
            for item in items:
                if '=' in item:
                    key, value = item.strip().split('=', 1)
                    cookies[key] = value
        return cookies

    def require_auth(self):
        cookies = self.parse_cookies()
        token = cookies.get("session_token")
        if token and validate_session(token):
            return True
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "error", "reason": "Unauthorized"}).encode('utf-8'))
        return False

    def list_directory(self, path):
        self.send_response(403)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"403 Forbidden: Directory listing is disabled.")
        return None

    def do_GET(self):
        if self.path == '/testimonies.json':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(visible_testimonies, indent=2).encode('utf-8'))

        elif self.path == '/testimonies/full.json':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(testimonies, indent=2).encode('utf-8'))

        elif self.path == '/admin/pending_testimonies':
            if not self.require_auth():
                return
            pending = get_pending_testimonies()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(pending, indent=2).encode('utf-8'))

        else:
            super().do_GET()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        if self.path == '/submit_testimony':
            try:
                data = json.loads(post_data.decode('utf-8'))
                add_pending_testimony(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode('utf-8'))

        elif self.path == '/admin/request_signup_otp':
            try:
                data = json.loads(post_data.decode('utf-8'))
                username = data.get("username")
                password = data.get("password")

                if not username or not password:
                    raise ValueError("Username and password are required")

                if load_admin_user(username):
                    raise ValueError("Admin already exists")

                code = f"{random.randint(100000, 999999)}"
                signup_otp_cache[username] = {
                    "code": code,
                    "password": password,
                    "expires": time.time() + 600  # 10 minutes
                }

                send_email(
                    to=EMAIL_FROM,
                    subject="Hacker Justice - Admin Signup OTP",
                    body=f"New admin signup request:\n\nUsername: {username}\nOTP Code: {code}\n\nThis code expires in 10 minutes."
                )

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode('utf-8'))

        elif self.path == '/admin/verify_signup_otp':
            try:
                data = json.loads(post_data.decode('utf-8'))
                username = data.get("username")
                code = data.get("code")

                otp_data = signup_otp_cache.get(username)

                if not otp_data:
                    raise ValueError("No OTP request found for this username")

                if time.time() > otp_data["expires"]:
                    del signup_otp_cache[username]
                    raise ValueError("OTP expired")

                if otp_data["code"] != code:
                    raise ValueError("Invalid OTP")

                create_admin_user(username, otp_data["password"])
                del signup_otp_cache[username]

                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode('utf-8'))

        elif self.path == '/admin/login':
            try:
                data = json.loads(post_data.decode('utf-8'))
                username = data.get("username")
                password = data.get("password")
                if not username or not password:
                    raise ValueError("Username and password required")

                user = load_admin_user(username)
                if user and verify_password(user['password'], password):
                    token = create_session(username)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")

                    # ✅ Safe Set-Cookie for both HTTP and HTTPS
                    cookie = f"session_token={token}; Path=/; HttpOnly; SameSite=None"
                    origin = self.headers.get("Origin", "")
                    if origin.startswith("https://"):
                        cookie += "; Secure"

                    self.send_header("Set-Cookie", cookie)
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
                else:
                    raise ValueError("Invalid credentials")

            except Exception as e:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode('utf-8'))

        elif self.path == '/admin/request_reset':
            try:
                data = json.loads(post_data.decode('utf-8'))
                username = data.get("username")
                if not username:
                    raise ValueError("Username (email) is required")

                user = load_admin_user(username)
                if not user:
                    raise ValueError("No such user")

                code = generate_reset_code()
                save_reset_code(username, code)
                send_reset_email(username, code)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode('utf-8'))

        elif self.path == '/admin/reset_password':
            try:
                data = json.loads(post_data.decode('utf-8'))
                username = data.get("username")
                code = data.get("code")
                new_password = data.get("new_password")
                if not all([username, code, new_password]):
                    raise ValueError("All fields required")

                if not verify_reset_code(username, code):
                    raise ValueError("Invalid or expired code")

                hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                with conn.cursor() as cur:
                    cur.execute("UPDATE admin_users SET password = %s WHERE username = %s", (hashed_pw, username))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode('utf-8'))

        elif self.path == '/admin/update_testimony':
            if not self.require_auth():
                return
            try:
                data = json.loads(post_data.decode('utf-8'))
                testimony_id = data.get("id")
                action = data.get("action")
                if not testimony_id or action not in ("approve", "reject"):
                    raise ValueError("Invalid request")

                if action == "approve":
                    if not approve_testimony(testimony_id):
                        raise ValueError("Not found")
                    load_all_testimonies()
                else:
                    delete_pending_testimony(testimony_id)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode('utf-8'))

        elif self.path == '/admin/logout':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "session_token=deleted; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "reason": "Not found"}).encode('utf-8'))

# === Start Server ===
if __name__ == '__main__':
    print("Setting up database tables...")
    setup_tables()

    print("Loading testimonies from DB...")
    load_all_testimonies()
    update_visible_testimonies()

    print(f"Starting testimony rotation thread every {ROTATION_INTERVAL} seconds...")
    threading.Thread(target=rotate_testimonies, daemon=True).start()

    print(f"Serving HTTP on port {PORT} ...")
    with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
        httpd.serve_forever()
