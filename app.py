"""
FinBot – Flask Backend  (v2 – with Auth & Per-User Calendar)
=============================================================
Endpoints:
  GET  /                          – Serve login page (redirects to main if logged in)
  GET  /app                       – Serve the main finance chatbot HTML
  GET  /calendar                  – Serve the per-user calendar HTML

  POST /api/register              – Register a new user
  POST /api/login                 – Login
  POST /api/logout                – Logout
  GET  /api/me                    – Current user info

  GET  /api/transactions          – List transactions (scoped to user)
  POST /api/transactions          – Add transaction (scoped to user)
  DELETE /api/transactions/<id>   – Delete transaction

  GET  /api/summary               – Financial summary (scoped to user)

  GET  /api/calendar              – List calendar events for current user
  POST /api/calendar              – Add calendar event
  DELETE /api/calendar/<id>       – Delete calendar event

  POST /api/check-username        – Check if username is taken (real-time)
  POST /api/check-email           – Check if email is taken (real-time)

  POST /api/send-delete-code      – Send 6-digit OTP to user's email for account deletion
  POST /api/delete-account        – Permanently delete account (verifies OTP from email)
"""

import os
import random
import smtplib
import sqlite3
import uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (Flask, g, jsonify, redirect, request,
                   send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "finbot-dev-secret-please-change-me")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DB_PATH            = os.path.join(os.path.dirname(__file__), "finbot.db")
AI_MODEL           = "meta-llama/llama-3.1-8b-instruct"
AI_MAX_TOKENS      = 2000

# ── Email / SMTP config ───────────────────────────────────────────────────────
SMTP_HOST      = os.getenv("SMTP_HOST",      "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT",  "587"))
SMTP_USER      = os.getenv("SMTP_USER",      "finbot067@gmail.com")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD",  "")   # Gmail App Password
SMTP_FROM      = os.getenv("SMTP_FROM",      SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "FinBot Support")

# EMAIL_ENABLED is True only when real (non-placeholder) credentials are set
_is_placeholder = lambda v: (not v) or v.lower().startswith("your_")
EMAIL_ENABLED   = not (_is_placeholder(SMTP_USER) or _is_placeholder(SMTP_PASSWORD))


# ── CORS ──────────────────────────────────────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    return response


# ── Email helpers ────────────────────────────────────────────────────────────
def send_email(to_addr: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """Send an email via SMTP. Returns True on success, False if email is disabled or fails."""
    if not EMAIL_ENABLED:
        app.logger.info("[Email] SMTP not configured – skipping send to %s", to_addr)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{SMTP_FROM_NAME} <{SMTP_FROM}>"
        msg["To"]      = to_addr
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_addr, msg.as_string())
        app.logger.info("[Email] Sent '%s' to %s", subject, to_addr)
        return True
    except Exception as exc:
        app.logger.error("[Email] Failed to send to %s: %s", to_addr, exc)
        return False


