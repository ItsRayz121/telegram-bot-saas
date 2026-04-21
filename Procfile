web: gunicorn backend.app:app --bind 0.0.0.0:$PORT
worker: celery -A backend.scheduler worker --loglevel=info
beat: celery -A backend.scheduler beat --loglevel=info
