"""Modelos do banco local SQLite — coleta de notícias por assunto."""

from datetime import datetime, timezone

from app import db


def utcnow():
    """UTC sem fuso, para o SQLite comparar datas de forma estável."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Topic(db.Model):
    """Assunto monitorado. A busca usa `query` ou, se vazio, o nome."""

    __tablename__ = "topics"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    search_query = db.Column(db.String(400))
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    articles = db.relationship(
        "NewsArticle",
        back_populates="topic",
        cascade="all, delete-orphan",
    )

    def search_text(self) -> str:
        return (self.search_query or "").strip() or self.name.strip()

    def __repr__(self):
        return f"<Topic {self.name}>"


class ScheduleSlot(db.Model):
    """Horário do dia (Brasília) em que a coleta e o e-mail rodam."""

    __tablename__ = "schedule_slots"
    __table_args__ = (
        db.UniqueConstraint("hour", "minute", name="uq_schedule_time"),
    )

    id = db.Column(db.Integer, primary_key=True)
    hour = db.Column(db.Integer, nullable=False)
    minute = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def label(self) -> str:
        return f"{int(self.hour):02d}:{int(self.minute):02d}"

    def __repr__(self):
        return f"<Schedule {self.label}>"


class EmailRecipient(db.Model):
    """Destinatários do resumo de notícias."""

    __tablename__ = "email_recipients"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f"<EmailRecipient {self.email}>"


class NewsArticle(db.Model):
    __tablename__ = "news_articles"
    __table_args__ = (
        db.UniqueConstraint("url", "topic_id", name="uq_news_url_topic"),
    )

    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    summary = db.Column(db.Text)
    url = db.Column(db.String(1500), nullable=False)
    source = db.Column(db.String(160))
    published_at = db.Column(db.DateTime)
    relevance = db.Column(db.Float, default=0.0)
    selected = db.Column(db.Boolean, default=False, nullable=False, index=True)
    emailed_at = db.Column(db.DateTime)
    collected_at = db.Column(db.DateTime, default=utcnow, index=True)

    topic = db.relationship("Topic", back_populates="articles")

    def __repr__(self):
        return f"<News {self.title[:40]}>"


class DigestRun(db.Model):
    """Registro de cada coleta (manual ou agendada)."""

    __tablename__ = "digest_runs"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=utcnow, index=True)
    finished_at = db.Column(db.DateTime)
    news_found = db.Column(db.Integer, default=0)
    news_selected = db.Column(db.Integer, default=0)
    emails_sent = db.Column(db.Integer, default=0)
    status = db.Column(db.String(32), default="running")
    message = db.Column(db.Text)

    def __repr__(self):
        return f"<DigestRun {self.status}>"


class AppSettings(db.Model):
    """Preferências gerais (uma linha, id=1)."""

    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)
    max_items_per_topic = db.Column(db.Integer, nullable=False, default=5)
    min_relevance = db.Column(db.Float, nullable=False, default=0.40)
    lookback_hours = db.Column(db.Integer, nullable=False, default=36)
    weekdays_only = db.Column(db.Boolean, nullable=False, default=False)
    last_run_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<AppSettings max={self.max_items_per_topic}>"
