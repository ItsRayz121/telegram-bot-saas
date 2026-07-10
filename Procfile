web: gunicorn backend.app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --graceful-timeout 20
release: python -m backend.migrate
