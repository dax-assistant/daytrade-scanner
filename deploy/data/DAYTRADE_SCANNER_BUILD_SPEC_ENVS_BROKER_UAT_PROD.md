# Day Trade Scanner Build Spec

Date: 2026-04-11  
Owner: Zach / Bolt  
Status: Ready for build  
Scope: three-environment deployment, broker abstraction, UAT isolation, sub-$25k live-readiness guardrails

---

## 1. Executive decision

This system should move to:

- **one codebase**
- **one Docker image**
- **three isolated runtime environments**
- **broker abstraction beneath the strategy/execution layer**
- **cash-account-aware live safety rules for sub-$25k operation**

Do **not** create three separate codebases.

That would create drift, inconsistent fixes, and false confidence when promoting changes from test to live.

The correct architecture is:

1. **DEV**: synthetic and injectable testing environment
2. **UAT**: real broker API, paper-only, production-like behavior
3. **PROD**: real-money environment, guarded and locked down

---

## 2. Build objectives

### Primary objectives
1. Separate development, paper-UAT, and production runtime concerns
2. Make broker execution pluggable instead of Alpaca-specific
3. Support future evaluation of **Interactive Brokers** and **Tradier** without rewriting core strategy code
4. Make sub-$25k live trading possible only through **cash-account-safe** controls
5. Create a clean promotion path from dev -> UAT -> prod

### Secondary objectives
1. Reduce risk of stray orders, mismatched state, and stale reconciliation
2. Allow deterministic lifecycle testing without touching a real broker
3. Make deployment, rollback, and troubleshooting environment-specific
4. Prepare the codebase for real-money supervision without enabling it prematurely

---

## 3. Non-goals

These items are explicitly out of scope for this build tranche:

1. Turning on real-money production trading
2. Building multi-broker support for every broker immediately
3. Strategy redesign or profitability research
4. Replacing current UI unless required for mode/risk visibility
5. Building a fully separate frontend per environment

---

## 4. Current-state constraints observed

Current repo facts:

- single `Dockerfile`
- single main config shape in `config.yaml`
- current live runtime is Dockerized and mounted with:
  - `/app/config/config.yaml`
  - `/app/data`
  - `/app/logs`
- current web port is `8081`
- current environment value is descriptive but not strong enough as a safety boundary
- current simulator can submit paper broker orders using Alpaca

Current architecture is good enough to evolve into a three-environment model without a repo split.

---

## 5. Target architecture

### 5.1 Runtime environments

#### DEV
Purpose:
- rapid code validation
- synthetic fills
- injected test trades
- reproducible reconciliation scenarios
- UI and API development

Rules:
- never allowed to use live broker credentials
- should default to no real external order submission
- may use fake broker adapter or simulated broker adapter

#### UAT
Purpose:
- production-like staging environment
- real broker API, but **paper only**
- final proving ground before prod promotion

Rules:
- must use paper credentials only
- must mirror prod configuration structure as closely as possible
- should be the place for smoke tests after deploys
- should be the only place real broker paper order lifecycle is validated

#### PROD
Purpose:
- live trading environment

Rules:
- locked down
- environment-specific secrets only
- strongest auth and risk limits
- live broker access only if explicitly enabled
- no dev/test injection endpoints

---

### 5.2 Deployment model

Build one image and deploy it three times as separate services:

- `daytrade-scanner-dev`
- `daytrade-scanner-uat`
- `daytrade-scanner-prod`

Each service must have:

- separate config file
- separate data directory
- separate logs directory
- separate database file
- separate secrets / env file
- separate port binding
- separate container name
- separate health target

Recommended ports:

- DEV: `8082`
- UAT: `8083`
- PROD: `8081`

---

## 6. Required repo layout changes

Create the following deployment structure:

```text
deploy/
  data/
    DAYTRADE_SCANNER_BUILD_SPEC_ENVS_BROKER_UAT_PROD.md
  shared/
    docker-compose.base.yml
  tower/
    docker-compose.yml
    .env.dev.example
    .env.uat.example
    .env.prod.example
    config/
      dev.yaml.example
      uat.yaml.example
      prod.yaml.example
```

Runtime host layout on Tower should become:

