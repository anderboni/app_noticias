"""Coleta notícias por assunto via Google Notícias (RSS público)."""

from __future__ import annotations

import html
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup
from flask import current_app

from app import db
from app.models import NewsArticle, Topic, utcnow
from app.services.news_content import USER_AGENT, fetch_article_body

logger = logging.getLogger(__name__)

STOPWORDS = {
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "para",
    "por", "com", "sem", "que", "uma", "uns", "umas", "the", "and", "for",
    "with", "from", "sobre", "como", "mais", "seu", "sua", "aos", "pelo",
    "pela", "ou", "or", "when", "noticia", "noticias", "news", "not",
}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def trim_summary(text: str, limit: int = 500) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if dot > 140:
        return cut[: dot + 1]
    return cut.rstrip() + "…"


def topic_terms(topic: Topic) -> list[str]:
    raw = fold(f"{topic.name} {topic.search_query or ''}")
    raw = re.sub(r"when:\d+d", " ", raw)
    seen: list[str] = []
    for part in re.findall(r"[a-z0-9]{3,}", raw):
        if part in STOPWORDS or part in seen:
            continue
        seen.append(part)
    return seen


def score_relevance(title: str, summary: str, topic: Topic) -> float:
    """0 a 1. A busca já filtra o assunto; o score separa o que entra no e-mail."""
    title_f = fold(title)
    summary_f = fold(summary)
    name = fold(topic.name.strip())
    terms = topic_terms(topic)

    if name and name in title_f:
        base = 0.82
    elif name and name in summary_f:
        base = 0.62
    else:
        base = 0.28

    if not terms:
        return round(min(1.0, base), 3)

    title_hits = sum(1 for term in terms if term in title_f)
    summary_hits = sum(1 for term in terms if term in summary_f)
    extra = 0.35 * (title_hits / len(terms)) + 0.15 * (summary_hits / len(terms))
    return round(min(1.0, base + extra), 3)


def _parse_date(entry) -> datetime:
    for attr in ("published", "updated"):
        raw = entry.get(attr) if hasattr(entry, "get") else getattr(entry, attr, None)
        if not raw:
            continue
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            continue
    return utcnow()


def _source_name(entry, fallback: str) -> str:
    source = entry.get("source") if hasattr(entry, "get") else None
    if source:
        title = source.get("title") if hasattr(source, "get") else None
        if title:
            return clean_text(str(title))[:160]
    return fallback[:160]


def _google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )


def _title_without_source(title: str, source: str) -> str:
    suffix = f" - {source}".strip()
    if source and title.endswith(suffix):
        return title[: -len(suffix)].strip() or title
    return title


def _summary_is_redundant(title: str, summary: str) -> bool:
    folded_title = fold(title)
    folded_summary = fold(summary)
    if not folded_summary or not folded_title:
        return True
    return folded_summary.startswith(folded_title[:48]) or folded_title.startswith(folded_summary[:48])


def resolve_publisher_url(url: str) -> str | None:
    """Troca o link do Google Notícias pelo endereço da matéria, quando possível."""
    if not url or "news.google." not in url or "/articles/" not in url:
        return None
    article_id = url.split("/articles/", 1)[1].split("?", 1)[0]
    headers = {"User-Agent": USER_AGENT}
    try:
        page = requests.get(
            "https://news.google.com/rss/articles/" + article_id,
            timeout=12,
            headers=headers,
        )
        page.raise_for_status()
        node = BeautifulSoup(page.text, "lxml").select_one("[data-n-a-sg]")
        if node is None:
            return None
        signature = node.get("data-n-a-sg")
        timestamp = node.get("data-n-a-ts")
        if not signature or not timestamp:
            return None
        inner = [
            "garturlreq",
            [
                ["X", "X", ["X", "X"], None, None, 1, 1, "BR:pt-419", None, 1, None, None, None, None, None, 0, 1],
                "X",
                "X",
                1,
                [1, 1, 1],
                1,
                1,
                None,
                0,
                0,
                None,
                0,
            ],
            article_id,
            int(timestamp),
            signature,
        ]
        payload = "f.req=" + quote(
            json.dumps([[["Fbv4je", json.dumps(inner, separators=(",", ":"))]]])
        )
        decoded = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": USER_AGENT,
            },
            timeout=12,
        )
        decoded.raise_for_status()
        match = re.search(r'garturlres\\?",\\?"(https://[^"\\]+)', decoded.text)
        if not match:
            return None
        return match.group(1)[:1500]
    except Exception as exc:
        logger.debug("Não foi possível abrir o link do Google Notícias: %s", exc)
        return None


