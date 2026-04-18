import os
import sqlite3
from flask import Flask, request, jsonify, send_file, redirect, url_for, g
import requests
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE = "users.db"

# ─── Database helpers ────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Create the users table if it doesn't exist."""
    with sqlite3.connect(DATABASE) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()
    print("✅ Database initialised — users table ready.")

# ─── CORS ────────────────────────────────────────────────────────────────────

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ─── Page routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return send_file("login.html")

@app.route('/dashboard')
def dashboard():
    return send_file("finance-chatbot (4).html")

# ─── Auth API ────────────────────────────────────────────────────────────────

@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 204
    data = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400

    hashed = generate_password_hash(password)
    try:
        db = get_db()
        db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, hashed))
        db.commit()
        return jsonify({"success": True, "message": "Account created! You can now sign in."}), 201
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "An account with this email already exists."}), 409
    except Exception as e:
        print(f"Register error: {e}")
        return jsonify({"success": False, "message": "Server error."}), 500


@app.route('/api/login', methods=['POST', 'OPTIONS'])
def api_login():
    if request.method == 'OPTIONS':
        return '', 204
    data = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None:
        return jsonify({"success": False, "message": "No account found with that email."}), 404
    if not check_password_hash(user["password_hash"], password):
        return jsonify({"success": False, "message": "Incorrect password. Please try again."}), 401

    return jsonify({"success": True, "message": "Login successful!", "email": email}), 200

# ─── Chat API ────────────────────────────────────────────────────────────────

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.json
        if not data:
            return jsonify({"error": {"message": "Invalid request payload"}}), 400

        messages = data.get("messages", [])
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {GROQ_API_KEY}'
            },
            json={
                'model': 'llama-3.1-8b-instant',
                'max_tokens': 1000,
                'messages': messages
            }
        )
        return jsonify(response.json()), response.status_code

    except Exception as e:
        print(f"Error handling chat request: {e}")
        return jsonify({"error": {"message": "Internal server error"}}), 500

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='127.0.0.1', port=5000)