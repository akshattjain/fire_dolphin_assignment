import os

from celery import Celery

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")

celery_app = Celery(
    "fire_dolphin",
    broker=RABBITMQ_URL,
    include=["src.services.queue_service.main"],
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.task_track_started = True
