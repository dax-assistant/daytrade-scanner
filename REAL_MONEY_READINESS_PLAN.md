# Day Trade Scanner, Real Money Readiness Plan

Date: 2026-04-10
Owner: Zach / Bolt
Status: Planning

## Goal
Move the daytrade-scanner from a useful paper-trading research tool to a system that can eventually trade real money with explicit safety controls, broker-aware execution handling, and a staged rollout.

## Current honest assessment
The app is promising, but not ready for live capital yet.

What is already good:
- Live scanner, dashboard, and paper trading loop are working.
- Persistence, websocket updates, reconciliation hooks, and emergency stop exist.
- Paper results are directionally promising.

What is not good enough yet:
- No hard paper/live separation.
- Web control surface is not hardened enough for real-money trading.
- Secrets are stored in plaintext config.
- Execution handling is still too thin for live broker behavior.
- Risk controls are not yet strong enough.
- No test suite.
- Strategy validation is not mature enough for unattended live deployment.

---

# Priority roadmap

## P1, Must fix before any live-money testing
1. Hard paper/live separation
2. Secure the control surface
3. Move secrets out of config and rotate exposed credentials
4. Add audit logging for all trading-critical actions

## P2, Execution and broker safety
1. Broker-native protection, bracket/OCO/stop behavior where supported
2. Order state machine
3. Broker-first reconciliation
4. Failure handling for stale/rejected/partial/canceled orders

## P3, Risk engine and guardrails
1. Account-level hard limits
2. Trade-entry guardrails
3. Kill switches and circuit breakers

## P4, Validation before real rollout
1. Test suite
2. 20 to 30 market days of paper/shadow validation
3. Tiny-size supervised rollout only after all prior gates pass

---

# Detailed P1 implementation plan

## P1.1 Hard paper/live separation

### Objective
Make live trading impossible unless explicitly and safely enabled.

### Why this is P1
Right now the app uses paper endpoints in config, but the code does not enforce a true live-mode safety architecture. The current `environment` field is mostly descriptive, not a hard guardrail.

### Current code areas involved
- `config.yaml`
- `src/config.py`
- `src/simulator/engine.py`
- `src/data/alpaca_client.py`
- `src/web/routes.py`
- `run.py`

### Implementation tasks
1. Add an explicit trading-mode model in config.
   - Separate scanner/data environment from execution mode.
   - Introduce something like:
     - `trading.mode: paper | live`
     - `trading.live.enabled: false`
     - `trading.live.confirmation_phrase`
     - `trading.live.max_notional_per_order`
     - `trading.live.require_auth: true`
   - Keep paper as the default.

2. Split paper and live Alpaca credentials/base URLs.
   - Do not reuse a single credential block for both.
   - Paper and live must be distinct config/env inputs.

3. Add startup refusal rules.
   - App must refuse to start in live mode unless all of these pass:
     - explicit live enable flag is set
     - live credentials are present
     - web auth is enabled
     - websocket auth is enabled
     - secrets are coming from env/secret source, not plaintext YAML
     - required live risk settings are configured

4. Add runtime execution gate in the simulator/execution path.
   - Before any broker order submission, enforce a centralized policy check.
   - No route or code path should be able to bypass it.

5. Add a UI-visible mode banner.
   - Paper mode should be visually obvious.
   - Live mode should be visually impossible to miss.

6. Add a one-way safety default.
   - If config is ambiguous, invalid, or incomplete, execution falls back to non-live behavior.

### Acceptance criteria
- The app cannot submit a live order unless live mode is explicitly enabled and validated.
- Invalid live configuration prevents startup.
- Every order path passes through one centralized execution policy gate.
- The UI and API clearly expose whether the app is in paper or live mode.

---

## P1.2 Secure the control surface

### Objective
Harden the dashboard and APIs so they are safe enough to control a trading system.

### Why this is P1
Right now the app exposes powerful simulator endpoints and websocket functionality without enough protection. This is unacceptable for anything connected to live money.

### Current code areas involved
- `src/web/app.py`
- `src/web/routes.py`
- `src/web/ws_manager.py`
- `src/web/static/app.js`
- `src/config.py`
- `config.yaml`

### Current issues observed
- Web auth is optional and currently defaults off.
- CORS is `*`.
- Trading-impacting endpoints exist for manual entry, close, settings changes, and emergency stop.
- Websocket auth does not appear hardened.

