from __future__ import annotations

from typing import Dict

from src.config import Settings
from src.data.models import RiskProfile


def load_risk_profiles(settings: Settings) -> Dict[str, RiskProfile]:
    profiles: Dict[str, RiskProfile] = {}
    for name, cfg in settings.risk_profiles.items():
        profiles[name] = RiskProfile(
            name=name,
            position_size_pct=float(cfg.position_size_pct),
            stop_loss_pct=float(cfg.stop_loss_pct),
            take_profit_pct=float(cfg.take_profit_pct),
            trailing_stop=bool(cfg.trailing_stop),
            trailing_stop_pct=float(cfg.trailing_stop_pct),
            max_hold_minutes=int(cfg.max_hold_minutes),
        )
    return profiles


def get_profile(profiles: Dict[str, RiskProfile], name: str) -> RiskProfile:
    if name in profiles:
        return profiles[name]
    if "moderate" in profiles:
        return profiles["moderate"]
    if profiles:
        return next(iter(profiles.values()))
    raise ValueError("No risk profiles configured")