def send_welcome_email(username: str, email: str) -> None:
    """Send a greeting email to a newly-logged-in user."""
    subject = "👋 Welcome back to FinBot – You're logged in!"
    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;background:#080b0e;color:#dce8f0;padding:32px;">
      <div style="max-width:520px;margin:0 auto;">
        <div style="text-align:center;margin-bottom:24px;">
          <div style="display:inline-block;background:linear-gradient(135deg,#00d4aa,#3b9eff);
                      border-radius:14px;padding:14px 22px;font-size:28px;">💹</div>
          <h1 style="font-size:22px;font-weight:700;margin:12px 0 4px;
                     background:linear-gradient(90deg,#00d4aa,#3b9eff);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
            FinBot Finance Assistant
          </h1>
          <p style="margin:0;font-size:12px;color:#4a6070;">Sent by FinBot Support · finbot067@gmail.com</p>
        </div>

        <div style="background:#0e1318;border:1px solid #1f2e3d;border-radius:12px;padding:24px;">
          <p style="font-size:16px;font-weight:600;color:#dce8f0;margin:0 0 10px;">Hey {username}! 👋</p>
          <p style="color:#8fa3b8;font-size:14px;line-height:1.7;margin:0 0 16px;">
            You've successfully logged into <strong style="color:#00d4aa;">FinBot</strong>.
            Your smart finance assistant is ready to help you track income, log expenses,
            and get insights on your spending.
          </p>
          <div style="background:#141c23;border-radius:8px;padding:14px 18px;margin-bottom:16px;">
            <p style="margin:0 0 6px;font-size:11px;color:#4a6070;letter-spacing:.08em;text-transform:uppercase;">Logged in as</p>
            <p style="margin:0;font-size:14px;color:#dce8f0;font-weight:500;">{username}</p>
            <p style="margin:2px 0 0;font-size:12px;color:#8fa3b8;">{email}</p>
          </div>
          <p style="color:#8fa3b8;font-size:13px;line-height:1.6;margin:0;">
            If this wasn't you, please <a href="/" style="color:#ff7043;">sign in and change your password</a> immediately.
          </p>
        </div>

        <p style="text-align:center;color:#4a6070;font-size:11px;margin-top:20px;">
          © FinBot Support · finbot067@gmail.com
        </p>
      </div>
    </div>
    """
    text = f"Hey {username},\n\nYou've logged in to FinBot.\nIf this wasn't you, please secure your account immediately.\n\n— FinBot Support\nfinbot067@gmail.com"
    send_email(email, subject, html, text)


def send_registration_email(username: str, email: str) -> None:
    """Send a welcome-aboard email when a new user registers."""
    subject = "🎉 Welcome to FinBot – Your account is ready!"
    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;background:#080b0e;color:#dce8f0;padding:32px;">
      <div style="max-width:520px;margin:0 auto;">
        <div style="text-align:center;margin-bottom:24px;">
          <div style="display:inline-block;background:linear-gradient(135deg,#00d4aa,#3b9eff);
                      border-radius:14px;padding:14px 22px;font-size:36px;">🎉</div>
          <h1 style="font-size:22px;font-weight:700;margin:12px 0 4px;
                     background:linear-gradient(90deg,#00d4aa,#3b9eff);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
            Welcome to FinBot!
          </h1>
          <p style="margin:0;font-size:12px;color:#4a6070;">Sent by FinBot Support · finbot067@gmail.com</p>
        </div>

        <div style="background:#0e1318;border:1px solid #1f2e3d;border-radius:12px;padding:24px;">
          <p style="font-size:16px;font-weight:600;color:#dce8f0;margin:0 0 10px;">Hi {username}! 🚀</p>
          <p style="color:#8fa3b8;font-size:14px;line-height:1.7;margin:0 0 16px;">
            Your <strong style="color:#00d4aa;">FinBot</strong> account has been successfully created.
            You can now start tracking your income, expenses, and financial goals all in one place.
          </p>

          <div style="background:#141c23;border-radius:8px;padding:14px 18px;margin-bottom:16px;">
            <p style="margin:0 0 6px;font-size:11px;color:#4a6070;letter-spacing:.08em;text-transform:uppercase;">Account Details</p>
            <p style="margin:0;font-size:14px;color:#dce8f0;font-weight:500;">👤 {username}</p>
            <p style="margin:4px 0 0;font-size:12px;color:#8fa3b8;">📧 {email}</p>
          </div>

          <div style="display:flex;gap:10px;margin-bottom:16px;">
            <div style="flex:1;background:linear-gradient(135deg,rgba(0,212,170,0.1),rgba(0,212,170,0.05));
                        border:1px solid rgba(0,212,170,0.2);border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:20px;margin-bottom:4px;">📊</div>
              <p style="margin:0;font-size:11px;color:#00d4aa;font-weight:600;">Track Finances</p>
            </div>
            <div style="flex:1;background:linear-gradient(135deg,rgba(59,158,255,0.1),rgba(59,158,255,0.05));
                        border:1px solid rgba(59,158,255,0.2);border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:20px;margin-bottom:4px;">🤖</div>
              <p style="margin:0;font-size:11px;color:#3b9eff;font-weight:600;">AI Assistant</p>
            </div>
            <div style="flex:1;background:linear-gradient(135deg,rgba(255,193,7,0.1),rgba(255,193,7,0.05));
                        border:1px solid rgba(255,193,7,0.2);border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:20px;margin-bottom:4px;">📅</div>
              <p style="margin:0;font-size:11px;color:#ffc107;font-weight:600;">Calendar</p>
            </div>
          </div>

          <p style="color:#8fa3b8;font-size:13px;line-height:1.6;margin:0;">
            If you didn't create this account, please contact us immediately at
            <a href="mailto:finbot067@gmail.com" style="color:#ff7043;">finbot067@gmail.com</a>.
          </p>
        </div>

        <p style="text-align:center;color:#4a6070;font-size:11px;margin-top:20px;">
          © FinBot Support · finbot067@gmail.com
        </p>
      </div>
    </div>
    """
    text = (
        f"Hi {username},\n\n"
        f"Your FinBot account has been successfully created!\n"
        f"Username: {username}\nEmail: {email}\n\n"
        f"Start tracking your finances at http://127.0.0.1:5000\n\n"
        f"If you didn't create this account, contact us at finbot067@gmail.com.\n\n"
        f"— FinBot Support\nfinbot067@gmail.com"
    )
    send_email(email, subject, html, text)


def send_delete_otp_email(username: str, email: str, otp: str) -> bool:
    """Send the 6-digit OTP for account deletion confirmation."""
    subject = "🔐 FinBot Account Deletion Code"
    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;background:#080b0e;color:#dce8f0;padding:32px;">
      <div style="max-width:520px;margin:0 auto;">
        <div style="text-align:center;margin-bottom:24px;">
          <div style="display:inline-block;background:linear-gradient(135deg,#ff7043,#ff4444);
                      border-radius:14px;padding:14px 22px;font-size:28px;">⚠️</div>
          <h1 style="font-size:20px;font-weight:700;margin:12px 0 4px;color:#ff7043;">
            Account Deletion Request
          </h1>
        </div>

        <div style="background:#0e1318;border:1px solid rgba(255,112,67,0.3);border-radius:12px;padding:24px;">
          <p style="font-size:15px;color:#dce8f0;margin:0 0 12px;">Hi <strong>{username}</strong>,</p>
          <p style="color:#8fa3b8;font-size:14px;line-height:1.7;margin:0 0 20px;">
            We received a request to <strong style="color:#ff7043;">permanently delete</strong> your FinBot account.
            Use the verification code below to confirm. This code expires in <strong style="color:#dce8f0;">10 minutes</strong>.
          </p>

          <div style="text-align:center;background:#141c23;border:2px solid rgba(255,112,67,0.4);
                      border-radius:12px;padding:24px;margin-bottom:20px;">
            <p style="margin:0 0 8px;font-size:11px;color:#4a6070;letter-spacing:.1em;text-transform:uppercase;">Verification Code</p>
            <p style="margin:0;font-size:36px;font-weight:700;letter-spacing:10px;color:#ff7043;
                      font-family:'Courier New',monospace;">{otp}</p>
          </div>

          <div style="background:rgba(255,112,67,0.07);border-radius:8px;padding:12px 16px;">
            <p style="margin:0;font-size:12px;color:#ff7043;">
              ⚠️ <strong>This action is irreversible.</strong> All your transactions, calendar events,
              and account data will be permanently erased.
            </p>
          </div>

          <p style="color:#4a6070;font-size:12px;margin:16px 0 0;">
            If you did <strong>not</strong> request this, you can safely ignore this email. Your account remains safe.
          </p>
        </div>

        <p style="text-align:center;color:#4a6070;font-size:11px;margin-top:20px;">
          © FinBot · Your Personal Finance Assistant
        </p>
      </div>
    </div>
    """
    text = f"Hi {username},\n\nYour FinBot account deletion code is: {otp}\nThis code expires in 10 minutes.\n\nIf you did not request this, ignore this email."
    return send_email(email, subject, html, text)


# ── Database helpers ──────────────────────────────────────────────────────────
def get_db():
    """Return a per-request SQLite connection stored in Flask's g."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create / migrate all tables."""
    with app.app_context():
        db = get_db()

        # ── Users ──────────────────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           TEXT PRIMARY KEY,
                username     TEXT NOT NULL UNIQUE CHECK(LENGTH(username) <= 10),
                email        TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
        """)

        # ── Transactions (add user_id if column doesn't exist yet) ────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          TEXT PRIMARY KEY,
                user_id     TEXT REFERENCES users(id),
                type        TEXT NOT NULL CHECK(type IN ('income','expense')),
                amount      REAL NOT NULL CHECK(amount > 0),
                category    TEXT NOT NULL,
                description TEXT DEFAULT '',
                date        TEXT NOT NULL
            )
        """)
        # Migration: add user_id column to existing transactions table
        cols = [r[1] for r in db.execute("PRAGMA table_info(transactions)").fetchall()]
        if "user_id" not in cols:
            db.execute("ALTER TABLE transactions ADD COLUMN user_id TEXT REFERENCES users(id)")

        # ── Calendar Events ───────────────────────────────────────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS calendar_events (
                id         TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL REFERENCES users(id),
                title      TEXT NOT NULL,
                amount     REAL DEFAULT 0,
                type       TEXT CHECK(type IN ('income','expense','note')),
                date       TEXT NOT NULL,
                note       TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        db.commit()