```text
/mnt/user/appdata/daytrade-scanner/
  dev/
    config/config.yaml
    data/
    logs/
  uat/
    config/config.yaml
    data/
    logs/
  prod/
    config/config.yaml
    data/
    logs/
```

Notes:
- keep each environment physically isolated at the filesystem level
- do not share sqlite DB files across environments
- do not share logs across environments
- do not share secrets files across environments

---

## 7. Config model redesign

## 7.1 Top-level environment model

Add explicit environment and execution model.

Target config shape:

```yaml
environment:
  name: dev | uat | prod
  role: development | preproduction | production

execution:
  mode: simulated | paper_broker | live_broker
  broker: alpaca | ibkr | tradier
  enable_live_trading: false
  require_startup_confirmation: true
  startup_confirmation_phrase: null

broker:
  alpaca:
    paper:
      key_id: ""
      secret_key: ""
      trading_base_url: "https://paper-api.alpaca.markets"
      data_base_url: "https://data.alpaca.markets"
      websocket_url: "wss://stream.data.alpaca.markets/v2/iex"
    live:
      key_id: ""
      secret_key: ""
      trading_base_url: "https://api.alpaca.markets"
      data_base_url: "https://data.alpaca.markets"
      websocket_url: "wss://stream.data.alpaca.markets/v2/iex"
  ibkr:
    enabled: false
    ...
  tradier:
    enabled: false
    ...

risk:
  account_mode: cash | margin
  enforce_settled_cash: true
  max_notional_per_order: 0
  max_open_positions: 0
  max_daily_loss: 0
  max_trades_per_day: 0
  allow_extended_hours: false
  require_manual_approval_for_live_entries: true

features:
  enable_trade_injection: false
  enable_debug_routes: false
  enable_manual_entry: true
  enable_emergency_stop: true
```

---

## 7.2 Environment defaults

### DEV defaults
```yaml
environment.name: dev
execution.mode: simulated
execution.broker: alpaca
execution.enable_live_trading: false
risk.account_mode: cash
features.enable_trade_injection: true
features.enable_debug_routes: true
simulator.use_alpaca_orders: false
```

### UAT defaults
```yaml
environment.name: uat
execution.mode: paper_broker
execution.broker: alpaca
execution.enable_live_trading: false
risk.account_mode: cash
features.enable_trade_injection: false
features.enable_debug_routes: false
simulator.use_alpaca_orders: true
```

### PROD defaults
```yaml
environment.name: prod
execution.mode: live_broker
execution.broker: alpaca
execution.enable_live_trading: false   # remains false until formal go-live approval
risk.account_mode: cash
features.enable_trade_injection: false
features.enable_debug_routes: false
simulator.use_alpaca_orders: true
```

Important:
- `execution.mode: live_broker` is not enough by itself
- `execution.enable_live_trading` must remain hard-disabled until formal promotion
- ambiguous config must fail closed

---

## 8. Secrets model

### Requirement
Broker and sensitive tokens must not live in committed YAML.

### Build requirements
1. Move sensitive values to env files or secrets injection
2. Config files should reference env-backed values only
3. Startup must fail if sensitive fields are missing for the selected mode

### Examples
Use env vars such as:
- `ALPACA_PAPER_KEY_ID`
- `ALPACA_PAPER_SECRET_KEY`
- `ALPACA_LIVE_KEY_ID`
- `ALPACA_LIVE_SECRET_KEY`
- `FINNHUB_API_KEY`
- `TELEGRAM_BOT_TOKEN`

### Acceptance criteria
- example configs contain placeholders only
- host runtime provides real secret values
- prod secrets are distinct from uat and dev

---

## 9. Broker abstraction design

## 9.1 Goal
Separate strategy, simulator, and reconciliation logic from broker-specific transport and payload handling.

## 9.2 New module layout
Create:

```text
src/brokers/
  __init__.py
  base.py
  models.py
  alpaca.py
  ibkr.py
  tradier.py
  factory.py
```

## 9.3 Broker interface
Create a `BrokerAdapter` interface with methods covering the minimum execution contract:

