web: gunicorn backend.app:app
worker: celery -A backend.scheduler worker --loglevel=info
beat: celery -A backend.scheduler beat --loglevel=info
