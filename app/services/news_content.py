"""Extração educada do texto principal de URLs públicas (a partir do RSS).

- Timeout curto, User-Agent identificado, limite de tamanho
- Não força bypass de paywall/login
- Se falhar, o fluxo segue só com título/resumo do feed
"""

from __future__ import annotations

import logging
import re
import unicodedata
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "AppNoticiasLocal/1.0 (+uso pessoal; contato local; "
    "respeita robots quando aplicável)"
)
TIMEOUT = 12
MAX_HTML_BYTES = 1_500_000
MAX_BODY_CHARS = 4500

SKIP_HOST_FRAGMENTS = (
    "accounts.google.",
    "news.google.",
    "consent.google.",
    "login.",
    "signin.",
    "paywall",
)


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def _title_terms(title: str) -> list[str]:
    stop = {"para", "como", "com", "uma", "que", "dos", "das", "por", "the", "and", "com"}
    terms = []
    for part in re.findall(r"[a-z0-9]{4,}", _fold(title)):
        if part in stop or part in terms:
            continue
        terms.append(part)
    return terms


def extract_article_text(html: str, title: str = "") -> str:
    """Extrai um trecho curto do texto principal, de preferência ligado à manchete."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    paragraphs = []
    for node in soup.find_all("p"):
        text = _clean_text(node.get_text(" ", strip=True))
        if len(text) < 50:
            continue
        folded = _fold(text)
        if folded.startswith(("escrito por", "revisado por", "leia tambem", "tenha acesso", "assine ")):
            continue
        paragraphs.append(text)

    terms = _title_terms(title)
    if paragraphs and terms:
        def hits(text: str) -> int:
            folded = _fold(text)
            return sum(1 for term in terms if term in folded)

        best_index = max(range(len(paragraphs)), key=lambda index: (hits(paragraphs[index]), -index))
        if hits(paragraphs[best_index]) > 0:
            window = " ".join(paragraphs[best_index: best_index + 3])
            if len(window) >= 80:
                return window[:MAX_BODY_CHARS]

    if paragraphs:
        joined = " ".join(paragraphs[:4])
        if len(joined) >= 80:
            return joined[:MAX_BODY_CHARS]

    return ""


def fetch_article_body(url: str, title: str = "") -> str | None:
    """Baixa e extrai corpo da matéria. Retorna None se indisponível."""
    if not url or not url.startswith("http"):
        return None

    host = urlparse(url).netloc.lower()
    if any(x in host for x in SKIP_HOST_FRAGMENTS):
        return None

    try:
        resp = requests.get(
            url,
            timeout=TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
            allow_redirects=True,
        )
        if resp.status_code != 200:
            logger.debug("HTTP %s ao buscar %s", resp.status_code, url)
            return None

        final_host = urlparse(resp.url).netloc.lower()
        if any(x in final_host for x in SKIP_HOST_FRAGMENTS):
            return None

        raw = resp.content[:MAX_HTML_BYTES]
        ctype = "utf-8"
        if resp.encoding and resp.encoding.lower() != "iso-8859-1":
            ctype = resp.encoding
        html = raw.decode(ctype, errors="replace")
        text = extract_article_text(html, title=title)
        return text or None
    except Exception as exc:
        logger.debug("Falha ao extrair corpo de %s: %s", url, exc)
        return None