```python
class BrokerAdapter(Protocol):
    async def get_account(self) -> BrokerAccount: ...
    async def get_positions(self) -> list[BrokerPosition]: ...
    async def get_order(self, broker_order_id: str) -> BrokerOrder | None: ...
    async def list_open_orders(self) -> list[BrokerOrder]: ...
    async def submit_market_entry(self, request: EntryOrderRequest) -> BrokerOrderSubmission: ...
    async def submit_market_exit(self, request: ExitOrderRequest) -> BrokerOrderSubmission: ...
    async def cancel_order(self, broker_order_id: str) -> BrokerCancelResult: ...
    async def supports_bracket_orders(self) -> bool: ...
    async def healthcheck(self) -> BrokerHealth: ...
```

## 9.4 Shared models
Create normalized broker-domain models:
- `BrokerAccount`
- `BrokerPosition`
- `BrokerOrder`
- `BrokerOrderSubmission`
- `BrokerCancelResult`
- `BrokerHealth`
- `EntryOrderRequest`
- `ExitOrderRequest`
- `BrokerOrderState`

## 9.5 Implementation order
1. implement `base.py` and `models.py`
2. wrap current Alpaca logic into `src/brokers/alpaca.py`
3. add factory selection by config
4. refactor simulator/execution paths to call adapter only
5. add stubs for `ibkr.py` and `tradier.py`

## 9.6 Hard rule
After refactor, **no order-submission code outside broker adapters**.

---

## 10. Execution policy engine

## 10.1 Goal
Every broker order path must pass through one centralized policy gate.

Create module:

```text
src/trading/policy.py
```

## 10.2 Policy checks required
Before any entry order:
1. environment is allowed to place broker-backed orders
2. execution mode is valid
3. live trading is explicitly enabled if live mode is selected
4. broker adapter is healthy
5. account mode is compatible with requested behavior
6. settled cash is sufficient when `account_mode == cash`
7. daily loss limit not breached
8. max open positions not exceeded
9. max trades per day not exceeded
10. per-order notional cap not exceeded
11. ticker not blocked
12. manual approval satisfied when required

Before any exit order:
1. environment may submit exits
2. broker position/order state is consistent enough to act
3. emergency-stop mode may bypass some entry-only checks but not audit logging

## 10.3 Required outputs
Policy checks must return structured outcomes:
- `allowed: bool`
- `reason_code`
- `user_message`
- `audit_details`

---

## 11. Cash-account / sub-$25k safety logic

## 11.1 Why this matters
For sub-$25k trading, the real operational issue is usually not PDT in a cash account. It is **settled cash discipline** and avoiding free-riding / good-faith problems.

## 11.2 Required build items
Create module:

```text
src/trading/cash_controls.py
```

Implement:
1. settled cash snapshot ingestion from broker account data if available
2. internal ledger for:
   - starting settled cash
   - cash committed to open entries
   - cash expected from exits pending settlement
   - next-available settled funds
3. pre-trade calculation for maximum safe notional
4. rejection when requested order would exceed safe settled buying capacity
5. audit logging for every cash-based rejection

## 11.3 First version rules
For V1:
- assume `account_mode: cash`
- disallow new entries when safe settled funds are insufficient
- do not attempt margin-like behavior
- prefer false negatives over risky approvals

## 11.4 Acceptance criteria
- app can explain why an entry is blocked in cash mode
- blocked entries are visible in audit logs
- UAT can simulate these blocks deterministically

---

## 12. DEV environment features

## 12.1 Goal
Make DEV useful for rapid iteration without any chance of sending a live order.

## 12.2 Required features
1. synthetic broker adapter or simulated order backend
2. injected manual trade scenarios
3. deterministic event/reconciliation replay
4. optional seed data loader
5. obvious DEV banner in UI

## 12.3 Scenario injection routes
Add DEV-only routes for:
- create synthetic pending entry
- mark entry filled
- mark partial fill
- mark stop filled
- mark target filled
- mark rejected
- mark stale order
- inject orphan broker order
- inject unexpected broker position

These routes must be:
- unavailable in UAT and PROD
- behind explicit dev feature flags

---

## 13. UAT environment requirements

## 13.1 Goal
UAT must be production-like enough that passing UAT actually means something.

