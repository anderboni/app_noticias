"""Configurações persistidas: assuntos, horários, destinatários e preferências."""

from __future__ import annotations

import re
from datetime import timedelta

from flask import current_app
from sqlalchemy import func

from app import db
from app.models import AppSettings, EmailRecipient, ScheduleSlot, Topic, utcnow
from app.utils.datetime_br import now_brasilia

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _cfg(key: str, default):
    return current_app.config.get(key, default)


def ensure_settings_seeded() -> AppSettings:
    """Garante a linha de preferências, um horário inicial e o e-mail do .env."""
    settings = db.session.get(AppSettings, 1)
    if not settings:
        settings = AppSettings(id=1)
        db.session.add(settings)
        db.session.commit()

    if ScheduleSlot.query.count() == 0:
        db.session.add(ScheduleSlot(hour=8, minute=0, active=True))
        db.session.commit()

    if EmailRecipient.query.count() == 0:
        mail_to = (str(_cfg("MAIL_TO", "")) or "").strip().lower()
        if mail_to and EMAIL_RE.match(mail_to):
            db.session.add(EmailRecipient(email=mail_to, active=True))
            db.session.commit()

    return settings


def get_settings() -> AppSettings:
    return ensure_settings_seeded()


def update_prefs(form) -> tuple[bool, str]:
    settings = get_settings()
    try:
        max_items = int(form.get("max_items_per_topic") or 5)
        lookback = int(form.get("lookback_hours") or 36)
        relevance = float(str(form.get("min_relevance") or "0.4").replace(",", "."))
    except (TypeError, ValueError):
        return False, "Informe números válidos nas preferências da coleta."

    if not 1 <= max_items <= 20:
        return False, "O máximo por assunto deve ficar entre 1 e 20."
    if not 1 <= lookback <= 168:
        return False, "A janela de horas deve ficar entre 1 e 168."
    if not 0 <= relevance <= 1:
        return False, "A relevância mínima deve ficar entre 0 e 1."

    settings.max_items_per_topic = max_items
    settings.lookback_hours = lookback
    settings.min_relevance = round(relevance, 2)
    settings.weekdays_only = form.get("weekdays_only") == "on"
    settings.updated_at = utcnow()
    db.session.commit()
    _reload_scheduler()
    return True, "Preferências da coleta salvas."


def touch_last_run() -> None:
    settings = get_settings()
    settings.last_run_at = utcnow()
    db.session.commit()


def list_topics() -> list[Topic]:
    return Topic.query.order_by(func.lower(Topic.name).asc(), Topic.id.asc()).all()


def add_topic(name: str, query: str | None) -> tuple[bool, str]:
    name = _clean_name(name)
    if not name:
        return False, "Informe o nome do assunto."
    if len(name) > 120:
        return False, "O nome do assunto deve ter no máximo 120 caracteres."
    query = _clean_query(query)
    if query and len(query) > 400:
        return False, "Os termos de busca devem ter no máximo 400 caracteres."
    if _topic_name_taken(name):
        return False, "Já existe um assunto com esse nome."
    db.session.add(Topic(name=name, search_query=query, active=True))
    db.session.commit()
    return True, f"Assunto “{name}” adicionado."


def update_topic(topic_id: int, name: str, query: str | None) -> tuple[bool, str]:
    topic = db.session.get(Topic, topic_id)
    if not topic:
        return False, "Assunto não encontrado."
    name = _clean_name(name)
    if not name:
        return False, "Informe o nome do assunto."
    if len(name) > 120:
        return False, "O nome do assunto deve ter no máximo 120 caracteres."
    query = _clean_query(query)
    if query and len(query) > 400:
        return False, "Os termos de busca devem ter no máximo 400 caracteres."
    if _topic_name_taken(name, exclude_id=topic.id):
        return False, "Já existe um assunto com esse nome."
    topic.name = name
    topic.search_query = query
    topic.updated_at = utcnow()
    db.session.commit()
    return True, f"Assunto “{name}” atualizado."


def delete_topic(topic_id: int) -> tuple[bool, str]:
    topic = db.session.get(Topic, topic_id)
    if not topic:
        return False, "Assunto não encontrado."
    name = topic.name
    db.session.delete(topic)
    db.session.commit()
    return True, f"Assunto “{name}” e as notícias dele foram removidos."


def toggle_topic(topic_id: int) -> tuple[bool, str]:
    topic = db.session.get(Topic, topic_id)
    if not topic:
        return False, "Assunto não encontrado."
    topic.active = not topic.active
    topic.updated_at = utcnow()
    db.session.commit()
    state = "ativado" if topic.active else "pausado"
    return True, f"Assunto “{topic.name}” {state}."


