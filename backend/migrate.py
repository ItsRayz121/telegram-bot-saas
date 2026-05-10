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

        # ── Phase 5: pgvector embedding columns (TEXT fallback — no pgvector ext required) ──
        _run_alter(
            db.engine,
            "ALTER TABLE notes ADD COLUMN IF NOT EXISTS embedding TEXT",
            "notes.embedding",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS embedding TEXT",
            "knowledge_documents.embedding",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE workspace_knowledge_documents ADD COLUMN IF NOT EXISTS embedding TEXT",
            "workspace_knowledge_documents.embedding",
        )

        # ── Phase 6.3: BotDMMessage extra columns ────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE bot_dm_messages ADD COLUMN IF NOT EXISTS session_id VARCHAR(64)",
            "bot_dm_messages.session_id",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE bot_dm_messages ADD COLUMN IF NOT EXISTS feedback VARCHAR(16)",
            "bot_dm_messages.feedback",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE bot_dm_messages ADD COLUMN IF NOT EXISTS intent_confidence FLOAT",
            "bot_dm_messages.intent_confidence",
        )

        # ── Phase 3: GroupDailySignal table (db.create_all handles new table; ──
        # ── add any extra columns here if the table already existed) ──────────
        _run_alter(
            db.engine,
            "ALTER TABLE group_daily_signals ADD COLUMN IF NOT EXISTS ai_summary TEXT",
            "group_daily_signals.ai_summary",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE group_daily_signals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
            "group_daily_signals.updated_at",
        )

        # ── UserAssistantProfile table (new — db.create_all handles creation) ─
        # ── Index for fast per-user lookup ────────────────────────────────────
        _run_alter(
            db.engine,
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_assistant_profiles_user_id ON user_assistant_profiles (user_id)",
            "user_assistant_profiles.user_id index",
        )

        # ── pending_verifications: add forum topic + auto-delete columns ────────
        _run_alter(
            db.engine,
            "ALTER TABLE pending_verifications ADD COLUMN IF NOT EXISTS message_thread_id INTEGER",
            "pending_verifications.message_thread_id",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE pending_verifications ADD COLUMN IF NOT EXISTS auto_delete_on_timeout BOOLEAN DEFAULT TRUE",
            "pending_verifications.auto_delete_on_timeout",
        )

        # ── 1-A-01: Subscription lifecycle fields ────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ",
            "users.subscription_expires_at",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_grace_until TIMESTAMPTZ",
            "users.subscription_grace_until",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_interval VARCHAR(20)",
            "users.subscription_interval",
        )
        # ── 1-D-05: ToS acceptance tracking ──────────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tos_version_accepted VARCHAR(20)",
            "users.tos_version_accepted",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tos_accepted_at TIMESTAMP",
            "users.tos_accepted_at",
        )

        # ── 1-C-01: PendingUnban table (db.create_all handles creation) ─────────
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_pending_unbans_unban_at ON pending_unbans (unban_at) WHERE success = FALSE",
            "pending_unbans.unban_at index",
        )

        # ── 1-B-01: TelegramGroupLinkCode — dashboard-generated flow columns ────
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_group_link_codes ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
            "telegram_group_link_codes.user_id",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_group_link_codes ADD COLUMN IF NOT EXISTS bot_id INTEGER REFERENCES bots(id)",
            "telegram_group_link_codes.bot_id",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_group_link_codes ALTER COLUMN telegram_group_id DROP NOT NULL",
            "telegram_group_link_codes.telegram_group_id nullable",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_group_link_codes ALTER COLUMN created_by_telegram_user_id DROP NOT NULL",
            "telegram_group_link_codes.created_by_telegram_user_id nullable",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_group_link_codes ADD COLUMN IF NOT EXISTS used BOOLEAN NOT NULL DEFAULT FALSE",
            "telegram_group_link_codes.used",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_tglc_user_id ON telegram_group_link_codes (user_id)",
            "telegram_group_link_codes.user_id index",
        )

        # ── 1-A-02: SubscriptionRenewal table (db.create_all handles creation) ─
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_subscription_renewals_user_id ON subscription_renewals (user_id)",
            "subscription_renewals.user_id index",
        )

        # ── members.last_name ─────────────────────────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE members ADD COLUMN IF NOT EXISTS last_name VARCHAR(255)",
            "members.last_name",
        )

        # ── 2-D-01: 14-day Pro trial columns ─────────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP",
            "users.trial_ends_at",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_used BOOLEAN DEFAULT FALSE",
            "users.trial_used",
        )
        # ── 2-B-01: Onboarding completed steps ───────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed_steps JSONB",
            "users.onboarding_completed_steps",
        )
        # ── 1-G-04: AI cost tracking columns ─────────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_cost_usd_today NUMERIC(10,6) DEFAULT 0",
            "users.ai_cost_usd_today",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_cost_reset_at TIMESTAMP",
            "users.ai_cost_reset_at",
        )

        # ── auto_replies as AI knowledge ──────────────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE auto_responses ADD COLUMN IF NOT EXISTS use_as_ai_knowledge BOOLEAN NOT NULL DEFAULT FALSE",
            "auto_responses.use_as_ai_knowledge",
        )

        # ── Backfill: create UserTelegramAccount rows for legacy User.telegram_user_id ──
        # Any user with telegram_user_id but no junction row gets a primary record created.
        _backfill_telegram_accounts(app)

        # ── Context separation: group_context column on telegram_groups ──────────
        # All existing rows (Group Management groups) default to 'group_management'.
        # Assistant Hub groups are stored in hub_connected_groups (separate table).
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_groups ADD COLUMN IF NOT EXISTS group_context VARCHAR(20) NOT NULL DEFAULT 'group_management'",
            "telegram_groups.group_context (pillar separation — default group_management)",
        )
        # Ensure any rows with NULL context are backfilled (shouldn't happen given
        # server_default, but safe to run idempotently).
        _run_alter(
            db.engine,
            "UPDATE telegram_groups SET group_context = 'group_management' WHERE group_context IS NULL",
            "telegram_groups.group_context backfill NULL rows",
        )

        print("Migration complete.")

    # One-shot Telegram account backfill (also runs inline above via _backfill_telegram_accounts).
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


