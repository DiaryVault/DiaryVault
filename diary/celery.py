# diary/celery.py - Complete Celery configuration
import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project_name.settings')

# Create Celery app
app = Celery('diary')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat Schedule for periodic tasks
from celery.schedules import crontab

app.conf.beat_schedule = {
    # Update journal analytics every 6 hours
    'update-journal-analytics': {
        'task': 'diary.tasks.update_journal_analytics',
        'schedule': crontab(minute=0, hour='*/6'),
    },

    # Clean up old AI logs daily at 2 AM
    'cleanup-old-ai-logs': {
        'task': 'diary.tasks.cleanup_old_ai_logs',
        'schedule': crontab(minute=0, hour=2),
    },

    # Update marketplace stats every hour
    'update-marketplace-stats': {
        'task': 'diary.tasks.update_marketplace_stats',
        'schedule': crontab(minute=0),
    },

    # Generate daily insights digest for active users
    'generate-daily-insights': {
        'task': 'diary.tasks.generate_daily_insights_digest',
        'schedule': crontab(minute=30, hour=9),  # 9:30 AM daily
    },

    # Clean up expired cache entries
    'cleanup-expired-caches': {
        'task': 'diary.tasks.cleanup_expired_caches',
        'schedule': crontab(minute=15, hour='*/4'),  # Every 4 hours
    },
}

# Celery configuration
app.conf.update(
    # Task serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Timezone
    timezone='UTC',
    enable_utc=True,

    # Task routing
    task_routes={
        'diary.tasks.generate_insights_async': {'queue': 'ai_tasks'},
        'diary.tasks.generate_biography_async': {'queue': 'ai_tasks'},
        'diary.tasks.generate_entry_summary_async': {'queue': 'ai_tasks'},
        'diary.tasks.update_journal_analytics': {'queue': 'analytics'},
        'diary.tasks.cleanup_old_ai_logs': {'queue': 'maintenance'},
    },

    # Task time limits
    task_soft_time_limit=300,  # 5 minutes
    task_time_limit=600,       # 10 minutes

    # Worker configuration
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,

    # Result backend configuration
    result_expires=3600,  # 1 hour
)

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup"""
    print(f'Request: {self.request!r}')
    return 'Debug task completed'


