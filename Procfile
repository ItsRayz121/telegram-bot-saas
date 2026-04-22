web: gunicorn backend.app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
worker: celery -A backend.scheduler worker --loglevel=info
beat: celery -A backend.scheduler beat --loglevel=info
