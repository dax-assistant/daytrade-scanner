from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass(frozen=True)
class AlpacaConfig:
    key_id: str
    secret_key: str
    data_base_url: str
    trading_base_url: str
    feed: str
    websocket_url: str
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


@dataclass(frozen=True)
class WebConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: List[str] = None  # type: ignore[assignment]


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
    use_alpaca_orders: bool = True
    eod_summary_telegram: bool = True
    weekly_report_telegram: bool = True
    monthly_report_telegram: bool = True
    simulated_slippage_bps: float = 10.0
    reconcile_interval_seconds: int = 30


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
class Settings:
    environment: str
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


def _req(d: Dict[str, Any], key: str) -> Any:
    if key not in d:
        raise ValueError(f"Missing required config key: {key}")
    return d[key]


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

    alpaca_cfg = AlpacaConfig(**_req(api, "alpaca"))
    finnhub_cfg = FinnhubConfig(**_req(api, "finnhub"))
    telegram_cfg = TelegramConfig(**_req(api, "telegram"))
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
    )
    web_auth_raw = web_raw.get("auth", {}) or {}
    web_auth_cfg = WebAuthConfig(
        enabled=bool(web_auth_raw.get("enabled", False)),
        username=str(web_auth_raw.get("username", "admin")),
        password=str(web_auth_raw.get("password", "")),
        session_secret=str(web_auth_raw.get("session_secret", "")),
    )

    simulator_raw = raw.get("simulator", {}) or {}
    simulator_cfg = SimulatorConfig(
        enabled=bool(simulator_raw.get("enabled", True)),
        default_risk_profile=str(simulator_raw.get("default_risk_profile", "moderate")),
        account_size=float(simulator_raw.get("account_size", 25000.0)),
        max_positions=int(simulator_raw.get("max_positions", 3)),
        max_daily_loss=float(simulator_raw.get("max_daily_loss", 500.0)),
        entry_delay_seconds=int(simulator_raw.get("entry_delay_seconds", 5)),
        use_alpaca_orders=bool(simulator_raw.get("use_alpaca_orders", True)),
        eod_summary_telegram=bool(simulator_raw.get("eod_summary_telegram", True)),
        weekly_report_telegram=bool(simulator_raw.get("weekly_report_telegram", True)),
        monthly_report_telegram=bool(simulator_raw.get("monthly_report_telegram", True)),
        simulated_slippage_bps=float(simulator_raw.get("simulated_slippage_bps", 10.0)),
        reconcile_interval_seconds=int(simulator_raw.get("reconcile_interval_seconds", 30)),
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

    log_cfg = LoggingConfig(**logging_cfg)

    settings = Settings(
        environment=str(raw.get("environment", "paper")),
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
    if settings.database.path.strip() == "":
        raise ValueError("database.path is required")
    if settings.web_auth.enabled:
        if settings.web_auth.username.strip() == "":
            raise ValueError("web.auth.username is required when web auth is enabled")
        if settings.web_auth.password.strip() == "":
            raise ValueError("web.auth.password is required when web auth is enabled")
        if settings.web_auth.session_secret.strip() == "":
            raise ValueError("web.auth.session_secret is required when web auth is enabled")
