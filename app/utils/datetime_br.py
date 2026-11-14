"""Formatação de datas no fuso de Brasília (America/Sao_Paulo)."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")


def to_brasilia(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BR_TZ)


def format_brasilia(dt: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    local = to_brasilia(dt)
    if local is None:
        return "—"
    return local.strftime(fmt)


def now_brasilia() -> datetime:
    return datetime.now(timezone.utc).astimezone(BR_TZ)
