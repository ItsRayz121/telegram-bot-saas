from .app import create_app
from .models import db


def _run_alter(conn, sql, description):
    try:
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

        # Add any columns that were added after initial deployment
        with db.engine.begin() as conn:
            print("Applying schema additions…")
            _run_alter(
                conn,
                "ALTER TABLE payment_history ADD COLUMN IF NOT EXISTS billing_period VARCHAR(10) DEFAULT 'monthly'",
                "payment_history.billing_period",
            )
            _run_alter(
                conn,
                "ALTER TABLE telegram_groups ADD COLUMN IF NOT EXISTS member_count INTEGER NOT NULL DEFAULT 0",
                "telegram_groups.member_count",
            )
            _run_alter(
                conn,
                "ALTER TABLE telegram_groups ADD COLUMN IF NOT EXISTS description TEXT",
                "telegram_groups.description",
            )
        print("Migration complete.")


if __name__ == "__main__":
    init_db()
