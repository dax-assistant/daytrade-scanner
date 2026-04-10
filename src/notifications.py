from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class NotificationRouter:
    """Routes notifications to web clients and optionally Telegram."""

    def __init__(self, telegram_alerter: Any, ws_manager: Any, telegram_enabled: bool = True) -> None:
        self.telegram_alerter = telegram_alerter
        self.ws_manager = ws_manager
        self.telegram_enabled = bool(telegram_enabled)

    async def start(self) -> None:
        await self.telegram_alerter.start()

    async def close(self) -> None:
        await self.telegram_alerter.close()

    def set_telegram_enabled(self, enabled: bool) -> None:
        self.telegram_enabled = bool(enabled)

    def get_settings(self) -> Dict[str, bool]:
        return {"telegram_enabled": self.telegram_enabled}

    async def send_scanner_hit(self, candidate: Any) -> Dict[str, str]:
        message = self.telegram_alerter.format_scanner_hit(candidate)
        data = candidate.to_dict() if hasattr(candidate, "to_dict") else {"ticker": getattr(candidate, "ticker", "")}
        return await self._send_alert(
            alert_type="scanner_alert",
            message=message,
            data=data,
            telegram_callable=(lambda: self.telegram_alerter.send_scanner_hit(candidate)),
        )

    async def send_system_message(self, text: str) -> Dict[str, str]:
        return await self._send_alert(
            alert_type="system",
            message=text,
            data={},
            telegram_callable=(lambda: self.telegram_alerter.send_system_message(text)),
        )

    async def send_trade_alert(self, trade: Any, action: str) -> Dict[str, str]:
        message = self.telegram_alerter.format_trade_alert(trade, action)
        payload = trade.to_dict() if hasattr(trade, "to_dict") else {"action": action}
        payload["action"] = action
        return await self._send_alert(
            alert_type="trade_signal",
            message=message,
            data=payload,
            telegram_callable=(lambda: self.telegram_alerter.send_trade_alert(trade, action)),
        )

    async def send_eod_summary(self, summary: Any) -> Dict[str, str]:
        message = self.telegram_alerter.format_eod_summary(summary)
        payload = summary.to_dict() if hasattr(summary, "to_dict") else {}
        return await self._send_alert(
            alert_type="eod_summary",
            message=message,
            data=payload,
            telegram_callable=(lambda: self.telegram_alerter.send_eod_summary(summary)),
        )

    async def send_weekly_report(self, text: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        return await self._send_alert(
            alert_type="weekly_report",
            message=text,
            data=data or {},
            telegram_callable=(lambda: self.telegram_alerter.send_system_message(text)),
        )

    async def send_monthly_report(self, text: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        return await self._send_alert(
            alert_type="monthly_report",
            message=text,
            data=data or {},
            telegram_callable=(lambda: self.telegram_alerter.send_system_message(text)),
        )

    async def _send_alert(
        self,
        alert_type: str,
        message: str,
        data: Dict[str, Any],
        telegram_callable,
    ) -> Dict[str, str]:
        timestamp = datetime.now(timezone.utc).timestamp()

        await self.ws_manager.broadcast_alert(
            {
                "type": alert_type,
                "message": message,
                "data": data,
                "timestamp": timestamp,
            }
        )

        if not self.telegram_enabled:
            return {
                "status": "web_only",
                "message_id": "",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }

        return await telegram_callable()
