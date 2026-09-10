web: MALLOC_ARENA_MAX=${MALLOC_ARENA_MAX:-2} gunicorn backend.app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --graceful-timeout 20 --max-requests ${GUNICORN_MAX_REQUESTS:-500} --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-50}
release: python -m backend.migrate
