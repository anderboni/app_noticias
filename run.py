"""Ponto de entrada do coletor de notícias."""

import logging

from app import create_app
from app.services.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = create_app()

if __name__ == "__main__":
    start_scheduler(app)
    host = app.config.get("APP_HOST", "0.0.0.0")
    port = app.config.get("APP_PORT", 5000)
    app.run(host=host, port=port, debug=True, use_reloader=False)
