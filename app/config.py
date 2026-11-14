"""Configurações da aplicação."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _database_uri() -> str:
    """Usa noticias.db no projeto. O banco financeiro antigo não entra neste sistema."""
    raw = os.getenv("DATABASE_URL", "").strip().replace("\\", "/")
    default = f"sqlite:///{(BASE_DIR / 'noticias.db').as_posix()}"
    if not raw or raw.rstrip("/").endswith("financeiro.db"):
        return default
    prefix = "sqlite:///"
    if raw.startswith(prefix):
        path = raw[len(prefix):]
        if path.endswith(".db") and "/" not in path and ":" not in path:
            return f"sqlite:///{(BASE_DIR / path).as_posix()}"
    return raw


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-local-nao-usar-em-producao")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_ENABLED = os.getenv("MAIL_ENABLED", "false").lower() == "true"
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.hostinger.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "")
    MAIL_TO = os.getenv("MAIL_TO", "")

    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "5000"))
    APP_PUBLIC_HOST = os.getenv("APP_PUBLIC_HOST", "").strip()

    # Enriquece resumos curtos com o texto público da matéria, quando possível
    NEWS_FETCH_BODY = os.getenv("NEWS_FETCH_BODY", "true").lower() == "true"
    NEWS_FETCH_MAX_PER_RUN = int(os.getenv("NEWS_FETCH_MAX_PER_RUN", "12"))
