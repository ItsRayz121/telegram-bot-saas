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
        _run_alter(
            db.engine,
            "ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'group'",
            "user_api_keys.scope",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS workspace_ai_tokens_today INTEGER NOT NULL DEFAULT 0",
            "users.workspace_ai_tokens_today",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS workspace_ai_tokens_reset_at TIMESTAMP",
            "users.workspace_ai_tokens_reset_at",
        )
        # DigestLog table is created by db.create_all() above; add any missing columns here
        _run_alter(
            db.engine,
            "ALTER TABLE digest_logs ADD COLUMN IF NOT EXISTS tokens_used INTEGER",
            "digest_logs.tokens_used",
        )
        # pending_invoices is created by db.create_all(); add any future columns here
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_pending_invoices_user_id ON pending_invoices (user_id)",
            "pending_invoices.user_id index",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE webhook_integrations ADD COLUMN IF NOT EXISTS signing_secret VARCHAR(64)",
            "webhook_integrations.signing_secret",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS token_hash VARCHAR(64)",
            "password_reset_tokens.token_hash",
        )
        _run_alter(
            db.engine,
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_prt_token_hash ON password_reset_tokens (token_hash)",
            "password_reset_tokens.token_hash index",
        )
        # FK indexes for hot-path query columns (P1-08)
        for table, col in [
            ("bots", "user_id"),
            ("members", "group_id"),
            ("audit_logs", "group_id"),
            ("scheduled_messages", "group_id"),
            ("raids", "group_id"),
            ("knowledge_documents", "group_id"),
            ("webhook_integrations", "group_id"),
            ("user_api_keys", "group_id"),
            ("reported_messages", "group_id"),
            ("polls", "group_id"),
        ]:
            _run_alter(
                db.engine,
                f"CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col})",
                f"{table}.{col} index",
            )
        # admin_audit_logs is created by db.create_all(); add any future columns here
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_admin_id ON admin_audit_logs (admin_id)",
            "admin_audit_logs.admin_id index",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'UTC'",
            "users.timezone",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE directory_listings ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(16) NOT NULL DEFAULT 'approved'",
            "directory_listings.moderation_status (existing rows → approved)",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_directory_listings_moderation_status ON directory_listings (moderation_status)",
            "directory_listings.moderation_status index",
        )
        print("Migration complete.")

    # One-shot TOTP secret encryption migration.
    # Run with: MIGRATE_ENCRYPT_TOTP=1 python -m backend.migrate
    import os as _os
    if _os.environ.get("MIGRATE_ENCRYPT_TOTP") == "1":
        _migrate_encrypt_totp(app)


def _migrate_encrypt_totp(app):
    """Re-encrypt any plaintext TOTP secrets in the database under the current key.

    Detects plaintext by attempting to decrypt — if decryption raises DecryptionError
    the stored value is treated as plaintext (legacy pre-encryption row) and encrypted.
    Already-encrypted rows are left untouched (idempotent).

    Enable with: MIGRATE_ENCRYPT_TOTP=1 python -m backend.migrate
    """
    from .models import db, User
    from .utils.encryption import encrypt_value, DecryptionError

    with app.app_context():
        users = User.query.filter(User._totp_secret_enc.isnot(None)).all()
        updated = 0
        for user in users:
            raw = user._totp_secret_enc
            # Try to decrypt — success means already encrypted, skip
            try:
                from .utils.encryption import decrypt_value
                decrypt_value(raw)
                continue
            except DecryptionError:
                pass
            # Value looks like plaintext — validate it's a base32 TOTP secret
            import re
            if re.match(r'^[A-Z2-7]{16,64}$', raw):
                user._totp_secret_enc = encrypt_value(raw)
                updated += 1
            else:
                print(f"  ⚠ User {user.id} has unrecognisable totp_secret — skipping")
        if updated:
            db.session.commit()
            print(f"  ✓ Encrypted {updated} plaintext TOTP secrets")
        else:
            print("  – No plaintext TOTP secrets found (already encrypted or none set)")


if __name__ == "__main__":
    init_db()
