# 🎮 PlayStation 4K Auto-Buyer & Restock Sniper Bot

Dedicated Python Telegram Bot engineered specifically to snipe and auto-buy **PlayStation Gift Cards (₹4,000 / 4K)** from **Rooter Shop** using Rooter Wallet balances across multiple accounts simultaneously.

Based on the battle-tested **October 17 codebase**, customized for **exclusive ₹4,000 card purchasing**, multi-account parallel checkout, and multi-admin broadcast notifications.

---

## 🌟 Key Features

1. **Strictly 4K PlayStation Gift Card Focus**:
   - Targets only **PlayStation Gift Card ₹4,000**.
   - Auto-checks restocks every 29 seconds.
   - Instantly buys when stock lands without touching unwanted denominations.

2. **Multi-Account Concurrent Sniper (3–10 Accounts)**:
   - Run multiple Rooter accounts in parallel (e.g., 3 accounts x ₹4,000 = ₹12,000).
   - Each account buys 1 card (₹4,000) or up to 2 cards (₹8,000) if wallet balance has ≥ ₹8,000.
   - Live wallet balance auto-sync in real time directly from Rooter's payments API.

3. **Multi-Admin Broadcast Notifications**:
   - Access restricted to authorized Chat IDs: `5701727023`, `1988639571`, `828429985`, `8801210593`.
   - All 4 Telegram IDs receive instant alerts:
     - 🚨 **Stock Detected Alert**
     - 🎉 **Purchase Successful with Voucher Codes & PINs**
     - 📸 **Order Confirmation Screenshots**
     - 🛑 **Status / Stop notifications**

4. **Headless Browser Automation (Playwright)**:
   - Headless Chromium with Indian region configuration and anti-detect stealth.
   - Auto-dismisses "Different Location Detected" popups.
   - 1-click checkout with Rooter wallet balance and automated coupon retrieval.

---

## ⚡ Telegram Commands

- `/start` — Welcome dashboard, live balance overview & quick action buttons.
- `/snipe` — 🎯 Start 24/7 restock auto-sniper for ₹4,000 PlayStation Card.
- `/stop` — 🛑 Stop 24/7 restock auto-sniper.
- `/buy` — 🛒 Instant 1-click buy for ₹4,000 PlayStation Card.
- `/accounts` — 👥 Multi-account dashboard (view balances, pause/resume, remove).
- `/addaccount <token> [label]` — Add new Rooter account with auto live balance sync.
- `/settoken <token>` — Quick update for primary account token.
- `/setbalance <acc_id> <amount>` — Manual balance override (if needed).
- `/status` — View current sessions, sniper state, and admin IDs.
- `/toggle_sim` — Switch between **Safe Simulation Mode** and **Live Purchasing**.
- `/help` — Full command list and operational guide.

💡 *Tip:* Authorized admins can simply paste a Bearer token (`eyJhbGciOi...`) directly into the chat to auto-register an account!

---

## 📂 Project Structure

```
Play-Card-Bot/
├── .env                       # Pre-configured credentials and chat IDs
├── .env.example               # Template for environment variables
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker container for Railway/VPS
├── Procfile                   # Process file for cloud hosting
├── railway.json               # Railway deployment configuration
├── replit.nix                 # Replit environment configuration
├── config.py                  # Bot configuration & admin authorization
├── main.py                    # Main bot application entry point
├── start_bot.bat              # 1-Click local Windows startup batch script
├── bot/
│   ├── __init__.py
│   ├── states.py              # Conversation states
│   ├── keyboards.py           # Rich inline buttons & UI
│   └── handlers.py            # Command handlers & 4K multi-account sniper
├── services/
│   ├── __init__.py
│   ├── account_manager.py     # Multi-account storage & live balance sync
│   ├── base_platform.py       # Base platform interfaces
│   ├── browser_manager.py     # Playwright browser instance manager
│   └── rooter_service.py      # Rooter Shop Playwright automation engine
├── sessions/                  # Stored session files
└── screenshots/               # Order proofs & error screenshots
```

---

## 🚀 Environment Configuration (.env)

```env
BOT_TOKEN=8918128794:AAFYwsRDHm--pZwe9jm9pnBQe0PWUve4nck
ADMIN_CHAT_IDS=5701727023,1988639571,828429985,8801210593
TARGET_DENOMINATION=4000
MAX_CARDS_PER_ACCOUNT=2
SIMULATION_MODE=False
HEADLESS=true
SNIPE_INTERVAL_SECONDS=29
BLOCK_MEDIA_RESOURCES=True
```

---

## 💻 Running Locally

Double click `start_bot.bat` or run:

```bash
python main.py
```
