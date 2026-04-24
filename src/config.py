from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass(frozen=True)
class AlpacaTradingEnvConfig:
    key_id: str
    secret_key: str
    trading_base_url: str


@dataclass(frozen=True)
class AlpacaConfig:
    data_base_url: str
    feed: str
    websocket_url: str
    paper: AlpacaTradingEnvConfig
    live: AlpacaTradingEnvConfig
    request_timeout_seconds: int = 15


@dataclass(frozen=True)
class FinnhubConfig:
    api_key: str
    base_url: str
    request_timeout_seconds: int = 15


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    base_url: str
    enabled: bool = True


@dataclass(frozen=True)
class ActiveHoursConfig:
    start_hour_et: int
    end_hour_et: int
    primary_window_start_hour_et: int = 7
    primary_window_end_hour_et: int = 10


@dataclass(frozen=True)
class IntervalsConfig:
    premarket: int
    market_open: int
    late_day: int
    universe_refresh: int


@dataclass(frozen=True)
class ThresholdsConfig:
    min_price: float
    max_price: float
    min_gap_percent: float
    min_relative_volume: float
    max_float_shares: int
    min_pillars_for_alert: int
    max_news_age_hours: int
    max_candidates_per_cycle: int
    prefilter_min_gap_percent: float
    prefilter_min_volume: int
    min_avg_volume_floor: int
    relative_volume_lookback_days: int = 20
    universe_scan_multiplier: int = 12


@dataclass(frozen=True)
class AlertConfig:
    cooldown_minutes: int
    new_high_realert_percent: float


@dataclass(frozen=True)
class ScannerConfig:
    active_hours: ActiveHoursConfig
    intervals_seconds: IntervalsConfig
    thresholds: ThresholdsConfig
    alert: AlertConfig


@dataclass(frozen=True)
class WebsocketRuntimeConfig:
    enabled: bool
    max_symbols: int
    reconnect_max_seconds: int


@dataclass(frozen=True)
class RateLimitConfig:
    alpaca_calls_per_minute: int
    finnhub_calls_per_minute: int


@dataclass(frozen=True)
class WorkerConfig:
    max_concurrent_symbol_checks: int


@dataclass(frozen=True)
class RuntimeConfig:
    websocket: WebsocketRuntimeConfig
    rate_limits: RateLimitConfig
    worker: WorkerConfig


@dataclass(frozen=True)
class LoggingConfig:
    directory: str
    scanner_hits_filename_pattern: str
    alerts_filename_pattern: str
    app_log_filename_pattern: str
    level: str
    audit_filename_pattern: str = "audit-%Y-%m-%d.jsonl"


@dataclass(frozen=True)
class WebConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: List[str] = None  # type: ignore[assignment]
    websocket_auth_enabled: bool = False


@dataclass(frozen=True)
class WebAuthConfig:
    enabled: bool = False
    username: str = "admin"
    password: str = ""
    session_secret: str = ""


@dataclass(frozen=True)
class SimulatorConfig:
    enabled: bool = True
    default_risk_profile: str = "moderate"
    account_size: float = 25000.0
    max_positions: int = 3
    max_daily_loss: float = 500.0
    entry_delay_seconds: int = 5
    min_pillars_for_entry: int = 1
    use_alpaca_orders: bool = True
    eod_summary_telegram: bool = True
    weekly_report_telegram: bool = True
    monthly_report_telegram: bool = True
    simulated_slippage_bps: float = 10.0
    reconcile_interval_seconds: int = 30
    pending_order_stale_seconds: int = 120
    reconciliation_position_mismatch_seconds: int = 90


@dataclass(frozen=True)
class RiskProfileConfig:
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop: bool
    trailing_stop_pct: float
    max_hold_minutes: int


@dataclass(frozen=True)
class DatabaseConfig:
    path: str = "./scanner.db"


@dataclass(frozen=True)
class TradingPaperConfig:
    enabled: bool = True