# ── Auth helpers ──────────────────────────────────────────────────────────────
def current_user_id():
    return session.get("user_id")


def login_required(f):
    """Decorator: returns 401 JSON if the user is not logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user_id():
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Page Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Login page (root). Redirect to /app if already logged in."""
    if current_user_id():
        return redirect(url_for("main_app"))
    return send_file("login.html")


@app.route("/app")
def main_app():
    """Main finance chatbot – requires login."""
    if not current_user_id():
        return redirect(url_for("index"))
    return send_file("finance-chatbot (4).html")


@app.route("/calendar")
def calendar_page():
    """Per-user calendar page – requires login."""
    if not current_user_id():
        return redirect(url_for("index"))
    return send_file("calendar.html")


# ── Auth API ──────────────────────────────────────────────────────────────────

@app.route("/api/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return "", 204

    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "")

    errors = {}

    # Username validation
    if not username:
        errors["username"] = "Username is required"
    elif len(username) > 10:
        errors["username"] = "Username must be 10 characters or fewer"
    elif not username.replace("_", "").replace("-", "").isalnum():
        errors["username"] = "Username may only contain letters, numbers, hyphens, or underscores"

    # Email validation
    if not email:
        errors["email"] = "Email is required"
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Please enter a valid email address"

    # Password validation
    if not password:
        errors["password"] = "Password is required"
    elif len(password) < 8:
        errors["password"] = "Password must be at least 8 characters"

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    db = get_db()

    # Uniqueness checks
    if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        return jsonify({"error": "Validation failed", "details": {"username": "This username is already taken"}}), 409

    if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        return jsonify({"error": "Validation failed", "details": {"email": "This email is already registered"}}), 409

    user_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, username, email, password_hash, created_at) VALUES (?,?,?,?,?)",
        (user_id, username, email, generate_password_hash(password), datetime.utcnow().isoformat()),
    )
    db.commit()

    # Auto-login after registration
    session["user_id"]  = user_id
    session["username"] = username
    session["email"]    = email

    # Send registration welcome email (non-blocking)
    try:
        send_registration_email(username, email)
    except Exception as exc:
        app.logger.warning("[Email] Registration email failed: %s", exc)

    return jsonify({"id": user_id, "username": username, "email": email}), 201


