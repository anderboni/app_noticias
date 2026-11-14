"""Aplicação Flask — coleta de notícias por assunto e resumo por e-mail."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from app.config import Config

db = SQLAlchemy()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from app.routes.api import bp as api_bp
    from app.routes.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.template_filter("brasilia")
    def brasilia_filter(value, fmt="%d/%m/%Y %H:%M"):
        """Jinja: {{ dt|brasilia }} ou {{ dt|brasilia('%d/%m %H:%M') }}"""
        from app.utils.datetime_br import format_brasilia

        return format_brasilia(value, fmt)

    with app.app_context():
        from app import models  # noqa: F401

        db.create_all()
        from app.services.settings_service import ensure_settings_seeded

        ensure_settings_seeded()

    return app