def _backfill_telegram_accounts(app):
    """Create UserTelegramAccount rows for any User that has telegram_user_id but no junction row.

    Idempotent — safe to run multiple times.
    """
    from .models import db, User, UserTelegramAccount
    with app.app_context():
        legacy_users = User.query.filter(User.telegram_user_id.isnot(None)).all()
        created = 0
        for user in legacy_users:
            exists = UserTelegramAccount.query.filter_by(
                user_id=user.id,
                telegram_user_id=user.telegram_user_id,
            ).first()
            if not exists:
                acct = UserTelegramAccount(
                    user_id=user.id,
                    telegram_user_id=user.telegram_user_id,
                    telegram_username=user.telegram_username,
                    telegram_first_name=getattr(user, "telegram_first_name", None),
                    is_primary=True,
                    linked_at=getattr(user, "telegram_connected_at", None),
                )
                db.session.add(acct)
                created += 1
        if created:
            db.session.commit()
            print(f"  ✓ Backfilled {created} UserTelegramAccount rows from legacy telegram_user_id")
        else:
            print("  – UserTelegramAccount backfill: all rows already present")


def init_hub_db():
    """Apply Sprint 1 Assistant Hub schema — idempotent, safe to re-run."""
    app = create_app()
    with app.app_context():
        # Import hub models so SQLAlchemy knows about them before create_all
        from .assistant import hub_models  # noqa: F401

        db.create_all()
        print("Assistant Hub tables created (new tables only).")

        # Indexes — created via CREATE INDEX IF NOT EXISTS
        hub_indexes = [
            ("CREATE INDEX IF NOT EXISTS idx_hub_bot_identities_user ON hub_bot_identities(user_id, is_active)",
             "idx_hub_bot_identities_user"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_connected_groups_bot ON hub_connected_groups(bot_id, is_active)",
             "idx_hub_connected_groups_bot"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_connected_groups_user ON hub_connected_groups(user_id)",
             "idx_hub_connected_groups_user"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_tasks_user_bot_status ON hub_tasks(user_id, bot_id, status)",
             "idx_hub_tasks_user_bot_status"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_tasks_user_group ON hub_tasks(user_id, source_group_id)",
             "idx_hub_tasks_user_group"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_reminders_bot_remind_at ON hub_reminders(bot_id, remind_at) WHERE delivered_at IS NULL",
             "idx_hub_reminders_bot_remind_at"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_decisions_user_bot ON hub_decisions(user_id, bot_id)",
             "idx_hub_decisions_user_bot"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_meetings_bot_scheduled ON hub_meetings(bot_id, scheduled_at)",
             "idx_hub_meetings_bot_scheduled"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_inbox_user_bot_new ON hub_inbox_items(user_id, bot_id, is_new) WHERE dismissed_at IS NULL",
             "idx_hub_inbox_user_bot_new"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_templates_bot ON hub_templates(bot_id)",
             "idx_hub_templates_bot"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_knowledge_cards_bot ON hub_knowledge_cards(bot_id)",
             "idx_hub_knowledge_cards_bot"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_extraction_batches_bot_group ON hub_extraction_batches(bot_id, group_id, started_at DESC)",
             "idx_hub_extraction_batches_bot_group"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_memory_people_user ON hub_memory_people(user_id)",
             "idx_hub_memory_people_user"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_memory_suggestions_pending ON hub_memory_suggestions(user_id, status) WHERE status = 'pending'",
             "idx_hub_memory_suggestions_pending"),
            ("CREATE INDEX IF NOT EXISTS idx_hub_followups_user_bot_status ON hub_follow_ups(user_id, bot_id, status)",
             "idx_hub_followups_user_bot_status"),
        ]

        print("Applying Assistant Hub indexes…")
        for sql, desc in hub_indexes:
            _run_alter(db.engine, sql, desc)

        print("Assistant Hub migration complete.")


if __name__ == "__main__":
    init_db()
    init_hub_db()