## 13.2 Requirements
1. paper broker credentials only
2. same image as prod
3. same code path as prod
4. same risk engine as prod
5. same reconciliation loop as prod
6. same startup validation as prod, except live-trading enable remains false

## 13.3 UAT smoke test checklist
After deploy, validate:
1. app health endpoint
2. websocket connects
3. manual paper entry succeeds
4. bracket/stop/target metadata appears in API/UI
5. cancel path works for unfilled entry
6. reconcile path updates state correctly
7. restart recovery works
8. emergency stop works
9. audit log records all critical actions

---

## 14. PROD environment requirements

## 14.1 Goal
Prod must default to safe, explicit, difficult-to-misconfigure behavior.

## 14.2 Requirements
1. live trading disabled by default
2. startup refusal if prod config is incomplete
3. auth required
4. strong mode banner in UI
5. no dev/test routes
6. no trade injection
7. all critical actions audited
8. emergency stop available
9. live enable must require explicit config plus confirmation phrase

## 14.3 Recommended initial prod live settings
When eventually enabled, start with:
- `account_mode: cash`
- `max_open_positions: 1`
- `max_trades_per_day: 1-3`
- `max_notional_per_order`: very low
- `max_daily_loss`: very low
- `require_manual_approval_for_live_entries: true`
- constrained trading window only

---

## 15. Docker / compose specification

## 15.1 Compose targets
Tower compose must define three services.

Example shape:

```yaml
services:
  daytrade-scanner-dev:
    image: ghcr.io/dax-assistant/daytrade-scanner:latest
    container_name: daytrade-scanner-dev
    restart: unless-stopped
    env_file:
      - .env.dev
    volumes:
      - /mnt/user/appdata/daytrade-scanner/dev/config/config.yaml:/app/config/config.yaml:ro
      - /mnt/user/appdata/daytrade-scanner/dev/data:/app/data
      - /mnt/user/appdata/daytrade-scanner/dev/logs:/app/logs
    ports:
      - "8082:8081"

  daytrade-scanner-uat:
    image: ghcr.io/dax-assistant/daytrade-scanner:latest
    container_name: daytrade-scanner-uat
    restart: unless-stopped
    env_file:
      - .env.uat
    volumes:
      - /mnt/user/appdata/daytrade-scanner/uat/config/config.yaml:/app/config/config.yaml:ro
      - /mnt/user/appdata/daytrade-scanner/uat/data:/app/data
      - /mnt/user/appdata/daytrade-scanner/uat/logs:/app/logs
    ports:
      - "8083:8081"

  daytrade-scanner-prod:
    image: ghcr.io/dax-assistant/daytrade-scanner:latest
    container_name: daytrade-scanner-prod
    restart: unless-stopped
    env_file:
      - .env.prod
    volumes:
      - /mnt/user/appdata/daytrade-scanner/prod/config/config.yaml:/app/config/config.yaml:ro
      - /mnt/user/appdata/daytrade-scanner/prod/data:/app/data
      - /mnt/user/appdata/daytrade-scanner/prod/logs:/app/logs
    ports:
      - "8081:8081"
```

## 15.2 Health checks
Each service must keep the same container health endpoint, but be externally addressable per port.

Health URLs:
- DEV: `http://host:8082/api/health`
- UAT: `http://host:8083/api/health`
- PROD: `http://host:8081/api/health`

## 15.3 Image policy
Use one promoted image tag.

Promotion pattern:
1. build image once in CI
2. deploy to DEV
3. deploy same image digest to UAT
4. deploy same image digest to PROD

Do not rebuild separately per environment.

---

## 16. Code changes by file area

## 16.1 Config
Modify:
- `src/config.py`
- `config.example.yaml`

Add:
- explicit environment model
- execution model
- broker config families
- risk/cash controls config
- feature flags per environment

## 16.2 Execution
Modify:
- `src/simulator/engine.py`
- any current Alpaca submission logic

Add:
- `src/brokers/*`
- `src/trading/policy.py`
- `src/trading/cash_controls.py`

## 16.3 Web/API
Modify:
- `src/web/routes.py`
- `src/web/static/app.js`
- possibly style files for mode banners

Add:
- environment/mode visibility endpoint if not already present
- DEV-only injection routes
- UAT/PROD protections blocking those routes

