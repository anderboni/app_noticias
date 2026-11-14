"""Painel web local (sem login)."""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.models import DigestRun, NewsArticle, Topic
from app.services.digest import run_digest

bp = Blueprint("main", __name__)


def _finish_collect():
    log = run_digest()
    if log is None:
        flash("Já existe uma coleta em andamento.", "info")
    elif log.status == "ok":
        flash(log.message, "success")
    elif log.status == "empty":
        flash(log.message, "info")
    else:
        flash(log.message or "A coleta falhou.", "error")


@bp.route("/")
def index():
    from app.services.settings_service import (
        get_recipient_emails,
        get_settings,
        list_slots,
        list_topics,
        next_run_at,
    )

    settings = get_settings()
    topics = list_topics()
    slots = list_slots()
    last_run = DigestRun.query.order_by(DigestRun.started_at.desc()).first()
    recent = (
        NewsArticle.query.options(joinedload(NewsArticle.topic))
        .filter(NewsArticle.selected.is_(True))
        .order_by(NewsArticle.collected_at.desc())
        .limit(8)
        .all()
    )
    runs = DigestRun.query.order_by(DigestRun.started_at.desc()).limit(6).all()
    return render_template(
        "index.html",
        topics=topics,
        active_topics=sum(1 for topic in topics if topic.active),
        slots=slots,
        next_run=next_run_at(slots, settings.weekdays_only),
        weekdays_only=settings.weekdays_only,
        recipient_count=len(get_recipient_emails()),
        last_run=last_run,
        recent=recent,
        runs=runs,
        mail_enabled=current_app.config.get("MAIL_ENABLED"),
        settings=settings,
    )


@bp.route("/noticias")
def noticias():
    from app.services.settings_service import list_topics

    topic_id = request.args.get("assunto", type=int)
    topics = list_topics()
    query = NewsArticle.query.options(joinedload(NewsArticle.topic))
    if topic_id:
        query = query.filter(NewsArticle.topic_id == topic_id)
    articles = query.order_by(NewsArticle.collected_at.desc()).limit(150).all()
    current = next((topic for topic in topics if topic.id == topic_id), None)
    return render_template(
        "noticias.html",
        articles=articles,
        topics=topics,
        current_topic=current,
    )


@bp.route("/coletar", methods=["POST"])
def coletar():
    _finish_collect()
    nxt = (request.form.get("next") or "").strip()
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = url_for("main.index")
    return redirect(nxt)


@bp.route("/configuracoes", methods=["GET", "POST"])
def configuracoes():
    from app.services import settings_service as settings

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        ok, message = _apply_settings_action(settings, action)
        if message:
            flash(message, "success" if ok else "error")
        return redirect(url_for("main.configuracoes"))

    topics = settings.list_topics()
    counts = dict(
        db.session.query(NewsArticle.topic_id, func.count(NewsArticle.id))
        .group_by(NewsArticle.topic_id)
        .all()
    )
    for topic in topics:
        topic.news_count = counts.get(topic.id, 0)

    prefs = settings.get_settings()
    return render_template(
        "configuracoes.html",
        topics=topics,
        slots=settings.list_slots(),
        recipients=settings.list_recipients(),
        prefs=prefs,
        mail_enabled=current_app.config.get("MAIL_ENABLED"),
    )


def _apply_settings_action(settings, action: str) -> tuple[bool, str]:
    if action == "add_topic":
        return settings.add_topic(request.form.get("name") or "", request.form.get("query"))
    if action == "edit_topic":
        try:
            topic_id = int(request.form.get("topic_id") or "0")
        except ValueError:
            return False, "Assunto inválido."
        return settings.update_topic(
            topic_id, request.form.get("name") or "", request.form.get("query")
        )
    if action == "delete_topic":
        try:
            topic_id = int(request.form.get("topic_id") or "0")
        except ValueError:
            return False, "Assunto inválido."
        return settings.delete_topic(topic_id)
    if action == "toggle_topic":
        try:
            topic_id = int(request.form.get("topic_id") or "0")
        except ValueError:
            return False, "Assunto inválido."
        return settings.toggle_topic(topic_id)
    if action == "add_schedule":
        return settings.add_slot(request.form.get("run_time") or "")
    if action == "delete_schedule":
        try:
            slot_id = int(request.form.get("slot_id") or "0")
        except ValueError:
            return False, "Horário inválido."
        return settings.delete_slot(slot_id)
    if action == "toggle_schedule":
        try:
            slot_id = int(request.form.get("slot_id") or "0")
        except ValueError:
            return False, "Horário inválido."
        return settings.toggle_slot(slot_id)
    if action == "save_prefs":
        return settings.update_prefs(request.form)
    if action == "add_email":
        return settings.add_recipient(request.form.get("email") or "")
    if action == "edit_email":
        try:
            recipient_id = int(request.form.get("recipient_id") or "0")
        except ValueError:
            return False, "Destinatário inválido."
        return settings.update_recipient(recipient_id, request.form.get("email") or "")
    if action == "delete_email":
        try:
            recipient_id = int(request.form.get("recipient_id") or "0")
        except ValueError:
            return False, "Destinatário inválido."
        return settings.delete_recipient(recipient_id)
    return False, "Ação desconhecida."


@bp.route("/configuracoes/test-email", methods=["POST"])
def test_email():
    from app.services.email_notifier import send_test_email

    ok, message = send_test_email()
    flash(message, "success" if ok else "error")
    return redirect(url_for("main.configuracoes"))
