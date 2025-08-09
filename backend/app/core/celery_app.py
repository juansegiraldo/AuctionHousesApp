from celery import Celery
from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "auction_houses_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.scraping.tasks"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task routing
    task_routes={
        "app.scraping.tasks.*": {"queue": "scraping"},
    },
    
    # Beat schedule for periodic tasks
    beat_schedule={
        "daily-scraping": {
            "task": "app.scraping.tasks.schedule_daily_scraping",
            "schedule": 60.0 * 60.0 * 6,  # Every 6 hours
        },
        "weekly-scraping": {
            "task": "app.scraping.tasks.schedule_weekly_scraping", 
            "schedule": 60.0 * 60.0 * 24 * 7,  # Every week
        },
    },
    
    # Worker settings
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
)