## 16.4 Startup
Modify:
- `run.py`

Add startup validation:
- reject ambiguous mode combinations
- reject live mode without required auth and secrets
- log effective environment and execution mode at boot

---

## 17. Build phases

## Phase A, Environment split
### Deliverables
- 3 config examples
- 3 env examples
- compose updated for dev/uat/prod
- separate mount layout
- UI banner showing environment and execution mode

### Acceptance criteria
- all three services run independently
- each has isolated DB/logs/config
- health endpoints pass independently

---

## Phase B, Broker abstraction
### Deliverables
- `BrokerAdapter` interface
- normalized broker models
- Alpaca adapter refactor
- broker factory

### Acceptance criteria
- core code no longer submits Alpaca orders directly
- all Alpaca order actions route through adapter

---

## Phase C, Policy engine and cash controls
### Deliverables
- centralized pre-order policy gate
- cash-account settled-funds checks
- structured rejection reasons
- audit events for policy approvals/blocks

### Acceptance criteria
- blocked trades explain exactly why they were blocked
- UAT can verify cash-account restrictions

---

## Phase D, DEV test injection framework
### Deliverables
- synthetic broker behavior routes
- event replay routes
- deterministic order-state testing

### Acceptance criteria
- can reproduce stale order, partial fill, cancel, reject, and orphan scenarios on demand

---

## Phase E, UAT hardening
### Deliverables
- paper broker lifecycle validation scripts/checklist
- restart recovery verification
- bracket/cancel/reconcile proof checklist

### Acceptance criteria
- 2+ weeks UAT stability with no unresolved reconciliation defects

---

## Phase F, Prod live-safe preparation
### Deliverables
- live config validation gates
- approval controls
- smallest-size rollout settings
- go-live checklist

### Acceptance criteria
- prod remains live-disabled until explicit approval and checklist completion

---

## 18. Testing requirements

## 18.1 Unit tests
Add tests for:
- config validation
- environment gating
- broker factory selection
- policy engine allow/deny cases
- cash-account settled-funds logic
- broker order normalization

## 18.2 Integration tests
Add tests for:
- simulated entry lifecycle
- paper order submission via adapter mock
- stale pending entry reconciliation
- cancel-before-fill path
- restart recovery path
- emergency stop path

## 18.3 Manual UAT scripts
Create a manual checklist document for:
- health
- login/auth
- order entry
- cancellation
- reconciliation
- restart recovery
- environment banner verification

---

## 19. Audit and observability requirements

Every trading-critical action must produce an audit event with:
- environment
- execution mode
- broker
- ticker
- order side
- quantity
- requested notional
- decision outcome
- policy rejection reason if blocked
- broker order id if created
- actor/source (`scanner_auto`, `manual_entry`, `reconcile`, `emergency_stop`)

Add environment labels to logs so mixed-container troubleshooting is easy.

---

## 20. Open questions to resolve during build

1. Should UAT and PROD use separate Telegram destinations or disable Telegram in DEV entirely?
2. Should PROD manual entries be disabled after initial rollout?
3. Should live entries require a second confirmation action in UI/API?
4. Which broker should be the second adapter built after Alpaca: **IBKR first** is recommended.
5. Do we want sqlite in all environments initially, or a more robust DB for PROD later?

Recommendation:
- keep sqlite for DEV/UAT initially
- allow sqlite for PROD short term only if file isolation and backup discipline are strong
- re-evaluate DB later if trading volume grows

---

## 21. Final recommendation

Build in this exact order:

1. **three-environment Docker split**
2. **config + secrets redesign**
3. **broker adapter abstraction**
4. **centralized policy engine**
5. **cash-account settled-funds protection**
6. **DEV synthetic lifecycle tooling**
7. **UAT hardening and checklist**
8. **prod live-safe gating**

If time or focus is limited, do **not** skip steps 1 through 5.
Those are the real foundation.

---

## 22. Build handoff summary

This spec is intended to be implementation-ready.

First coding tranche should produce:
- multi-environment compose layout
- config schema expansion
- environment/mode banners
- broker adapter base classes
- Alpaca adapter migration
- centralized execution policy gate

That is the minimum build slice that unlocks the rest safely.