def list_slots() -> list[ScheduleSlot]:
    return ScheduleSlot.query.order_by(
        ScheduleSlot.hour.asc(), ScheduleSlot.minute.asc()
    ).all()


def add_slot(raw_time: str) -> tuple[bool, str]:
    parsed = _parse_time(raw_time)
    if parsed is None:
        return False, "Informe um horário válido (HH:MM)."
    hour, minute = parsed
    exists = ScheduleSlot.query.filter_by(hour=hour, minute=minute).first()
    if exists:
        return False, "Este horário já está cadastrado."
    db.session.add(ScheduleSlot(hour=hour, minute=minute, active=True))
    db.session.commit()
    _reload_scheduler()
    return True, f"Horário {hour:02d}:{minute:02d} adicionado."


def delete_slot(slot_id: int) -> tuple[bool, str]:
    slot = db.session.get(ScheduleSlot, slot_id)
    if not slot:
        return False, "Horário não encontrado."
    label = slot.label
    db.session.delete(slot)
    db.session.commit()
    _reload_scheduler()
    return True, f"Horário {label} removido."


def toggle_slot(slot_id: int) -> tuple[bool, str]:
    slot = db.session.get(ScheduleSlot, slot_id)
    if not slot:
        return False, "Horário não encontrado."
    slot.active = not slot.active
    db.session.commit()
    _reload_scheduler()
    state = "ativado" if slot.active else "pausado"
    return True, f"Horário {slot.label} {state}."


def next_run_at(slots: list[ScheduleSlot] | None = None, weekdays_only: bool | None = None):
    """Próxima execução em horário de Brasília, ou None se não houver horário ativo."""
    if slots is None:
        slots = [s for s in list_slots() if s.active]
    else:
        slots = [s for s in slots if s.active]
    if not slots:
        return None
    if weekdays_only is None:
        weekdays_only = bool(get_settings().weekdays_only)

    now = now_brasilia().replace(second=0, microsecond=0)
    for day_offset in range(0, 8):
        day = now + timedelta(days=day_offset)
        if weekdays_only and day.weekday() >= 5:
            continue
        candidates = []
        for slot in slots:
            candidate = day.replace(hour=int(slot.hour), minute=int(slot.minute))
            if candidate > now:
                candidates.append(candidate)
        if candidates:
            return min(candidates)
    return None


def list_recipients() -> list[EmailRecipient]:
    ensure_settings_seeded()
    return EmailRecipient.query.order_by(
        EmailRecipient.email.asc(), EmailRecipient.id.asc()
    ).all()


def get_recipient_emails() -> list[str]:
    return [r.email for r in list_recipients() if r.active]


def add_recipient(email: str) -> tuple[bool, str]:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return False, "E-mail inválido."
    if EmailRecipient.query.filter_by(email=email).first():
        return False, "Este e-mail já está cadastrado."
    db.session.add(EmailRecipient(email=email, active=True))
    db.session.commit()
    return True, f"{email} adicionado."


def update_recipient(recipient_id: int, email: str) -> tuple[bool, str]:
    row = db.session.get(EmailRecipient, recipient_id)
    if not row:
        return False, "Destinatário não encontrado."
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return False, "E-mail inválido."
    conflict = EmailRecipient.query.filter(
        EmailRecipient.email == email, EmailRecipient.id != recipient_id
    ).first()
    if conflict:
        return False, "Este e-mail já está cadastrado."
    row.email = email
    db.session.commit()
    return True, "E-mail atualizado."


def delete_recipient(recipient_id: int) -> tuple[bool, str]:
    row = db.session.get(EmailRecipient, recipient_id)
    if not row:
        return False, "Destinatário não encontrado."
    db.session.delete(row)
    db.session.commit()
    return True, "E-mail removido."


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def _clean_query(query: str | None) -> str | None:
    text = re.sub(r"\s+", " ", (query or "").strip())
    return text or None


def _topic_name_taken(name: str, exclude_id: int | None = None) -> bool:
    needle = name.casefold()
    for topic in Topic.query.all():
        if exclude_id is not None and topic.id == exclude_id:
            continue
        if topic.name.casefold() == needle:
            return True
    return False


def _parse_time(raw: str) -> tuple[int, int] | None:
    text = (raw or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _reload_scheduler() -> None:
    try:
        from app.services.scheduler import reload_jobs

        reload_jobs()
    except Exception:
        pass