@dataclass(frozen=True)
class TradingLiveConfig:
    enabled: bool = False
    require_web_auth: bool = True
    require_ws_auth: bool = True
    require_env_secrets: bool = True
    require_explicit_confirmation_phrase: bool = True
    confirmation_phrase: str = "ENABLE LIVE TRADING"
    max_notional_per_order: float = 500.0
    max_position_size_pct: float = 1.0


@dataclass(frozen=True)
class TradingConfig:
    mode: str = "paper"
    broker: str = "alpaca"
    paper: TradingPaperConfig = field(default_factory=TradingPaperConfig)
    live: TradingLiveConfig = field(default_factory=TradingLiveConfig)


@dataclass(frozen=True)
class RiskConfig:
    account_mode: str = "cash"
    enforce_settled_cash: bool = True
    max_notional_per_order: float = 500.0
    max_open_positions: int = 3
    max_daily_loss: float = 500.0
    max_trades_per_day: int = 10
    allow_extended_hours: bool = False
    require_manual_approval_for_live_entries: bool = True


@dataclass(frozen=True)
class FeaturesConfig:
    enable_trade_injection: bool = False
    enable_debug_routes: bool = False
    enable_manual_entry: bool = True
    enable_emergency_stop: bool = True


@dataclass(frozen=True)
class Settings:
    environment: str
    environment_role: str
    timezone: str
    alpaca: AlpacaConfig
    finnhub: FinnhubConfig
    telegram: TelegramConfig
    telegram_enabled: bool
    scanner: ScannerConfig
    runtime: RuntimeConfig
    logging: LoggingConfig
    web: WebConfig
    web_auth: WebAuthConfig
    simulator: SimulatorConfig
    risk_profiles: Dict[str, RiskProfileConfig]
    database: DatabaseConfig
    trading: TradingConfig
    risk: RiskConfig
    features: FeaturesConfig


def _req(d: Dict[str, Any], key: str) -> Any:
    if key not in d:
        raise ValueError(f"Missing required config key: {key}")
    return d[key]


def _get_env_secret_name(prefix: str, mode: str, field: str) -> str:
    return f"{prefix}_{mode.upper()}_{field.upper()}"


def _resolve_secret(*env_names: str, fallback: str = "") -> str:
    for env_name in env_names:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return str(fallback or "").strip()


def _build_alpaca_config(raw_api: Dict[str, Any]) -> AlpacaConfig:
    alpaca_raw = dict(_req(raw_api, "alpaca"))

    data_base_url = str(alpaca_raw.get("data_base_url", "https://data.alpaca.markets"))
    feed = str(alpaca_raw.get("feed", "iex"))
    websocket_url = str(alpaca_raw.get("websocket_url", "wss://stream.data.alpaca.markets/v2/iex"))
    request_timeout_seconds = int(alpaca_raw.get("request_timeout_seconds", 15))

    if isinstance(alpaca_raw.get("paper"), dict) or isinstance(alpaca_raw.get("live"), dict):
        paper_raw = dict(alpaca_raw.get("paper", {}) or {})
        live_raw = dict(alpaca_raw.get("live", {}) or {})
    else:
        # Backward compatibility: treat legacy flat config as paper config.
        paper_raw = {
            "key_id": str(alpaca_raw.get("key_id", "")),
            "secret_key": str(alpaca_raw.get("secret_key", "")),
            "trading_base_url": str(alpaca_raw.get("trading_base_url", "https://paper-api.alpaca.markets")),
        }
        live_raw = {
            "key_id": "",
            "secret_key": "",
            "trading_base_url": "https://api.alpaca.markets",
        }

    paper_cfg = AlpacaTradingEnvConfig(
        key_id=_resolve_secret("ALPACA_PAPER_KEY_ID", fallback=str(paper_raw.get("key_id", ""))),
        secret_key=_resolve_secret("ALPACA_PAPER_SECRET_KEY", fallback=str(paper_raw.get("secret_key", ""))),
        trading_base_url=str(paper_raw.get("trading_base_url", "https://paper-api.alpaca.markets")),
    )
    live_cfg = AlpacaTradingEnvConfig(
        key_id=_resolve_secret("ALPACA_LIVE_KEY_ID", fallback=str(live_raw.get("key_id", ""))),
        secret_key=_resolve_secret("ALPACA_LIVE_SECRET_KEY", fallback=str(live_raw.get("secret_key", ""))),
        trading_base_url=str(live_raw.get("trading_base_url", "https://api.alpaca.markets")),
    )

    return AlpacaConfig(
        data_base_url=data_base_url,
        feed=feed,
        websocket_url=websocket_url,
        paper=paper_cfg,
        live=live_cfg,
        request_timeout_seconds=request_timeout_seconds,
    )


