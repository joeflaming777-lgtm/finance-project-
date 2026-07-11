"""
FinBot – Flask Backend
=====================
Endpoints:
  GET  /                       – Serve the frontend HTML
  POST /api/chat               – Proxy to OpenRouter AI (LLaMA 3.1)
  GET  /api/transactions       – List all transactions
  POST /api/transactions       – Add a new transaction
  DELETE /api/transactions/<id>– Delete a transaction
  GET  /api/summary            – Ledger totals + financial score
"""

import os
import sqlite3
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_file

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv()

app = Flask(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DB_PATH = os.path.join(os.path.dirname(__file__), "finbot.db")
AI_MODEL = "meta-llama/llama-3.1-8b-instruct"
AI_MAX_TOKENS = 2000

# ── CORS (allow the HTML to call the API from any origin) ─────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    return response

# ── Database helpers ──────────────────────────────────────────────────────────
def get_db():
    """Return a per-request SQLite connection (stored in Flask's g)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row          # rows behave like dicts
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """Create the transactions table if it does not exist."""
    with app.app_context():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          TEXT PRIMARY KEY,
                type        TEXT NOT NULL CHECK(type IN ('income','expense')),
                amount      REAL NOT NULL CHECK(amount > 0),
                category    TEXT NOT NULL,
                description TEXT DEFAULT '',
                date        TEXT NOT NULL
            )
        """)
        db.commit()

# ── Routes ────────────────────────────────────────────────────────────────────

# ---------- Serve the HTML front-end -----------------------------------------
@app.route("/")
def index():
    return send_file("finance-chatbot (4).html")

# ---------- AI chat proxy ----------------------------------------------------
@app.route("/api/chat", methods=["POST", "OPTIONS"])
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
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                # Optional: helps OpenRouter's analytics
                "HTTP-Referer": "http://127.0.0.1:5000",
                "X-Title": "FinBot Finance Assistant",
            },
            json={
                "model": AI_MODEL,
                "max_tokens": AI_MAX_TOKENS,
                "messages": messages,
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

# ---------- Transactions CRUD ------------------------------------------------
@app.route("/api/transactions", methods=["GET", "POST", "OPTIONS"])
def transactions():
    if request.method == "OPTIONS":
        return "", 204

    db = get_db()

    # ── GET: return all transactions (newest first) ──────────────────────────
    if request.method == "GET":
        rows = db.execute(
            "SELECT * FROM transactions ORDER BY date DESC, rowid DESC"
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    # ── POST: add a new transaction ──────────────────────────────────────────
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid payload"}), 400

    tx_type    = data.get("type", "").lower()
    amount     = data.get("amount")
    category   = data.get("category", "Other").strip()
    description= data.get("description", "").strip()
    date       = data.get("date") or datetime.today().strftime("%d/%m/%Y")

    # Validate
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

    tx_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO transactions (id, type, amount, category, description, date) VALUES (?,?,?,?,?,?)",
        (tx_id, tx_type, amount, category, description, date),
    )
    db.commit()

    return jsonify({
        "id": tx_id,
        "type": tx_type,
        "amount": amount,
        "category": category,
        "description": description,
        "date": date,
    }), 201

@app.route("/api/transactions/<tx_id>", methods=["DELETE", "OPTIONS"])
def delete_transaction(tx_id):
    if request.method == "OPTIONS":
        return "", 204

    db = get_db()
    row = db.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not row:
        return jsonify({"error": "Transaction not found"}), 404

    db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    db.commit()
    return jsonify({"deleted": tx_id})

# ---------- Summary / analytics ----------------------------------------------
@app.route("/api/summary", methods=["GET"])
def summary():
    db = get_db()

    income_row  = db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE type='income'").fetchone()
    expense_row = db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE type='expense'").fetchone()
    tx_count    = db.execute("SELECT COUNT(*) AS cnt FROM transactions").fetchone()["cnt"]

    income   = income_row["total"]
    expenses = expense_row["total"]
    balance  = income - expenses
    savings_rate = round((balance / income) * 100, 1) if income > 0 else 0.0

    # Financial health score (same formula as frontend)
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

    # Top expense category
    top_cat_row = db.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE type = 'expense'
        GROUP BY category
        ORDER BY total DESC
        LIMIT 1
    """).fetchone()
    top_category = top_cat_row["category"] if top_cat_row else None

    # Category breakdown
    cat_rows = db.execute("""
        SELECT type, category, SUM(amount) AS total
        FROM transactions
        GROUP BY type, category
        ORDER BY total DESC
    """).fetchall()
    breakdown = [dict(r) for r in cat_rows]

    return jsonify({
        "income":       income,
        "expenses":     expenses,
        "balance":      balance,
        "savingsRate":  savings_rate,
        "txCount":      tx_count,
        "topCategory":  top_category,
        "score":        score,
        "grade":        grade,
        "breakdown":    breakdown,
    })

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("\n[FinBot] Backend running at http://127.0.0.1:5000")
    print("         Open that URL in your browser to launch the app.\n")
    app.run(debug=True, host="127.0.0.1", port=5000)