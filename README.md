# 💰 FinBot – AI-Powered Personal Finance Assistant

> A full-stack personal finance web app with an AI chatbot, transaction tracking, financial health scoring, and a per-user financial calendar — all running locally via Flask.

---

## ✨ Features

### 🤖 AI Finance Chatbot
- Chat with **LLaMA 3.1 8B Instruct** (via [OpenRouter](https://openrouter.ai/)) about your finances
- AI is context-aware of your transactions and financial summary
- Streamed, conversational interface with a dark terminal-style UI

### 🔐 User Authentication
- Register & login with email + password (bcrypt-hashed via Werkzeug)
- Real-time username & email availability checks during sign-up
- Session-based auth — each user's data is fully isolated
- Auto-login after registration

### 💸 Transaction Tracking
- Add **income** and **expense** transactions with category, description, and date
- Delete transactions
- All transactions are scoped to the logged-in user

### 📊 Financial Summary & Health Score
- Live balance, total income, total expenses, and savings rate
- **Financial Health Score** (0–100) with a letter grade (A+ → F)
- Expense breakdown by category

### 📅 Financial Calendar
- Per-user monthly calendar view
- Add events tagged as **income**, **expense**, or **note**
- Events display directly on calendar days with color-coded badges
- Delete events from a day-detail panel

### 🎨 Premium Dark UI
- Three pages with glassmorphism, animated gradients, and micro-animations
- Fonts: **Inter** & **Space Grotesk** (Google Fonts)
- Fully responsive layout

---

## 🗂️ Project Structure

```
finance-project/
├── app.py                    # Flask backend — all API routes & DB logic
├── login.html                # Login / Register page
├── finance-chatbot (4).html  # Main chatbot + transaction dashboard
├── calendar.html             # Per-user financial calendar
├── requirements.txt          # Python dependencies
├── .env                      # Local secrets (not committed)
├── .env.example              # Environment variable template
├── .gitignore
├── LICENSE
├── finbot.db                 # SQLite DB (auto-created on first run)
└── users.db                  # (legacy, superseded by finbot.db)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- An **OpenRouter API key** → [openrouter.ai](https://openrouter.ai/) (free tier available)

### 2. Clone the repo

```bash
git clone https://github.com/joeflaming777-lgtm/finance-project-.git
cd finance-project-
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your key:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
SECRET_KEY=your-random-secret-key-here
```

> `SECRET_KEY` is used for Flask session signing. Generate one with:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

### 5. Run the app

```bash
python app.py
```

The server starts at **http://127.0.0.1:5000**

---

## 🌐 Pages & Routes

| URL | Description |
|-----|-------------|
| `/` | Login / Register page |
| `/app` | Main finance chatbot dashboard (requires login) |
| `/calendar` | Per-user financial calendar (requires login) |

---

## 🔌 API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/register` | Register a new user |
| `POST` | `/api/login` | Login |
| `POST` | `/api/logout` | Logout |
| `GET`  | `/api/me` | Get current user info |
| `POST` | `/api/check-username` | Check username availability |
| `POST` | `/api/check-email` | Check email availability |

### Transactions
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/transactions` | List all transactions for current user |
| `POST` | `/api/transactions` | Add a new transaction |
| `DELETE` | `/api/transactions/<id>` | Delete a transaction |

### Summary
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/summary` | Financial summary + health score for current user |

### Calendar
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/calendar` | List calendar events (optional `?month=YYYY-MM`) |
| `POST` | `/api/calendar` | Add a calendar event |
| `DELETE` | `/api/calendar/<id>` | Delete a calendar event |

### AI Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Proxy messages to OpenRouter LLaMA API |

---

## 🗄️ Database Schema

**SQLite** (`finbot.db`) — auto-created on first run.

```sql
-- Users
CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,   -- max 10 chars
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- Transactions
CREATE TABLE transactions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT REFERENCES users(id),
    type        TEXT CHECK(type IN ('income','expense')),
    amount      REAL CHECK(amount > 0),
    category    TEXT NOT NULL,
    description TEXT DEFAULT '',
    date        TEXT NOT NULL             -- format: DD/MM/YYYY
);

-- Calendar Events
CREATE TABLE calendar_events (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id),
    title      TEXT NOT NULL,
    amount     REAL DEFAULT 0,
    type       TEXT CHECK(type IN ('income','expense','note')),
    date       TEXT NOT NULL,             -- format: YYYY-MM-DD
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python · Flask |
| Database | SQLite (via `sqlite3`) |
| Auth | Werkzeug password hashing · Flask sessions |
| AI | LLaMA 3.1 8B Instruct via OpenRouter API |
| Frontend | Vanilla HTML · CSS · JavaScript |
| Fonts | Inter · Space Grotesk · JetBrains Mono |
| Config | python-dotenv |

---

## 🔒 Security Notes

- Passwords are hashed with **PBKDF2-SHA256** via `werkzeug.security`
- All transaction and calendar endpoints require an active session
- Each user can only read/modify their own data (user-scoped queries)
- CORS headers are open (`*`) — suitable for local dev only; restrict in production
- Change `SECRET_KEY` to a long random string before any public deployment

---

## 📝 License

MIT © 2026 [joeflaming777-lgtm](https://github.com/joeflaming777-lgtm)