def load_settings(config_path: str | Path) -> Settings:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    api = _req(raw, "api")
    scanner = _req(raw, "scanner")
    runtime = _req(raw, "runtime")
    logging_cfg = _req(raw, "logging")

    alpaca_cfg = _build_alpaca_config(api)
    finnhub_raw = dict(_req(api, "finnhub"))
    finnhub_cfg = FinnhubConfig(
        api_key=_resolve_secret("FINNHUB_API_KEY", fallback=str(finnhub_raw.get("api_key", ""))),
        base_url=str(finnhub_raw.get("base_url", "https://finnhub.io/api/v1")),
        request_timeout_seconds=int(finnhub_raw.get("request_timeout_seconds", 15)),
    )
    telegram_raw = dict(_req(api, "telegram"))
    telegram_cfg = TelegramConfig(
        bot_token=_resolve_secret("TELEGRAM_BOT_TOKEN", fallback=str(telegram_raw.get("bot_token", ""))),
        chat_id=str(telegram_raw.get("chat_id", "")),
        base_url=str(telegram_raw.get("base_url", "https://api.telegram.org")),
        enabled=bool(telegram_raw.get("enabled", True)),
    )
    telegram_enabled = bool(raw.get("TELEGRAM_ENABLED", telegram_cfg.enabled))

    scanner_cfg = ScannerConfig(
        active_hours=ActiveHoursConfig(**_req(scanner, "active_hours")),
        intervals_seconds=IntervalsConfig(**_req(scanner, "intervals_seconds")),
        thresholds=ThresholdsConfig(**_req(scanner, "thresholds")),
        alert=AlertConfig(**_req(scanner, "alert")),
    )

    runtime_cfg = RuntimeConfig(
        websocket=WebsocketRuntimeConfig(**_req(runtime, "websocket")),
        rate_limits=RateLimitConfig(**_req(runtime, "rate_limits")),
        worker=WorkerConfig(**_req(runtime, "worker")),
    )

    web_raw = raw.get("web", {}) or {}
    web_cfg = WebConfig(
        enabled=bool(web_raw.get("enabled", True)),
        host=str(web_raw.get("host", "0.0.0.0")),
        port=int(web_raw.get("port", 8080)),
        cors_origins=list(web_raw.get("cors_origins", ["*"])),
        websocket_auth_enabled=bool(web_raw.get("websocket_auth_enabled", False)),
    )
    web_auth_raw = web_raw.get("auth", {}) or {}
    web_auth_cfg = WebAuthConfig(
        enabled=bool(web_auth_raw.get("enabled", False)),
        username=str(web_auth_raw.get("username", "admin")),
        password=_resolve_secret("WEB_AUTH_PASSWORD", fallback=str(web_auth_raw.get("password", ""))),
        session_secret=_resolve_secret("WEB_AUTH_SESSION_SECRET", fallback=str(web_auth_raw.get("session_secret", ""))),
    )

    simulator_raw = raw.get("simulator", {}) or {}
    simulator_cfg = SimulatorConfig(
        enabled=bool(simulator_raw.get("enabled", True)),
        default_risk_profile=str(simulator_raw.get("default_risk_profile", "moderate")),
        account_size=float(simulator_raw.get("account_size", 25000.0)),
        max_positions=int(simulator_raw.get("max_positions", 3)),
        max_daily_loss=float(simulator_raw.get("max_daily_loss", 500.0)),
        entry_delay_seconds=int(simulator_raw.get("entry_delay_seconds", 5)),
        min_pillars_for_entry=int(simulator_raw.get("min_pillars_for_entry", 1)),
        use_alpaca_orders=bool(simulator_raw.get("use_alpaca_orders", True)),
        eod_summary_telegram=bool(simulator_raw.get("eod_summary_telegram", True)),
        weekly_report_telegram=bool(simulator_raw.get("weekly_report_telegram", True)),
        monthly_report_telegram=bool(simulator_raw.get("monthly_report_telegram", True)),
        simulated_slippage_bps=float(simulator_raw.get("simulated_slippage_bps", 10.0)),
        reconcile_interval_seconds=int(simulator_raw.get("reconcile_interval_seconds", 30)),
        pending_order_stale_seconds=int(simulator_raw.get("pending_order_stale_seconds", 120)),
        reconciliation_position_mismatch_seconds=int(simulator_raw.get("reconciliation_position_mismatch_seconds", 90)),
    )

    default_risk_profiles = {
        "conservative": {
            "position_size_pct": 2.0,
            "stop_loss_pct": 3.0,
            "take_profit_pct": 5.0,
            "trailing_stop": False,
            "trailing_stop_pct": 0.0,
            "max_hold_minutes": 30,
        },
        "moderate": {
            "position_size_pct": 5.0,
            "stop_loss_pct": 5.0,
            "take_profit_pct": 10.0,
            "trailing_stop": False,
            "trailing_stop_pct": 0.0,
            "max_hold_minutes": 60,
        },
        "aggressive": {
            "position_size_pct": 10.0,
            "stop_loss_pct": 7.0,
            "take_profit_pct": 0.0,
            "trailing_stop": True,
            "trailing_stop_pct": 5.0,
            "max_hold_minutes": 120,
        },
    }
    raw_profiles = raw.get("risk_profiles", default_risk_profiles)
    risk_profiles = {
        name: RiskProfileConfig(**cfg)
        for name, cfg in raw_profiles.items()
        if isinstance(cfg, dict)
    }

    database_raw = raw.get("database", {}) or {}
    database_cfg = DatabaseConfig(path=str(database_raw.get("path", "./scanner.db")))

    trading_raw = raw.get("trading", {}) or {}
    trading_cfg = TradingConfig(
        mode=str(trading_raw.get("mode", "paper")).strip().lower() or "paper",
        broker=str(trading_raw.get("broker", "alpaca")).strip().lower() or "alpaca",
        paper=TradingPaperConfig(**(trading_raw.get("paper", {}) or {})),
        live=TradingLiveConfig(**(trading_raw.get("live", {}) or {})),
    )

    environment_raw = raw.get("environment", "paper")
    if isinstance(environment_raw, dict):
        environment_name = str(environment_raw.get("name", "paper"))
        environment_role = str(environment_raw.get("role", "development"))
    else:
        environment_name = str(environment_raw)
        role_map = {
            "dev": "development",
            "development": "development",
            "uat": "preproduction",
            "paper": "preproduction",
            "prod": "production",
            "production": "production",
            "live": "production",
        }
        environment_role = role_map.get(environment_name.strip().lower(), "development")

    risk_raw = raw.get("risk", {}) or {}
    risk_cfg = RiskConfig(
        account_mode=str(risk_raw.get("account_mode", "cash")).strip().lower() or "cash",
        enforce_settled_cash=bool(risk_raw.get("enforce_settled_cash", True)),
        max_notional_per_order=float(risk_raw.get("max_notional_per_order", trading_cfg.live.max_notional_per_order)),
        max_open_positions=int(risk_raw.get("max_open_positions", simulator_cfg.max_positions)),
        max_daily_loss=float(risk_raw.get("max_daily_loss", simulator_cfg.max_daily_loss)),
        max_trades_per_day=int(risk_raw.get("max_trades_per_day", 10)),
        allow_extended_hours=bool(risk_raw.get("allow_extended_hours", False)),
        require_manual_approval_for_live_entries=bool(risk_raw.get("require_manual_approval_for_live_entries", True)),
    )

    features_raw = raw.get("features", {}) or {}
    features_cfg = FeaturesConfig(
        enable_trade_injection=bool(features_raw.get("enable_trade_injection", False)),
        enable_debug_routes=bool(features_raw.get("enable_debug_routes", False)),
        enable_manual_entry=bool(features_raw.get("enable_manual_entry", True)),
        enable_emergency_stop=bool(features_raw.get("enable_emergency_stop", True)),
    )

    log_cfg = LoggingConfig(**logging_cfg)

    settings = Settings(
        environment=environment_name,
        environment_role=environment_role,
        timezone=str(raw.get("timezone", "America/New_York")),
        alpaca=alpaca_cfg,
        finnhub=finnhub_cfg,
        telegram=telegram_cfg,
        telegram_enabled=telegram_enabled,
        scanner=scanner_cfg,
        runtime=runtime_cfg,
        logging=log_cfg,
        web=web_cfg,
        web_auth=web_auth_cfg,
        simulator=simulator_cfg,
        risk_profiles=risk_profiles,
        database=database_cfg,
        trading=trading_cfg,
        risk=risk_cfg,
        features=features_cfg,
    )

    _validate_settings(settings)
    return settings