@app.route("/api/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return "", 204

    data     = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["email"]    = user["email"]

    # Fire greeting email (non-blocking – errors are logged, never raised)
    try:
        send_welcome_email(user["username"], user["email"])
    except Exception as exc:
        app.logger.warning("[Email] Welcome email failed: %s", exc)

    return jsonify({"id": user["id"], "username": user["username"], "email": user["email"]})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/api/me", methods=["GET"])
@login_required
def me():
    return jsonify({
        "id":       current_user_id(),
        "username": session.get("username"),
        "email":    session.get("email"),
    })


@app.route("/api/send-delete-code", methods=["POST", "OPTIONS"])
@login_required
def send_delete_code():
    """Generate a 6-digit OTP, store it in session, and email it to the user."""
    if request.method == "OPTIONS":
        return "", 204

    user_id  = current_user_id()
    username = session.get("username", "User")
    email    = session.get("email", "")

    if not email:
        return jsonify({"error": "No email address found for your account"}), 400

    # Generate a 6-digit OTP
    otp = "{:06d}".format(random.randint(0, 999999))

    # Store OTP + expiry in session
    session["delete_otp"]        = otp
    session["delete_otp_expiry"] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    session["delete_otp_uid"]    = user_id   # bind to this user

    if not EMAIL_ENABLED:
        # Dev fallback: return the code when SMTP is not configured
        app.logger.warning("[Dev] SMTP not configured. Delete OTP for %s: %s", email, otp)
        return jsonify({
            "message": "Code generated (SMTP not configured – see toast for your code)",
            "dev_code": otp
        }), 200

    ok = send_delete_otp_email(username, email, otp)
    if not ok:
        # Email configured but sending failed — still return code so user isn't stuck
        app.logger.error("[Email] OTP send failed for %s – returning dev_code fallback", email)
        return jsonify({
            "message": "Email delivery failed. Use the code shown on screen.",
            "dev_code": otp
        }), 200

    return jsonify({"message": f"Verification code sent to {email}"}), 200


@app.route("/api/delete-account", methods=["POST", "OPTIONS"])
@login_required
def delete_account():
    """Permanently delete the current user's account after verifying the emailed OTP."""
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    otp  = (data.get("otp") or "").strip()

    if not otp:
        return jsonify({"error": "Verification code is required"}), 400

    # Validate OTP from session
    stored_otp    = session.get("delete_otp")
    stored_expiry = session.get("delete_otp_expiry")
    stored_uid    = session.get("delete_otp_uid")
    user_id       = current_user_id()

    if not stored_otp or not stored_expiry or stored_uid != user_id:
        return jsonify({"error": "No verification code found. Please request a new one."}), 400

    # Check expiry
    if datetime.utcnow() > datetime.fromisoformat(stored_expiry):
        session.pop("delete_otp", None)
        session.pop("delete_otp_expiry", None)
        session.pop("delete_otp_uid", None)
        return jsonify({"error": "Code has expired. Please request a new one."}), 403

    # Verify OTP
    if otp != stored_otp:
        return jsonify({"error": "Incorrect verification code. Please try again."}), 403

    # OTP valid — delete all user data
    db = get_db()
    db.execute("DELETE FROM transactions     WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM calendar_events WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users           WHERE id      = ?", (user_id,))
    db.commit()

    # Clear session entirely
    session.clear()

    return jsonify({"message": "Account permanently deleted"}), 200


# ── Real-time uniqueness checks ───────────────────────────────────────────────

@app.route("/api/check-username", methods=["POST"])
def check_username():
    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"available": False, "reason": "empty"})
    taken = bool(get_db().execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone())
    return jsonify({"available": not taken})


