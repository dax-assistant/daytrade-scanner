import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from run import validate_runtime_layout
from src.config import load_settings
from src.trading.models import OrderIntent
from src.trading.policy import TradingPolicy


class ConfigAndPolicyTests(unittest.TestCase):
    def write_config(self, body: str) -> str:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "config.yaml"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return str(path)

    def setUp(self):
        os.environ.setdefault("ALPACA_PAPER_KEY_ID", "paper-key")
        os.environ.setdefault("ALPACA_PAPER_SECRET_KEY", "paper-secret")
        os.environ.setdefault("FINNHUB_API_KEY", "finnhub-key")
        os.environ.setdefault("WEB_AUTH_PASSWORD", "password")
        os.environ.setdefault("WEB_AUTH_SESSION_SECRET", "session-secret")

    def test_environment_object_and_risk_features_load(self):
        config_path = self.write_config(
            """
            environment:
              name: uat
              role: preproduction
            timezone: America/New_York
            TELEGRAM_ENABLED: false
            api:
              alpaca:
                data_base_url: https://data.alpaca.markets
                feed: iex
                websocket_url: wss://stream.data.alpaca.markets/v2/iex
                paper:
                  trading_base_url: https://paper-api.alpaca.markets
                live:
                  trading_base_url: https://api.alpaca.markets
              finnhub:
                api_key: placeholder
                base_url: https://finnhub.io/api/v1
              telegram:
                bot_token: disabled
                chat_id: '1'
                base_url: https://api.telegram.org
                enabled: false
            scanner:
              active_hours: { start_hour_et: 4, end_hour_et: 16, primary_window_start_hour_et: 7, primary_window_end_hour_et: 10 }
              intervals_seconds: { premarket: 60, market_open: 30, late_day: 120, universe_refresh: 300 }
              thresholds: { min_price: 2.0, max_price: 20.0, min_gap_percent: 10.0, min_relative_volume: 5.0, max_float_shares: 10000000, min_pillars_for_alert: 5, max_news_age_hours: 24, max_candidates_per_cycle: 300, prefilter_min_gap_percent: 5.0, prefilter_min_volume: 50000, min_avg_volume_floor: 1, relative_volume_lookback_days: 20, universe_scan_multiplier: 12 }
              alert: { cooldown_minutes: 15, new_high_realert_percent: 2.0 }
            runtime:
              websocket: { enabled: true, max_symbols: 30, reconnect_max_seconds: 60 }
              rate_limits: { alpaca_calls_per_minute: 180, finnhub_calls_per_minute: 55 }
              worker: { max_concurrent_symbol_checks: 10 }
            logging:
              directory: /tmp
              scanner_hits_filename_pattern: scanner-hits-%Y-%m-%d.jsonl
              alerts_filename_pattern: alerts-%Y-%m-%d.jsonl
              app_log_filename_pattern: app-%Y-%m-%d.log
              level: INFO
            web:
              enabled: true
              host: 0.0.0.0
              port: 8081
              cors_origins: ['http://localhost:8081']
            simulator:
              enabled: true
              use_alpaca_orders: true
            database:
              path: /tmp/test.db
            trading:
              mode: paper
              broker: alpaca
            risk:
              account_mode: cash
              enforce_settled_cash: true
              max_notional_per_order: 123.45
              max_open_positions: 2
              max_daily_loss: 75
              max_trades_per_day: 4
            features:
              enable_trade_injection: true
              enable_debug_routes: true
              enable_manual_entry: true
              enable_emergency_stop: true
            """
        )

        settings = load_settings(config_path)
        self.assertEqual(settings.environment, "uat")
        self.assertEqual(settings.environment_role, "preproduction")
        self.assertEqual(settings.risk.account_mode, "cash")
        self.assertAlmostEqual(settings.risk.max_notional_per_order, 123.45)
        self.assertTrue(settings.features.enable_trade_injection)

    def test_validate_runtime_layout_rejects_live_dev(self):
        config_path = self.write_config(
            """
            environment:
              name: dev
              role: development
            timezone: America/New_York
            TELEGRAM_ENABLED: false
            api:
              alpaca:
                data_base_url: https://data.alpaca.markets
                feed: iex
                websocket_url: wss://stream.data.alpaca.markets/v2/iex
                paper:
                  trading_base_url: https://paper-api.alpaca.markets
                live:
                  trading_base_url: https://api.alpaca.markets
              finnhub:
                api_key: placeholder
                base_url: https://finnhub.io/api/v1
              telegram:
                bot_token: disabled
                chat_id: '1'
                base_url: https://api.telegram.org
                enabled: false
            scanner:
              active_hours: { start_hour_et: 4, end_hour_et: 16, primary_window_start_hour_et: 7, primary_window_end_hour_et: 10 }
              intervals_seconds: { premarket: 60, market_open: 30, late_day: 120, universe_refresh: 300 }
              thresholds: { min_price: 2.0, max_price: 20.0, min_gap_percent: 10.0, min_relative_volume: 5.0, max_float_shares: 10000000, min_pillars_for_alert: 5, max_news_age_hours: 24, max_candidates_per_cycle: 300, prefilter_min_gap_percent: 5.0, prefilter_min_volume: 50000, min_avg_volume_floor: 1, relative_volume_lookback_days: 20, universe_scan_multiplier: 12 }
              alert: { cooldown_minutes: 15, new_high_realert_percent: 2.0 }
            runtime:
              websocket: { enabled: true, max_symbols: 30, reconnect_max_seconds: 60 }
              rate_limits: { alpaca_calls_per_minute: 180, finnhub_calls_per_minute: 55 }
              worker: { max_concurrent_symbol_checks: 10 }
            logging:
              directory: /tmp
              scanner_hits_filename_pattern: scanner-hits-%Y-%m-%d.jsonl
              alerts_filename_pattern: alerts-%Y-%m-%d.jsonl
              app_log_filename_pattern: app-%Y-%m-%d.log
              level: INFO
            web:
              enabled: true
              host: 0.0.0.0
              port: 8081
              cors_origins: ['http://localhost:8081']
              websocket_auth_enabled: true
              auth: { enabled: true, username: admin, password: password, session_secret: session-secret }
            simulator:
              enabled: true
              use_alpaca_orders: true
            database:
              path: /tmp/test.db
            trading:
              mode: live
              broker: alpaca
              live:
                enabled: true
                max_notional_per_order: 150
                max_position_size_pct: 1.0
            risk:
              account_mode: cash
              max_notional_per_order: 200
              max_open_positions: 2
              max_daily_loss: 75
              max_trades_per_day: 4
            features:
              enable_trade_injection: true
              enable_debug_routes: true
            """
        )
        settings = load_settings(config_path)
        with self.assertRaisesRegex(RuntimeError, "Development environment cannot run"):
            validate_runtime_layout(settings)

    def test_policy_uses_live_notional_cap(self):
        os.environ["ALPACA_LIVE_KEY_ID"] = "live-key"
        os.environ["ALPACA_LIVE_SECRET_KEY"] = "live-secret"
        config_path = self.write_config(
            """
            environment: prod
            timezone: America/New_York
            TELEGRAM_ENABLED: false
            api:
              alpaca:
                data_base_url: https://data.alpaca.markets
                feed: iex
                websocket_url: wss://stream.data.alpaca.markets/v2/iex
                paper:
                  trading_base_url: https://paper-api.alpaca.markets
                live:
                  trading_base_url: https://api.alpaca.markets
              finnhub:
                api_key: placeholder
                base_url: https://finnhub.io/api/v1
              telegram:
                bot_token: disabled
                chat_id: '1'
                base_url: https://api.telegram.org
                enabled: false
            scanner:
              active_hours: { start_hour_et: 4, end_hour_et: 16, primary_window_start_hour_et: 7, primary_window_end_hour_et: 10 }
              intervals_seconds: { premarket: 60, market_open: 30, late_day: 120, universe_refresh: 300 }
              thresholds: { min_price: 2.0, max_price: 20.0, min_gap_percent: 10.0, min_relative_volume: 5.0, max_float_shares: 10000000, min_pillars_for_alert: 5, max_news_age_hours: 24, max_candidates_per_cycle: 300, prefilter_min_gap_percent: 5.0, prefilter_min_volume: 50000, min_avg_volume_floor: 1, relative_volume_lookback_days: 20, universe_scan_multiplier: 12 }
              alert: { cooldown_minutes: 15, new_high_realert_percent: 2.0 }
            runtime:
              websocket: { enabled: true, max_symbols: 30, reconnect_max_seconds: 60 }
              rate_limits: { alpaca_calls_per_minute: 180, finnhub_calls_per_minute: 55 }
              worker: { max_concurrent_symbol_checks: 10 }
            logging:
              directory: /tmp
              scanner_hits_filename_pattern: scanner-hits-%Y-%m-%d.jsonl
              alerts_filename_pattern: alerts-%Y-%m-%d.jsonl
              app_log_filename_pattern: app-%Y-%m-%d.log
              level: INFO
            web:
              enabled: true
              host: 0.0.0.0
              port: 8081
              cors_origins: ['http://localhost:8081']
              websocket_auth_enabled: true
              auth: { enabled: true, username: admin, password: password, session_secret: session-secret }
            simulator:
              enabled: true
              use_alpaca_orders: true
            database:
              path: /tmp/test.db
            trading:
              mode: live
              broker: alpaca
              live:
                enabled: true
                max_notional_per_order: 150
                max_position_size_pct: 1.0
            risk:
              account_mode: cash
              max_notional_per_order: 200
              max_open_positions: 2
              max_daily_loss: 75
              max_trades_per_day: 4
            """
        )
        settings = load_settings(config_path)
        policy = TradingPolicy(settings)
        allowed = policy.evaluate_order_intent(OrderIntent(symbol="AMD", side="buy", qty=1, estimated_price=10, estimated_notional=100, source="test"))
        blocked = policy.evaluate_order_intent(OrderIntent(symbol="AMD", side="buy", qty=100, estimated_price=10, estimated_notional=1000, source="test"))

        self.assertTrue(allowed.allowed)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.reason_code, "max_notional_exceeded")


if __name__ == "__main__":
    unittest.main()
