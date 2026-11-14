"""API JSON local."""

from flask import Blueprint, jsonify

from app.models import DigestRun, NewsArticle, Topic
from app.services.digest import run_digest

bp = Blueprint("api", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "topics": Topic.query.count()})


@bp.get("/topics")
def topics():
    rows = Topic.query.order_by(Topic.name.asc()).all()
    return jsonify(
        [
            {
                "id": topic.id,
                "name": topic.name,
                "query": topic.search_query,
                "active": topic.active,
            }
            for topic in rows
        ]
    )


@bp.get("/news")
def news():
    topic_id = None
    from flask import request

    raw = request.args.get("assunto")
    if raw:
        try:
            topic_id = int(raw)
        except ValueError:
            topic_id = None

    query = NewsArticle.query.order_by(NewsArticle.collected_at.desc())
    if topic_id:
        query = query.filter_by(topic_id=topic_id)
    rows = query.limit(80).all()
    return jsonify(
        [
            {
                "id": article.id,
                "topic_id": article.topic_id,
                "title": article.title,
                "summary": article.summary,
                "source": article.source,
                "url": article.url,
                "relevance": article.relevance,
                "selected": article.selected,
                "emailed_at": article.emailed_at.isoformat() if article.emailed_at else None,
                "published_at": article.published_at.isoformat() if article.published_at else None,
            }
            for article in rows
        ]
    )


@bp.get("/digests")
def digests():
    rows = DigestRun.query.order_by(DigestRun.started_at.desc()).limit(20).all()
    return jsonify(
        [
            {
                "id": run.id,
                "status": run.status,
                "message": run.message,
                "news_found": run.news_found,
                "news_selected": run.news_selected,
                "emails_sent": run.emails_sent,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
            for run in rows
        ]
    )


@bp.post("/collect")
def collect():
    log = run_digest()
    if log is None:
        return jsonify({"status": "busy", "message": "Coleta já em andamento."}), 409
    return jsonify(
        {
            "status": log.status,
            "message": log.message,
            "news_found": log.news_found,
            "news_selected": log.news_selected,
            "emails_sent": log.emails_sent,
        }
    )
