"""Monta e envia o resumo de notícias.

Credenciais SMTP ficam no .env (MAIL_*). Destinatários vêm do banco.
Com MAIL_ENABLED=false, o envio é registrado no log e tratado como falha.
"""

from __future__ import annotations

import html
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import lru_cache

import requests
from flask import current_app

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_public_ip() -> str:
    endpoints = (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    )
    for url in endpoints:
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                ip = resp.text.strip()
                if ip:
                    return ip
        except Exception:
            continue
    return "127.0.0.1"


def get_system_url() -> str:
    host = current_app.config.get("APP_PUBLIC_HOST") or get_public_ip()
    port = current_app.config.get("APP_PORT", 5000)
    return f"http://{host}:{port}"


def _send_mail(subject: str, body: str, recipients: list[str], html_body: str | None = None) -> bool:
    cfg = current_app.config
    recipients = [item.strip() for item in recipients if item and item.strip()]

    if not cfg.get("MAIL_ENABLED"):
        logger.info("E-mail desabilitado. Assunto: %s\n%s", subject, body)
        return False

    username = cfg.get("MAIL_USERNAME") or ""
    password = cfg.get("MAIL_PASSWORD") or ""
    mail_from = cfg.get("MAIL_FROM") or username
    if not username or not password or not recipients:
        logger.warning("Credenciais ou destinatários incompletos — não enviado.")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = mail_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=30) as server:
            if cfg.get("MAIL_USE_TLS"):
                server.starttls()
            server.login(username, password)
            server.sendmail(mail_from, recipients, msg.as_string())
        logger.info("E-mail enviado: %s -> %s", subject, recipients)
        return True
    except Exception as exc:
        logger.exception("Falha ao enviar e-mail: %s", exc)
        return False


def _article_block(article) -> list[str]:
    lines = [f"• {article.title}"]
    if article.summary:
        lines.append(f"  {article.summary}")
    if article.source:
        lines.append(f"  Fonte: {article.source}")
    lines.append(f"  {article.url}")
    lines.append("")
    return lines


def send_digest_email(groups: list[dict], when_label: str) -> bool:
    """groups: [{topic: str, articles: [NewsArticle, ...]}]"""
    from app.services.settings_service import get_recipient_emails

    recipients = get_recipient_emails()
    system_url = get_system_url()
    subject = f"Resumo de notícias — {when_label}"

    lines = [
        f"Resumo de notícias — {when_label}",
        "",
        "Principais notícias encontradas para os assuntos configurados.",
        "",
    ]
    html_parts = [
        "<html><body style=\"font-family:Segoe UI,Helvetica,sans-serif;color:#1c2430;line-height:1.45;\">",
        f"<h1 style=\"font-size:20px;margin:0 0 8px;\">Resumo de notícias</h1>",
        f"<p style=\"color:#5c6b7a;margin:0 0 20px;\">{html.escape(when_label)}</p>",
    ]

    for group in groups:
        lines.append(group["topic"].upper())
        lines.append("")
        html_parts.append(
            f"<h2 style=\"font-size:16px;margin:22px 0 8px;border-bottom:1px solid #e4e9ef;padding-bottom:4px;\">{html.escape(group['topic'])}</h2>"
        )
        for article in group["articles"]:
            lines.extend(_article_block(article))
            summary = html.escape(article.summary or "")
            source = html.escape(article.source or "")
            title = html.escape(article.title or "")
            url = html.escape(article.url or "", quote=True)
            html_parts.append(
                "<div style=\"margin:0 0 16px;\">"
                f"<div style=\"font-weight:650;\"><a href=\"{url}\" style=\"color:#0b6b57;text-decoration:none;\">{title}</a></div>"
                + (f"<p style=\"margin:4px 0;\">{summary}</p>" if summary else "")
                + (f"<div style=\"color:#5c6b7a;font-size:13px;\">{source}</div>" if source else "")
                + f"<div style=\"font-size:13px;\"><a href=\"{url}\">Abrir notícia</a></div>"
                "</div>"
            )

    lines.extend(
        [
            f"Ver todas as notícias no sistema: {system_url}/noticias",
            "",
            "Resumo gerado automaticamente a partir de feeds públicos.",
        ]
    )
    html_parts.append(
        f"<p style=\"margin-top:24px;\"><a href=\"{html.escape(system_url + '/noticias', quote=True)}\">Ver todas as notícias no sistema</a></p>"
        "<p style=\"color:#5c6b7a;font-size:12px;\">Resumo gerado automaticamente a partir de feeds públicos.</p>"
        "</body></html>"
    )
    return _send_mail(subject, "\n".join(lines), recipients, html_body="".join(html_parts))


def send_test_email() -> tuple[bool, str]:
    from app.services.settings_service import get_recipient_emails

    recipients = get_recipient_emails()
    if not recipients:
        return False, "Cadastre ao menos um e-mail em Configurações."
    if not current_app.config.get("MAIL_ENABLED"):
        return False, "MAIL_ENABLED=false no .env — ative para enviar."

    system_url = get_system_url()
    subject = "App Notícias — teste de e-mail"
    body = "\n".join(
        [
            "Este é um e-mail de teste do App Notícias.",
            "",
            "Se você recebeu esta mensagem, o SMTP está configurado.",
            "Os resumos trazem, por assunto, um texto curto e o link de cada notícia.",
            "",
            f"Notícias no sistema: {system_url}/noticias",
            f"Destinatários deste teste: {', '.join(recipients)}",
        ]
    )
    html_body = (
        "<html><body style=\"font-family:Segoe UI,Helvetica,sans-serif;color:#1c2430;\">"
        "<h1 style=\"font-size:18px;\">Teste de e-mail</h1>"
        "<p>Se você recebeu esta mensagem, o SMTP está configurado.</p>"
        "<p>Os resumos trazem, por assunto, um texto curto e o link de cada notícia.</p>"
        f"<p><a href=\"{html.escape(system_url + '/noticias', quote=True)}\">Abrir notícias no sistema</a></p>"
        "</body></html>"
    )
    ok = _send_mail(subject, body, recipients, html_body=html_body)
    if ok:
        return True, f"E-mail de teste enviado para {len(recipients)} destinatário(s)."
    return False, "Falha ao enviar. Verifique o log do servidor e as credenciais SMTP."