def _validate_settings(settings: Settings) -> None:
    t = settings.scanner.thresholds
    if t.min_price >= t.max_price:
        raise ValueError("scanner.thresholds.min_price must be < max_price")
    if t.min_pillars_for_alert < 1 or t.min_pillars_for_alert > 5:
        raise ValueError("scanner.thresholds.min_pillars_for_alert must be between 1 and 5")
    if t.relative_volume_lookback_days < 2:
        raise ValueError("scanner.thresholds.relative_volume_lookback_days must be >= 2")
    if t.universe_scan_multiplier < 1:
        raise ValueError("scanner.thresholds.universe_scan_multiplier must be >= 1")
    if settings.scanner.active_hours.start_hour_et >= settings.scanner.active_hours.end_hour_et:
        raise ValueError("scanner.active_hours.start_hour_et must be before end_hour_et")
    if settings.scanner.active_hours.primary_window_start_hour_et >= settings.scanner.active_hours.primary_window_end_hour_et:
        raise ValueError("scanner.active_hours.primary_window_start_hour_et must be before primary_window_end_hour_et")
    if settings.simulator.max_positions < 1:
        raise ValueError("simulator.max_positions must be >= 1")
    if settings.simulator.simulated_slippage_bps < 0:
        raise ValueError("simulator.simulated_slippage_bps must be >= 0")
    if settings.simulator.reconcile_interval_seconds < 5:
        raise ValueError("simulator.reconcile_interval_seconds must be >= 5")
    if settings.simulator.pending_order_stale_seconds < settings.simulator.reconcile_interval_seconds:
        raise ValueError("simulator.pending_order_stale_seconds must be >= simulator.reconcile_interval_seconds")
    if settings.simulator.reconciliation_position_mismatch_seconds < settings.simulator.reconcile_interval_seconds:
        raise ValueError("simulator.reconciliation_position_mismatch_seconds must be >= simulator.reconcile_interval_seconds")
    if settings.database.path.strip() == "":
        raise ValueError("database.path is required")
    if settings.environment.strip() == "":
        raise ValueError("environment is required")
    if settings.environment_role not in {"development", "preproduction", "production"}:
        raise ValueError("environment.role must be development, preproduction, or production")
    if settings.finnhub.api_key.strip() == "":
        raise ValueError("api.finnhub.api_key is required")
    if settings.telegram_enabled and settings.telegram.bot_token.strip() == "":
        raise ValueError("api.telegram.bot_token is required when Telegram is enabled")
    if settings.web_auth.enabled:
        if settings.web_auth.username.strip() == "":
            raise ValueError("web.auth.username is required when web auth is enabled")
        if settings.web_auth.password.strip() == "":
            raise ValueError("web.auth.password is required when web auth is enabled")
        if settings.web_auth.session_secret.strip() == "":
            raise ValueError("web.auth.session_secret is required when web auth is enabled")
        if "*" in settings.web.cors_origins:
            raise ValueError("web.cors_origins cannot include '*' when web auth is enabled")
    if settings.web.websocket_auth_enabled and not settings.web_auth.enabled:
        raise ValueError("web.auth.enabled must be true when web.websocket_auth_enabled is enabled")

    if settings.trading.mode not in {"paper", "live"}:
        raise ValueError("trading.mode must be 'paper' or 'live'")
    if not (1 <= settings.simulator.min_pillars_for_entry <= 5):
        raise ValueError("simulator.min_pillars_for_entry must be between 1 and 5")
    if settings.trading.broker != "alpaca":
        raise ValueError("trading.broker must currently be 'alpaca'")
    if settings.risk.account_mode not in {"cash", "margin"}:
        raise ValueError("risk.account_mode must be 'cash' or 'margin'")
    if settings.risk.max_notional_per_order <= 0:
        raise ValueError("risk.max_notional_per_order must be > 0")
    if settings.risk.max_open_positions < 1:
        raise ValueError("risk.max_open_positions must be >= 1")
    if settings.risk.max_daily_loss <= 0:
        raise ValueError("risk.max_daily_loss must be > 0")
    if settings.risk.max_trades_per_day < 1:
        raise ValueError("risk.max_trades_per_day must be >= 1")
    if settings.alpaca.paper.trading_base_url.strip() == "":
        raise ValueError("api.alpaca.paper.trading_base_url is required")
    if settings.alpaca.paper.key_id.strip() == "":
        raise ValueError("api.alpaca.paper.key_id is required")
    if settings.alpaca.paper.secret_key.strip() == "":
        raise ValueError("api.alpaca.paper.secret_key is required")

    if settings.trading.mode == "live":
        live = settings.trading.live
        if not live.enabled:
            raise ValueError("trading.live.enabled must be true when trading.mode is 'live'")
        if settings.alpaca.live.trading_base_url.strip() == "":
            raise ValueError("api.alpaca.live.trading_base_url is required in live mode")
        if settings.alpaca.live.key_id.strip() == "":
            raise ValueError("api.alpaca.live.key_id is required in live mode")
        if settings.alpaca.live.secret_key.strip() == "":
            raise ValueError("api.alpaca.live.secret_key is required in live mode")
        if live.require_web_auth and not settings.web_auth.enabled:
            raise ValueError("web.auth.enabled must be true in live mode")
        if live.require_ws_auth and not settings.web.websocket_auth_enabled:
            raise ValueError("web.websocket_auth_enabled must be true in live mode")
        if live.require_explicit_confirmation_phrase and live.confirmation_phrase.strip() == "":
            raise ValueError("trading.live.confirmation_phrase is required in live mode")
        if live.max_notional_per_order <= 0:
            raise ValueError("trading.live.max_notional_per_order must be > 0 in live mode")
        if live.max_position_size_pct <= 0:
            raise ValueError("trading.live.max_position_size_pct must be > 0 in live mode")
        if live.require_env_secrets:
            required_envs = [
                _get_env_secret_name("ALPACA", "LIVE", "KEY_ID"),
                _get_env_secret_name("ALPACA", "LIVE", "SECRET_KEY"),
            ]
            missing = [name for name in required_envs if not os.getenv(name, "").strip()]
            if missing:
                missing_csv = ", ".join(missing)
                raise ValueError(f"Live mode requires environment secrets: {missing_csv}")
