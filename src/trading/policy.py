from __future__ import annotations

from typing import Any, Dict

from src.config import Settings
from src.trading.models import ExecutionGuardStatus, OrderIntent, PolicyDecision, TradingPolicyError


class TradingPolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_guard_status(self) -> ExecutionGuardStatus:
        mode = self.settings.trading.mode
        broker = self.settings.trading.broker

        if mode == "paper":
            return ExecutionGuardStatus(
                mode=mode,
                broker=broker,
                allowed=True,
                reason="paper_mode",
                details={
                    "active_trading_base_url": self.settings.alpaca.paper.trading_base_url,
                    "live_enabled": False,
                    "environment": self.settings.environment,
                    "environment_role": self.settings.environment_role,
                    "account_mode": self.settings.risk.account_mode,
                    "enforce_settled_cash": self.settings.risk.enforce_settled_cash,
                    "trade_injection_enabled": self.settings.features.enable_trade_injection,
                },
            )

        live = self.settings.trading.live
        details: Dict[str, Any] = {
            "active_trading_base_url": self.settings.alpaca.live.trading_base_url,
            "live_enabled": bool(live.enabled),
            "require_web_auth": bool(live.require_web_auth),
            "require_ws_auth": bool(live.require_ws_auth),
            "require_env_secrets": bool(live.require_env_secrets),
            "max_notional_per_order": float(live.max_notional_per_order),
            "max_position_size_pct": float(live.max_position_size_pct),
            "environment": self.settings.environment,
            "environment_role": self.settings.environment_role,
            "account_mode": self.settings.risk.account_mode,
            "enforce_settled_cash": self.settings.risk.enforce_settled_cash,
            "manual_live_approval_required": self.settings.risk.require_manual_approval_for_live_entries,
        }

        if not live.enabled:
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="live_not_enabled", details=details)
        if live.require_web_auth and not self.settings.web_auth.enabled:
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="web_auth_required", details=details)
        if live.require_ws_auth and not self.settings.web.websocket_auth_enabled:
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="ws_auth_required", details=details)
        if self.settings.alpaca.live.key_id.strip() == "" or self.settings.alpaca.live.secret_key.strip() == "":
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="live_credentials_missing", details=details)
        if self.settings.alpaca.live.trading_base_url.strip() == "":
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="live_base_url_missing", details=details)
        if live.require_explicit_confirmation_phrase and live.confirmation_phrase.strip() == "":
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="confirmation_phrase_missing", details=details)
        if live.max_notional_per_order <= 0:
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="max_notional_not_configured", details=details)
        if live.max_position_size_pct <= 0:
            return ExecutionGuardStatus(mode=mode, broker=broker, allowed=False, reason="max_position_size_not_configured", details=details)

        return ExecutionGuardStatus(mode=mode, broker=broker, allowed=True, reason="execution_allowed", details=details)

    def evaluate_order_intent(self, intent: OrderIntent) -> PolicyDecision:
        status = self.get_guard_status()
        if not status.allowed:
            return PolicyDecision(
                allowed=False,
                reason_code=status.reason,
                user_message=f"execution blocked: {status.reason}",
                audit_details={"guard_status": status.to_dict(), "intent": intent.to_dict()},
            )

        max_notional = float(self.settings.risk.max_notional_per_order)
        if status.mode == "live":
            if (
                self.settings.risk.require_manual_approval_for_live_entries
                and intent.side.lower() == "buy"
                and intent.source != "manual_entry"
            ):
                return PolicyDecision(
                    allowed=False,
                    reason_code="manual_live_entry_required",
                    user_message="live buy entries require manual approval",
                    audit_details={"intent": intent.to_dict(), "guard_status": status.to_dict()},
                )
            max_notional = min(max_notional, float(self.settings.trading.live.max_notional_per_order))
            if intent.estimated_notional > max_notional:
                return PolicyDecision(
                    allowed=False,
                    reason_code="max_notional_exceeded",
                    user_message=f"estimated notional {intent.estimated_notional:.2f} exceeds cap {max_notional:.2f}",
                    audit_details={"intent": intent.to_dict(), "max_notional_allowed": max_notional},
                    max_notional_allowed=max_notional,
                )

        return PolicyDecision(
            allowed=True,
            reason_code="allowed",
            user_message="order allowed",
            audit_details={"intent": intent.to_dict(), "max_notional_allowed": max_notional},
            max_notional_allowed=max_notional,
        )

    def assert_order_allowed(self, intent: OrderIntent) -> None:
        decision = self.evaluate_order_intent(intent)
        if not decision.allowed:
            raise TradingPolicyError(f"execution_blocked:{decision.reason_code}")
