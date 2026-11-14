"""Agendamento das coletas nos horários configurados (fuso de Brasília)."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.utils.datetime_br import BR_TZ

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_app = None


def start_scheduler(app):
    global _scheduler, _app
    if _scheduler is not None:
        return _scheduler

    _app = app
    scheduler = BackgroundScheduler(daemon=True, timezone=BR_TZ)
    scheduler.start()
    _scheduler = scheduler

    with app.app_context():
        from app.services.settings_service import ensure_settings_seeded

        ensure_settings_seeded()
        reload_jobs()

    return scheduler


def reload_jobs() -> None:
    """Recria os jobs a partir dos horários ativos."""
    global _scheduler, _app
    if _scheduler is None or _app is None:
        return

    _scheduler.remove_all_jobs()

    with _app.app_context():
        from app.services.settings_service import get_settings, list_slots

        settings = get_settings()
        slots = [slot for slot in list_slots() if slot.active]
        weekdays = bool(settings.weekdays_only)

    for slot in slots:
        _scheduler.add_job(
            _scheduled_job,
            trigger=CronTrigger(
                hour=int(slot.hour),
                minute=int(slot.minute),
                day_of_week="mon-fri" if weekdays else "*",
                timezone=BR_TZ,
            ),
            id=f"digest-{slot.id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3 * 60 * 60,
        )

    logger.info(
        "Agenda atualizada — %s horário(s)%s",
        len(slots),
        " (dias úteis)" if weekdays else "",
    )


def _scheduled_job() -> None:
    if _app is None:
        return
    with _app.app_context():
        from app.services.digest import run_digest

        logger.info("Coleta agendada iniciada")
        run_digest()
