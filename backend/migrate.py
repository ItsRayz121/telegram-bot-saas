from .app import create_app
from .models import db


def _run_alter(engine, sql, description):
    """Run a single DDL statement in its own transaction so one failure cannot
    abort subsequent migrations."""
    try:
        with engine.begin() as conn:
            conn.execute(db.text(sql))
        print(f"  ✓ {description}")
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "duplicate column" in msg:
            print(f"  – {description} (already exists, skipped)")
        else:
            print(f"  ✗ {description}: {e}")


def init_db():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Database tables created (new tables only).")

        print("Applying schema additions…")
        _run_alter(
            db.engine,
            "ALTER TABLE payment_history ADD COLUMN IF NOT EXISTS billing_period VARCHAR(10) DEFAULT 'monthly'",
            "payment_history.billing_period",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_groups ADD COLUMN IF NOT EXISTS member_count INTEGER NOT NULL DEFAULT 0",
            "telegram_groups.member_count",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_groups ADD COLUMN IF NOT EXISTS description TEXT",
            "telegram_groups.description",
        )
        print("Migration complete.")


if __name__ == "__main__":
    init_db()
