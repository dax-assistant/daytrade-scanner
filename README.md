# Day Trade Scanner (Python)

Production-oriented momentum scanner for Ross Cameron-style small-cap setups.

## What it does

- Runs continuously during **4:00 AM – 4:00 PM Eastern**
- Scans US equities for the **5 pillars**:
  1. Price in range ($2-$20)
  2. Gap up >= 30%
  3. Relative volume >= 5x
  4. Float < 10M shares
  5. Fresh news catalyst
- Sends Telegram alerts to chat ID `8474445926`
- Uses **Alpaca websocket** for real-time updates with REST polling fallback
- Logs scanner hits + sent alerts to daily JSONL files

---

## Project structure

```text
daytrade-scanner/
├── src/
│   ├── scanner.py
│   ├── alerts.py
│   ├── data/
│   │   ├── alpaca_client.py
│   │   ├── finnhub_client.py
│   │   └── models.py
│   ├── patterns/
│   │   └── micro_pullback.py
│   └── config.py
├── config.yaml
├── requirements.txt
├── run.py
└── README.md
```

---

## Requirements

- Python 3.10+
- Alpaca account (paper account is fine to start)
- Finnhub API key (free tier)
- Telegram bot token

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## API setup

## 1) Alpaca

1. Create account: https://alpaca.markets/
2. Generate API key + secret from dashboard
3. Keep paper trading enabled for initial testing
4. Export secrets as environment variables, not in `config.yaml`:
   - `ALPACA_PAPER_KEY_ID`
   - `ALPACA_PAPER_SECRET_KEY`
   - optional live credentials for armed live mode:
     - `ALPACA_LIVE_KEY_ID`
     - `ALPACA_LIVE_SECRET_KEY`

## 2) Finnhub

1. Create account: https://finnhub.io/
2. Get free API key
3. Export:
   - `FINNHUB_API_KEY`

## 3) Telegram Bot

1. Create bot via [@BotFather](https://t.me/BotFather)
2. Copy bot token
3. Export:
   - `TELEGRAM_BOT_TOKEN`
4. `chat_id` stays in `config.yaml`

## 4) Dashboard auth secrets

When enabling dashboard auth, export:
- `WEB_AUTH_PASSWORD`
- `WEB_AUTH_SESSION_SECRET`

---

## Configuration

All non-secret scanner thresholds are in `config.yaml` (nothing hardcoded):

- Price range
- Gap threshold
- Relative volume threshold
- Float threshold
- News freshness
- Alert cooldown + re-alert breakout
- Scan intervals by session
- Runtime and rate limits
- Logging paths

Tune these values directly in YAML.

Secrets should come from environment variables. Leave the secret fields in `config.yaml` blank.

---

## Run

```bash
export ALPACA_PAPER_KEY_ID=...
export ALPACA_PAPER_SECRET_KEY=...
export FINNHUB_API_KEY=...
# optional when Telegram is enabled
export TELEGRAM_BOT_TOKEN=...
# optional when dashboard auth is enabled
export WEB_AUTH_PASSWORD=...
export WEB_AUTH_SESSION_SECRET=...

python run.py --config config.yaml
```

---

## Alert format

Example alert:

```text
🔥 SCANNER HIT: $TICKER
Price: $X.XX (↑XX.X%)
Float: X.XM shares
Rel Volume: XXx
News: [headline]
Pillars: 5/5 ⭐⭐⭐⭐⭐
```

---

## Logging

Daily files are written under `logging.directory` (default `./logs`):

- `scanner-hits-YYYY-MM-DD.jsonl` (all evaluated scanner hits)
- `alerts-YYYY-MM-DD.jsonl` (all Telegram delivery attempts)
- `app-YYYY-MM-DD.log` (application runtime logs if configured externally)

---

## Reliability notes

- API calls are rate-limited per provider
- Retries + exponential backoff on transient failures
- 429 handling with `Retry-After`
- Alpaca websocket auto-reconnect with progressive backoff
- Polling loop remains active even if websocket drops

---

## v2 module

`src/patterns/micro_pullback.py` is intentionally stubbed for later implementation.
