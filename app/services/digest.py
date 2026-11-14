"""Executa uma coleta: busca, seleciona notícias relevantes e envia o resumo."""

from __future__ import annotations

import logging
import threading

from app import db
from app.models import DigestRun, NewsArticle, Topic, utcnow
from app.services.email_notifier import send_digest_email
from app.services.news_collector import collect_all_topics, pending_digest_articles
from app.services.settings_service import get_recipient_emails, get_settings, touch_last_run
from app.utils.datetime_br import format_brasilia

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def run_digest() -> DigestRun | None:
    """Roda a coleta. Retorna None se outra coleta já estiver em andamento."""
    if not _lock.acquire(blocking=False):
        logger.info("Coleta já em andamento — ignorada.")
        return None

    try:
        return _run_digest_locked()
    finally:
        _lock.release()


def _run_digest_locked() -> DigestRun:
    settings = get_settings()
    log = DigestRun(status="running", started_at=utcnow(), news_found=0, news_selected=0, emails_sent=0)
    db.session.add(log)
    db.session.commit()

    try:
        topics = Topic.query.filter_by(active=True).order_by(Topic.id.asc()).all()
        if not topics:
            log.status = "error"
            log.message = "Nenhum assunto ativo. Cadastre ao menos um em Configurações."
            return log

        stats = collect_all_topics(
            topics,
            min_relevance=float(settings.min_relevance or 0.4),
            lookback_hours=int(settings.lookback_hours or 36),
        )
        log.news_found = stats["found"]

        groups = []
        chosen: list[NewsArticle] = []
        limit = int(settings.max_items_per_topic or 5)
        lookback = int(settings.lookback_hours or 36)
        for topic in topics:
            articles = pending_digest_articles(topic, limit=limit, lookback_hours=lookback)
            if articles:
                groups.append({"topic": topic.name, "articles": articles})
                chosen.extend(articles)

        log.news_selected = len(chosen)
        pieces = [f"{len(topics)} assunto(s)", f"{stats['found']} notícia(s) nova(s)"]

        if stats["errors"]:
            pieces.append("falha em: " + "; ".join(stats["errors"][:3]))

        if not groups:
            log.status = "error" if stats["errors"] and stats["found"] == 0 else "empty"
            log.message = " · ".join(pieces) + ". Nada novo para enviar."
            return log

        recipients = get_recipient_emails()
        if not recipients:
            log.status = "empty"
            log.message = (
                " · ".join(pieces)
                + f". {len(chosen)} relevante(s) aguardando destinatário de e-mail."
            )
            return log

        when_label = format_brasilia(log.started_at)
        sent = send_digest_email(groups, when_label)
        if not sent:
            log.status = "error"
            log.emails_sent = 0
            log.message = (
                " · ".join(pieces)
                + ". O e-mail não foi enviado; as notícias continuam pendentes."
            )
            return log

        sent_at = utcnow()
        for article in chosen:
            article.emailed_at = sent_at
        log.emails_sent = len(recipients)
        log.status = "ok"
        log.message = (
            " · ".join(pieces)
            + f". Resumo com {len(chosen)} notícia(s) enviado para {len(recipients)} e-mail(s)."
        )
        return log
    except Exception as exc:
        logger.exception("Falha na coleta")
        log_id = log.id
        db.session.rollback()
        log = db.session.get(DigestRun, log_id) or log
        log.status = "error"
        log.message = f"Erro na coleta: {exc}"
        return log
    finally:
        log.finished_at = utcnow()
        db.session.commit()
        touch_last_run()