@app.route("/api/check-email", methods=["POST"])
def check_email():
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"available": False, "reason": "empty"})
    taken = bool(get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone())
    return jsonify({"available": not taken})


# ── Transactions CRUD (scoped to current user) ────────────────────────────────

@app.route("/api/transactions", methods=["GET", "POST", "OPTIONS"])
@login_required
def transactions():
    if request.method == "OPTIONS":
        return "", 204

    db      = get_db()
    user_id = current_user_id()

    if request.method == "GET":
        rows = db.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC, rowid DESC",
            (user_id,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    data        = request.get_json(silent=True) or {}
    tx_type     = data.get("type", "").lower()
    amount      = data.get("amount")
    category    = (data.get("category") or "Other").strip()
    description = (data.get("description") or "").strip()
    date        = data.get("date") or datetime.today().strftime("%d/%m/%Y")

    errors = {}
    if tx_type not in ("income", "expense"):
        errors["type"] = "Must be 'income' or 'expense'"
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors["amount"] = "Must be a positive number"
    if not category:
        errors["category"] = "Required"

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    tx_id = (data.get("id") or "").strip() or str(uuid.uuid4())
    db.execute(
        "INSERT INTO transactions (id, user_id, type, amount, category, description, date) VALUES (?,?,?,?,?,?,?)",
        (tx_id, user_id, tx_type, amount, category, description, date),
    )
    db.commit()

    return jsonify({
        "id": tx_id, "user_id": user_id, "type": tx_type,
        "amount": amount, "category": category,
        "description": description, "date": date,
    }), 201


@app.route("/api/transactions/<tx_id>", methods=["DELETE", "OPTIONS"])
@login_required
def delete_transaction(tx_id):
    if request.method == "OPTIONS":
        return "", 204

    db      = get_db()
    user_id = current_user_id()
    row     = db.execute(
        "SELECT id FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id)
    ).fetchone()

    if not row:
        return jsonify({"error": "Transaction not found"}), 404

    db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    db.commit()
    return jsonify({"deleted": tx_id})


# ── Summary / analytics (scoped to user) ─────────────────────────────────────

@app.route("/api/summary", methods=["GET"])
@login_required
def summary():
    db      = get_db()
    user_id = current_user_id()

    income_row  = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE type='income' AND user_id=?",
        (user_id,),
    ).fetchone()
    expense_row = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE type='expense' AND user_id=?",
        (user_id,),
    ).fetchone()
    tx_count    = db.execute(
        "SELECT COUNT(*) AS cnt FROM transactions WHERE user_id=?", (user_id,)
    ).fetchone()["cnt"]

    income       = income_row["total"]
    expenses     = expense_row["total"]
    balance      = income - expenses
    savings_rate = round((balance / income) * 100, 1) if income > 0 else 0.0

    score = 0
    grade = "—"
    if income > 0:
        savings_score = min(50.0, (savings_rate / 20) * 50)
        exp_score     = max(0.0, 30 - ((expenses / income) * 30))
        score         = round(min(100, savings_score + exp_score + 20))
        if   score >= 85: grade = "A+"
        elif score >= 70: grade = "A"
        elif score >= 55: grade = "B"
        elif score >= 40: grade = "C"
        elif score >= 25: grade = "D"
        else:             grade = "F"

    top_cat_row = db.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE type = 'expense' AND user_id = ?
        GROUP BY category ORDER BY total DESC LIMIT 1
    """, (user_id,)).fetchone()
    top_category = top_cat_row["category"] if top_cat_row else None

    cat_rows  = db.execute("""
        SELECT type, category, SUM(amount) AS total
        FROM transactions
        WHERE user_id = ?
        GROUP BY type, category ORDER BY total DESC
    """, (user_id,)).fetchall()
    breakdown = [dict(r) for r in cat_rows]

    return jsonify({
        "income":      income,
        "expenses":    expenses,
        "balance":     balance,
        "savingsRate": savings_rate,
        "txCount":     tx_count,
        "topCategory": top_category,
        "score":       score,
        "grade":       grade,
        "breakdown":   breakdown,
    })


# ── Calendar Events ───────────────────────────────────────────────────────────

@app.route("/api/calendar", methods=["GET", "POST", "OPTIONS"])
@login_required
def calendar_events():
    if request.method == "OPTIONS":
        return "", 204

    db      = get_db()
    user_id = current_user_id()

    if request.method == "GET":
        month = request.args.get("month")   # "YYYY-MM"  optional filter
        if month:
            rows = db.execute(
                "SELECT * FROM calendar_events WHERE user_id = ? AND date LIKE ? ORDER BY date",
                (user_id, f"{month}%"),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM calendar_events WHERE user_id = ? ORDER BY date",
                (user_id,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    data   = request.get_json(silent=True) or {}
    title  = (data.get("title") or "").strip()
    amount = data.get("amount", 0)
    etype  = (data.get("type") or "note").lower()
    date   = (data.get("date") or "").strip()
    note   = (data.get("note") or "").strip()

    if not title:
        return jsonify({"error": "Title is required"}), 422
    if not date:
        return jsonify({"error": "Date is required"}), 422
    if etype not in ("income", "expense", "note"):
        etype = "note"

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0

    ev_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO calendar_events (id, user_id, title, amount, type, date, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (ev_id, user_id, title, amount, etype, date, note, datetime.utcnow().isoformat()),
    )
    db.commit()

    return jsonify({
        "id": ev_id, "user_id": user_id, "title": title,
        "amount": amount, "type": etype, "date": date, "note": note,
    }), 201


@app.route("/api/calendar/<ev_id>", methods=["DELETE", "OPTIONS"])
@login_required
def delete_calendar_event(ev_id):
    if request.method == "OPTIONS":
        return "", 204

    db      = get_db()
    user_id = current_user_id()
    row     = db.execute(
        "SELECT id FROM calendar_events WHERE id = ? AND user_id = ?", (ev_id, user_id)
    ).fetchone()

    if not row:
        return jsonify({"error": "Event not found"}), 404

    db.execute("DELETE FROM calendar_events WHERE id = ?", (ev_id,))
    db.commit()
    return jsonify({"deleted": ev_id})


# ── AI chat proxy ─────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST", "OPTIONS"])
@login_required
def chat():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": {"message": "Invalid request payload"}}), 400

    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": {"message": "No messages provided"}}), 400

    if not OPENROUTER_API_KEY:
        return jsonify({"error": {"message": "OPENROUTER_API_KEY not configured on the server"}}), 500

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer":  "http://127.0.0.1:5000",
                "X-Title":       "FinBot Finance Assistant",
            },
            json={
                "model":      AI_MODEL,
                "max_tokens": AI_MAX_TOKENS,
                "messages":   messages,
            },
            timeout=60,
        )
        return jsonify(resp.json()), resp.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": {"message": "AI service timed out – please try again"}}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": {"message": "Could not reach AI service"}}), 502
    except Exception as exc:
        app.logger.error("chat error: %s", exc)
        return jsonify({"error": {"message": "Internal server error"}}), 500


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("\n[FinBot] Backend running at http://127.0.0.1:5000")
    print("         Open that URL in your browser to launch the app.\n")
    app.run(debug=True, host="127.0.0.1", port=5000)