def fetch_query(query: str, limit: int = 20) -> list[dict]:
    articles: list[dict] = []
    try:
        response = requests.get(
            _google_news_url(query),
            timeout=20,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, */*"},
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as exc:
        logger.warning("Falha ao buscar %r: %s", query, exc)
        raise

    for entry in parsed.entries[:limit]:
        title = clean_text(entry.get("title") or "")
        summary = trim_summary(entry.get("summary") or entry.get("description") or "")
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        source = _source_name(entry, "Google Notícias")
        title = _title_without_source(title, source)
        articles.append(
            {
                "title": title[:500],
                "summary": "" if _summary_is_redundant(title, summary) else summary,
                "url": link[:1500],
                "source": source,
                "published_at": _parse_date(entry),
            }
        )
    return articles


def _search_queries(topic: Topic, lookback_hours: int) -> list[str]:
    base = topic.search_text()
    days = max(1, min(7, -(-lookback_hours // 24)))  # ceil
    if re.search(r"when:\d+d", base, flags=re.IGNORECASE):
        return [base]
    return [f"{base} when:{days}d", base]


def collect_all_topics(topics: list[Topic], *, min_relevance: float, lookback_hours: int) -> dict:
    """Busca notícias novas para os assuntos ativos e grava no banco."""
    cutoff = utcnow() - timedelta(hours=lookback_hours)
    fetch_body = True
    enrich_limit = 12
    try:
        fetch_body = bool(current_app.config.get("NEWS_FETCH_BODY", True))
        enrich_limit = max(0, int(current_app.config.get("NEWS_FETCH_MAX_PER_RUN", 12)))
    except Exception:
        pass
    found = 0
    selected = 0
    errors: list[str] = []
    prepared: list[dict] = []

    for topic in topics:
        items: list[dict] = []
        last_error = None
        for query in _search_queries(topic, lookback_hours):
            try:
                items = fetch_query(query)
            except Exception as exc:
                last_error = str(exc)
                items = []
            if items:
                break
        if not items and last_error:
            errors.append(f"{topic.name}: {last_error}")
            continue
        if not items:
            logger.info("Nenhuma notícia no feed para %s", topic.name)
            continue

        seen_urls: set[str] = set()
        for item in items:
            if item["published_at"] < cutoff:
                continue
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            exists = NewsArticle.query.filter_by(url=item["url"], topic_id=topic.id).first()
            if exists:
                continue
            relevance = score_relevance(item["title"], item["summary"], topic)
            item["topic_id"] = topic.id
            item["relevance"] = relevance
            item["selected"] = relevance >= min_relevance
            prepared.append(item)

    ranked = sorted(
        [item for item in prepared if item["selected"]],
        key=lambda item: item["relevance"],
        reverse=True,
    )
    per_topic: dict[int, int] = {}
    enriched = 0
    for item in ranked:
        if enriched >= enrich_limit or per_topic.get(item["topic_id"], 0) >= 8:
            continue
        resolved = resolve_publisher_url(item["url"])
        if resolved:
            item["url"] = resolved
        if fetch_body:
            body = fetch_article_body(item["url"], title=item["title"])
            if body and len(body) > len(item["summary"] or ""):
                item["summary"] = trim_summary(body, 700)
        per_topic[item["topic_id"]] = per_topic.get(item["topic_id"], 0) + 1
        enriched += 1
        time.sleep(0.2)

    seen_saved: set[tuple[int, str]] = set()
    for item in prepared:
        key = (item["topic_id"], item["url"])
        if key in seen_saved:
            continue
        seen_saved.add(key)
        exists = NewsArticle.query.filter_by(url=item["url"], topic_id=item["topic_id"]).first()
        if exists:
            continue
        db.session.add(
            NewsArticle(
                topic_id=item["topic_id"],
                title=item["title"],
                summary=item["summary"] or None,
                url=item["url"],
                source=item["source"],
                published_at=item["published_at"],
                relevance=item["relevance"],
                selected=item["selected"],
                collected_at=utcnow(),
            )
        )
        found += 1
        if item["selected"]:
            selected += 1

    if found:
        db.session.commit()
    logger.info("Coleta: novas=%s selecionadas=%s erros=%s", found, selected, len(errors))
    return {"found": found, "selected": selected, "errors": errors}


def pending_digest_articles(topic: Topic, *, limit: int, lookback_hours: int) -> list[NewsArticle]:
    cutoff = utcnow() - timedelta(hours=lookback_hours)
    return (
        NewsArticle.query.filter(
            NewsArticle.topic_id == topic.id,
            NewsArticle.selected.is_(True),
            NewsArticle.emailed_at.is_(None),
            NewsArticle.collected_at >= cutoff,
        )
        .order_by(NewsArticle.relevance.desc(), NewsArticle.published_at.desc())
        .limit(limit)
        .all()
    )