### Implementation tasks
1. Turn web auth into a required feature for any non-dev deployment.
   - Add proper session-based auth middleware.
   - Require login for all pages and APIs except health/login endpoints.

2. Protect websocket access.
   - Require authenticated session or signed token for websocket connection.
   - Reject unauthenticated socket clients.

3. Lock down CORS.
   - Replace `*` with explicit allowed origins.
   - Fail closed by default.

4. Add authorization boundaries for critical actions.
   - Manual trade entry
   - Manual close
   - Settings changes
   - Emergency stop
   - Any future live execution route

5. Add confirmation flows for dangerous actions.
   - Manual entries
   - Emergency stop
   - Switching into live mode
   - Updating live-risk settings

6. Add request audit metadata.
   - Who initiated the action
   - When
   - What changed
   - Old/new values when applicable

### Acceptance criteria
- Unauthenticated users cannot access the dashboard, API, or websocket.
- CORS is explicit, not wildcard.
- Critical actions require authenticated access and confirmation.
- Audit trail records user-driven changes and trading actions.

---

## P1.3 Move secrets out of config and rotate exposed credentials

### Objective
Remove plaintext credentials from repo-adjacent config and establish safer secret handling.

### Why this is P1
The current config contains Alpaca, Finnhub, and Telegram credentials in plaintext. That is not acceptable for a system that may eventually handle live capital.

### Current code areas involved
- `config.yaml`
- `src/config.py`
- deployment/runtime environment setup
- any startup scripts or container env wiring

### Implementation tasks
1. Refactor config loading to support secrets from environment variables.
   - API keys
   - broker secrets
   - Telegram tokens
   - web session secret

2. Keep non-secret operational settings in YAML.
   - thresholds
   - intervals
   - feature flags
   - ports
   - UI options

3. Fail startup if required secrets are missing.

4. Create a `.env.example` or equivalent secret contract document.
   - names only, no real values

5. Rotate currently exposed credentials.
   - Alpaca paper keys
   - Finnhub key if needed
   - Telegram bot token
   - any session secret used later

6. Ensure paper and future live credentials are completely separated.

### Acceptance criteria
- No real secrets remain in `config.yaml`.
- App loads secrets from env or approved secret source.
- Missing required secrets fail fast on startup.
- Exposed current credentials are rotated.

---

## P1.4 Add audit logging for trading-critical actions

### Objective
Create an audit trail strong enough to reconstruct what the app tried to do, what the broker said, and what a user changed.

### Why this is P1
Before live trading, we need forensic visibility. Without this, debugging or post-incident analysis is too weak.

### Current code areas involved
- `src/simulator/engine.py`
- `src/data/alpaca_client.py`
- `src/web/routes.py`
- `src/db/manager.py`
- possibly new DB tables or JSONL audit logs

### Implementation tasks
1. Define an audit event model.
   - event type
   - timestamp
   - actor/source
   - symbol
   - side
   - requested quantity/price
   - broker order id
   - result status
   - reason/details payload

2. Record broker intent and broker result separately.
   - order_requested
   - order_submitted
   - order_rejected
   - order_filled
   - close_requested
   - close_submitted
   - reconciliation_mismatch

3. Record all control-plane actions.
   - login/logout
   - settings changes
   - profile edits
   - emergency stop
   - manual trade actions
   - mode changes

4. Persist audit data in structured form.
   - SQLite table and/or dedicated JSONL stream

5. Add a simple audit query surface.
   - recent audit events endpoint or admin view

### Acceptance criteria
- Every trading-critical action is logged with structured metadata.
- Every settings/control action is logged.
- Audit records are queryable and survive restarts.

---

# Recommended execution order inside P1
1. P1.1 Hard paper/live separation
2. P1.2 Secure the control surface
3. P1.3 Secrets migration and credential rotation
4. P1.4 Audit logging

Reason:
- P1.1 creates the core safety architecture.
- P1.2 makes the system safe to control.
- P1.3 removes a major operational risk before deeper rollout work.
- P1.4 gives us the visibility needed for later P2 and P3 work.

---

# Definition of done for P1 overall
P1 is done only when:
- Live trading is impossible without explicit safe enablement.
- UI/API/socket surfaces are authenticated and hardened.
- Secrets are no longer stored in plaintext config.
- Trading and control actions generate structured audit records.

At that point, we can move into P2 execution safety work.
