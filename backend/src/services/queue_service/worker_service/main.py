"""
Celery worker entry-point.

Start the worker with:
    celery -A src.services.queue_service.worker_service.main worker --loglevel=info

Or equivalently (tasks module directly):
    celery -A src.services.queue_service.main worker --loglevel=info
"""

from dotenv import load_dotenv

load_dotenv()

from src.config.rabbitmq_config import celery_app  # noqa: E402
import src.services.queue_service.main  # noqa: E402, F401 — registers tasks

__all__ = ["celery_app"]
