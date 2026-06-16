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
            "ALTER TABLE bots ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR(64)",
            "bots.webhook_secret",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_tour_completed BOOLEAN NOT NULL DEFAULT FALSE",
            "users.onboarding_tour_completed",
        )
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
            "ALTER TABLE telegram_groups ADD COLUMN IF NOT EXISTS member_count_synced_at TIMESTAMP",
            "telegram_groups.member_count_synced_at",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_notes TEXT",
            "users.admin_notes",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_prefs JSON",
            "users.notification_prefs",
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

        # ── AI usage ledger (Phase 5 admin overhaul) ──────────────────────────
        # The ai_token_usage table + its indexes are created by db.create_all()
        # above (model: AITokenUsage). No ALTER needed — new table. Noted here so
        # the migration intent is documented alongside the other analytics tables.

        # ── Bot Health Center: error classification columns (Part 6) ──────────
        # bot_health_events / ai_activity tables are created by db.create_all();
        # these ALTERs add the new columns when the table already existed.
        _run_alter(
            db.engine,
            "ALTER TABLE bot_health_events ADD COLUMN IF NOT EXISTS severity VARCHAR(10)",
            "bot_health_events.severity",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE bot_health_events ADD COLUMN IF NOT EXISTS error_class VARCHAR(40)",
            "bot_health_events.error_class",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_bot_health_events_severity ON bot_health_events (severity)",
            "bot_health_events.severity index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_ai_activity_group_created ON ai_activity (scope, group_ref, created_at)",
            "ai_activity composite index",
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

        # ── Dual-side bot mirroring: cross-reference columns ─────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE custom_bots ADD COLUMN IF NOT EXISTS hub_bot_id VARCHAR(36) REFERENCES hub_bot_identities(id) ON DELETE SET NULL",
            "custom_bots.hub_bot_id (link to hub identity)",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_custom_bots_hub_bot_id ON custom_bots (hub_bot_id)",
            "custom_bots.hub_bot_id index",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE hub_bot_identities ADD COLUMN IF NOT EXISTS custom_bot_id INTEGER",
            "hub_bot_identities.custom_bot_id (link to group-management bot)",
        )
        _run_alter(
            db.engine,
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_hub_bot_custom_bot') THEN "
            "ALTER TABLE hub_bot_identities ADD CONSTRAINT fk_hub_bot_custom_bot "
            "FOREIGN KEY (custom_bot_id) REFERENCES custom_bots(id) ON DELETE SET NULL; "
            "END IF; END $$",
            "hub_bot_identities.custom_bot_id FK constraint",
        )

        _backfill_bot_mirror_links(app)

        # ── Forum topic cache table ───────────────────────────────────────────────
        # db.create_all() above handles the new table; add indexes idempotently.
        _run_alter(
            db.engine,
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_forum_topic_group_thread "
            "ON group_forum_topics (telegram_group_id, thread_id)",
            "group_forum_topics unique index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_group_forum_topics_group "
            "ON group_forum_topics (telegram_group_id)",
            "group_forum_topics.telegram_group_id index",
        )

        # ── groups.chat_type column ───────────────────────────────────────────────
        # Stores the Telegram chat type (group|supergroup|channel|private).
        # Existing rows default to 'group' which is safe — they were all created
        # from real group/supergroup events before this column existed.
        _run_alter(
            db.engine,
            "ALTER TABLE groups ADD COLUMN IF NOT EXISTS chat_type VARCHAR(20) NOT NULL DEFAULT 'group'",
            "groups.chat_type column",
        )

        # ── groups.chat_username column ──────────────────────────────────────────
        # NULL = not yet resolved (old records).
        # ""   = confirmed private (no @username).
        # Non-empty = public group with @username.
        _run_alter(
            db.engine,
            "ALTER TABLE groups ADD COLUMN IF NOT EXISTS chat_username VARCHAR(255)",
            "groups.chat_username column",
        )

        # ── Global escalation events table ────────────────────────────────────────
        # db.create_all() creates the table; add indexes idempotently.
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_escalation_events_group_id "
            "ON escalation_events (group_id)",
            "escalation_events.group_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_escalation_events_telegram_group_id "
            "ON escalation_events (telegram_group_id)",
            "escalation_events.telegram_group_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_escalation_events_status "
            "ON escalation_events (status)",
            "escalation_events.status index",
        )

        # ── GDPR: account soft-delete and suspension columns ─────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
            "users.deleted_at (soft-delete for GDPR)",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN NOT NULL DEFAULT FALSE",
            "users.is_suspended",
        )

        # ── AUP: Acceptable Use Policy acceptance tracking ────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS aup_accepted_at TIMESTAMP",
            "users.aup_accepted_at",
        )

        # ── KB isolation: enforce NOT NULL on workspace_knowledge_documents.user_id ─
        # Safe to run — all existing rows must have a user_id (FK required at insert).
        _run_alter(
            db.engine,
            "ALTER TABLE workspace_knowledge_documents ALTER COLUMN user_id SET NOT NULL",
            "workspace_knowledge_documents.user_id NOT NULL",
        )

        # ── Payment abuse tracking ────────────────────────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS chargeback_count INTEGER NOT NULL DEFAULT 0",
            "users.chargeback_count",
        )

        # ── Phase 4: Auto-knowledge capture columns ───────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE hub_connected_groups ADD COLUMN IF NOT EXISTS is_knowledge_channel BOOLEAN NOT NULL DEFAULT FALSE",
            "hub_connected_groups.is_knowledge_channel",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE hub_knowledge_cards ADD COLUMN IF NOT EXISTS embedding TEXT",
            "hub_knowledge_cards.embedding",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE hub_knowledge_cards ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'manual'",
            "hub_knowledge_cards.source",
        )

        # ── Phase 3: Community reply settings on hub_bot_settings ────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE hub_bot_settings ADD COLUMN IF NOT EXISTS reply_sensitivity VARCHAR(10) DEFAULT 'medium'",
            "hub_bot_settings.reply_sensitivity",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE hub_bot_settings ADD COLUMN IF NOT EXISTS escalation_contact BIGINT",
            "hub_bot_settings.escalation_contact",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE hub_bot_settings ADD COLUMN IF NOT EXISTS tone VARCHAR(20) DEFAULT 'friendly'",
            "hub_bot_settings.tone",
        )

        # ── Member CRM fields (custom-bot group parity) ───────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE members ADD COLUMN IF NOT EXISTS crm_tags JSONB",
            "members.crm_tags",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE members ADD COLUMN IF NOT EXISTS crm_notes TEXT",
            "members.crm_notes",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE members ADD COLUMN IF NOT EXISTS engagement_score INTEGER",
            "members.engagement_score",
        )

        # ── official_warnings.message_text — store the offending message text ──
        _run_alter(
            db.engine,
            "ALTER TABLE official_warnings ADD COLUMN IF NOT EXISTS message_text TEXT",
            "official_warnings.message_text",
        )

        # ── P3-3: Google Calendar — token table (db.create_all handles creation) ─
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_google_calendar_tokens_user_id ON google_calendar_tokens (user_id)",
            "google_calendar_tokens.user_id index",
        )

        # ── P3-1: Semantic search — embedding column on hub_notes ────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE hub_notes ADD COLUMN IF NOT EXISTS embedding TEXT",
            "hub_notes.embedding (semantic search)",
        )

        # ── P2-7: Meeting URL column on hub_meetings ──────────────────────────────
        _run_alter(
            db.engine,
            "ALTER TABLE hub_meetings ADD COLUMN IF NOT EXISTS meeting_url VARCHAR(500)",
            "hub_meetings.meeting_url",
        )

        # ── Promo codes (db.create_all handles table creation) ────────────────────
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_promo_codes_code ON promo_codes (code)",
            "promo_codes.code index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_promo_code_usages_promo_code_id ON promo_code_usages (promo_code_id)",
            "promo_code_usages.promo_code_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_promo_code_usages_user_id ON promo_code_usages (user_id)",
            "promo_code_usages.user_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_promo_code_usages_order_id ON promo_code_usages (order_id)",
            "promo_code_usages.order_id index",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE promo_code_usages ADD COLUMN IF NOT EXISTS confirmed BOOLEAN NOT NULL DEFAULT FALSE",
            "promo_code_usages.confirmed",
        )

        # ── L7: Mirror legacy AssistantBot rows into HubBotIdentity ──────────────
        # Registers each AssistantBot token under the new hub routing system so
        # custom bots benefit from hub handlers going forward.
        # AssistantBot rows are kept active for backward compatibility — the old
        # assistant_bot_handler path still fires first for existing rows.
        _migrate_assistant_bots_to_hub(app)

        # ── Telegram-first auth: make email/password optional ─────────────────────
        # Pre-flight check: abort if any user has BOTH email=NULL AND
        # telegram_user_id=NULL — that would violate the identity constraint.
        # (Should be zero rows on a clean DB.)
        _run_alter(
            db.engine,
            "DO $$ BEGIN "
            "  IF EXISTS (SELECT 1 FROM users WHERE email IS NULL AND telegram_user_id IS NULL) THEN "
            "    RAISE EXCEPTION 'Aborting: found users with neither email nor telegram_user_id. Fix these rows first.'; "
            "  END IF; "
            "END $$",
            "users: pre-flight identity check (email OR telegram_user_id required)",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ALTER COLUMN email DROP NOT NULL",
            "users.email nullable (Telegram-first auth)",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL",
            "users.password_hash nullable (Telegram-first auth)",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ALTER COLUMN full_name DROP NOT NULL",
            "users.full_name nullable (Telegram-first auth)",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) NOT NULL DEFAULT 'email'",
            "users.auth_provider ('email' | 'telegram' | 'both')",
        )
        # Backfill auth_provider for any existing users with Telegram already linked
        _run_alter(
            db.engine,
            "UPDATE users SET auth_provider = 'both' "
            "WHERE telegram_user_id IS NOT NULL AND email IS NOT NULL AND auth_provider = 'email'",
            "users.auth_provider backfill → 'both' for existing linked accounts",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_link_pending VARCHAR(255)",
            "users.email_link_pending (Mini App OTP flow)",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_link_otp_hash VARCHAR(64)",
            "users.email_link_otp_hash",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_link_otp_expires TIMESTAMP",
            "users.email_link_otp_expires",
        )
        # Safety constraint: every row must have email OR telegram_user_id (not both NULL)
        _run_alter(
            db.engine,
            "ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_one_identity",
            "users: drop old identity constraint if exists",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD CONSTRAINT chk_one_identity "
            "CHECK (email IS NOT NULL OR telegram_user_id IS NOT NULL)",
            "users: chk_one_identity constraint (email OR telegram_user_id required)",
        )

        # Telegram referral capture: ref code stashed at `/start ref_<code>` until
        # the Mini App auto-creates the user (telegram_bot_started.pending_referral_code).
        _run_alter(
            db.engine,
            "ALTER TABLE telegram_bot_started ADD COLUMN IF NOT EXISTS pending_referral_code VARCHAR(16)",
            "telegram_bot_started.pending_referral_code (Telegram referral attribution)",
        )

        # ── Engagement Campaigns engine (db.create_all handles table creation) ───
        # New tables: engagement_campaigns / engagement_custom_fields /
        # engagement_submissions. Indexes are created with the tables on a fresh
        # DB; these run idempotently in case a table already existed.
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_campaigns_group_id "
            "ON engagement_campaigns (group_id)",
            "engagement_campaigns.group_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_campaigns_telegram_group_id "
            "ON engagement_campaigns (telegram_group_id)",
            "engagement_campaigns.telegram_group_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_campaigns_owner_user_id "
            "ON engagement_campaigns (owner_user_id)",
            "engagement_campaigns.owner_user_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_campaigns_status "
            "ON engagement_campaigns (status)",
            "engagement_campaigns.status index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_custom_fields_campaign_id "
            "ON engagement_custom_fields (campaign_id)",
            "engagement_custom_fields.campaign_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_submissions_campaign_user "
            "ON engagement_submissions (campaign_id, telegram_user_id)",
            "engagement_submissions (campaign_id, telegram_user_id) index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_submissions_campaign_status "
            "ON engagement_submissions (campaign_id, status)",
            "engagement_submissions (campaign_id, status) index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_submissions_file_hash "
            "ON engagement_submissions (file_hash)",
            "engagement_submissions.file_hash index",
        )
        # Phase 6: anti-fraud flag columns
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_submissions ADD COLUMN IF NOT EXISTS flagged BOOLEAN NOT NULL DEFAULT FALSE",
            "engagement_submissions.flagged",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_submissions ADD COLUMN IF NOT EXISTS flag_reason VARCHAR(255)",
            "engagement_submissions.flag_reason",
        )
        # Group-post delivery tracking + proof examples + review-notify result.
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_campaigns ADD COLUMN IF NOT EXISTS post_status VARCHAR(16) NOT NULL DEFAULT 'none'",
            "engagement_campaigns.post_status",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_campaigns ADD COLUMN IF NOT EXISTS post_error TEXT",
            "engagement_campaigns.post_error",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_campaigns ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP",
            "engagement_campaigns.posted_at",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_custom_fields ADD COLUMN IF NOT EXISTS example VARCHAR(255)",
            "engagement_custom_fields.example",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_submissions ADD COLUMN IF NOT EXISTS notify_status VARCHAR(16) NOT NULL DEFAULT 'none'",
            "engagement_submissions.notify_status",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_submissions ADD COLUMN IF NOT EXISTS notify_error VARCHAR(255)",
            "engagement_submissions.notify_error",
        )

        # ── V2: Multi-task campaigns (engagement_tasks created by create_all) ────
        # A proof field now belongs to EITHER a campaign or a task, so campaign_id
        # must be nullable; submissions/fields gain task_id.
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_custom_fields ALTER COLUMN campaign_id DROP NOT NULL",
            "engagement_custom_fields.campaign_id nullable (multi-task)",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_custom_fields ADD COLUMN IF NOT EXISTS task_id INTEGER "
            "REFERENCES engagement_tasks(id) ON DELETE CASCADE",
            "engagement_custom_fields.task_id",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_custom_fields_task_id "
            "ON engagement_custom_fields (task_id)",
            "engagement_custom_fields.task_id index",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE engagement_submissions ADD COLUMN IF NOT EXISTS task_id INTEGER "
            "REFERENCES engagement_tasks(id) ON DELETE CASCADE",
            "engagement_submissions.task_id",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_submissions_task_id "
            "ON engagement_submissions (task_id)",
            "engagement_submissions.task_id index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_submissions_campaign_task_user "
            "ON engagement_submissions (campaign_id, task_id, telegram_user_id)",
            "engagement_submissions (campaign_id, task_id, telegram_user_id) index",
        )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_engagement_tasks_campaign_id "
            "ON engagement_tasks (campaign_id)",
            "engagement_tasks.campaign_id index",
        )

        # ── Automation Consolidation: forwarding many→many + topics (Phase 0) ──
        # forward_sources / forward_destinations tables are created by
        # db.create_all() above; here we add the new legacy columns and backfill
        # one source/destination child row per existing rule.
        _run_alter(
            db.engine,
            "ALTER TABLE forward_rules ADD COLUMN IF NOT EXISTS source_topic_id INTEGER",
            "forward_rules.source_topic_id",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE forward_logs ADD COLUMN IF NOT EXISTS destination_topic_id INTEGER",
            "forward_logs.destination_topic_id",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE forward_destinations ADD COLUMN IF NOT EXISTS fail_count INTEGER NOT NULL DEFAULT 0",
            "forward_destinations.fail_count",
        )
        _run_alter(
            db.engine,
            "ALTER TABLE forward_logs ADD COLUMN IF NOT EXISTS bot_id INTEGER",
            "forward_logs.bot_id",
        )
        _run_alter(
            db.engine,
            """
            INSERT INTO forward_sources (rule_id, source_chat_id, source_topic_id, created_at)
            SELECT id, source_group_id, source_topic_id, created_at FROM forward_rules fr
            WHERE NOT EXISTS (
                SELECT 1 FROM forward_sources fs WHERE fs.rule_id = fr.id
            )
            """,
            "forward_sources backfill",
        )
        _run_alter(
            db.engine,
            """
            INSERT INTO forward_destinations
                (rule_id, destination_id, topic_id, is_paused, forward_count, created_at)
            SELECT id, destination_id, NULL, FALSE, forward_count, created_at FROM forward_rules fr
            WHERE NOT EXISTS (
                SELECT 1 FROM forward_destinations fd WHERE fd.rule_id = fr.id
            )
            """,
            "forward_destinations backfill",
        )

        # ── Admin RBAC (Phase 1 admin-panel overhaul) ──
        _run_alter(
            db.engine,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_role VARCHAR(20)",
            "users.admin_role",
        )
        for col, ddl in (
            ("severity", "VARCHAR(10)"),
            ("target_type", "VARCHAR(40)"),
            ("target_id", "VARCHAR(64)"),
            ("old_value", "TEXT"),
            ("new_value", "TEXT"),
            # Phase 8 — critical-action resolution tracking.
            ("resolved_at", "TIMESTAMP"),
            ("resolved_by", "INTEGER"),
        ):
            _run_alter(
                db.engine,
                f"ALTER TABLE admin_audit_logs ADD COLUMN IF NOT EXISTS {col} {ddl}",
                f"admin_audit_logs.{col}",
            )
        _run_alter(
            db.engine,
            "CREATE INDEX IF NOT EXISTS ix_admin_audit_sev_resolved ON admin_audit_logs (severity, resolved_at)",
            "admin_audit_logs (severity, resolved_at) index",
        )

        # ── Backfill: create UserTelegramAccount rows for legacy User.telegram_user_id ──
        # Must run AFTER all users-table ALTER statements (including auth_provider)
        # so SQLAlchemy's User model doesn't query columns that don't exist yet.
        _backfill_telegram_accounts(app)

        print("Migration complete.")

    # One-shot Telegram account backfill (see above).
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


def _backfill_bot_mirror_links(app):
    """Link existing CustomBot ↔ HubBotIdentity records that predate the dual-side feature.

    Matches on (user_id, bot_username) — safe to run multiple times (skips already-linked rows).
    """
    from .models import db, CustomBot
    from .assistant.hub_models import HubBotIdentity
    with app.app_context():
        unlinked = CustomBot.query.filter(CustomBot.hub_bot_id.is_(None)).all()
        linked = 0
        for cb in unlinked:
            hub = HubBotIdentity.query.filter_by(
                user_id=cb.owner_user_id,
                telegram_bot_username=cb.bot_username,
                bot_type="custom",
                is_active=True,
            ).first()
            if hub:
                cb.hub_bot_id = hub.id
                hub.custom_bot_id = cb.id
                linked += 1
        if linked:
            db.session.commit()
            print(f"  ✓ Backfilled {linked} CustomBot ↔ HubBotIdentity links")
        else:
            print("  – Bot mirror backfill: no unlinked pairs found")


def _migrate_assistant_bots_to_hub(app):
    """Mirror each active AssistantBot row into HubBotIdentity (bot_type='custom').

    Idempotent — skips any bot whose token is already registered as a HubBotIdentity.
    AssistantBot rows are NOT deactivated so the legacy assistant_bot_handler path
    continues to work for existing users. The HubBotIdentity row ensures the same
    token is also visible to the hub routing path once the AssistantBot path is retired.
    """
    import uuid as _uuid
    from .models import db, AssistantBot
    from .assistant.hub_models import HubBotIdentity, HubBotSettings

    with app.app_context():
        bots = AssistantBot.query.filter_by(is_active=True).all()
        created = 0
        for ab in bots:
            token = ab.bot_token  # decrypted via property
            if not token:
                continue
            # Check by username first (token may be re-encrypted between runs)
            existing = HubBotIdentity.query.filter_by(
                user_id=ab.user_id,
                bot_type="custom",
                telegram_bot_username=ab.bot_username,
            ).first()
            if existing:
                continue
            hub = HubBotIdentity(
                id=str(_uuid.uuid4()),
                user_id=ab.user_id,
                bot_type="custom",
                display_name=ab.bot_name or ab.bot_username or "My Bot",
                telegram_bot_token=token,
                telegram_bot_username=ab.bot_username,
                is_active=True,
            )
            db.session.add(hub)
            db.session.flush()
            settings = HubBotSettings(
                id=str(_uuid.uuid4()),
                bot_id=hub.id,
                user_id=ab.user_id,
            )
            db.session.add(settings)
            created += 1

        if created:
            db.session.commit()
            print(f"  ✓ Mirrored {created} AssistantBot row(s) → HubBotIdentity")
        else:
            print("  – AssistantBot → HubBotIdentity: all already mirrored or none exist")


def init_hub_db():
    """Apply Sprint 1 Assistant Hub schema — idempotent, safe to re-run."""
    app = create_app()
    with app.app_context():
        # Import hub models so SQLAlchemy knows about them before create_all
        from .assistant import hub_models  # noqa: F401

        db.create_all()
        print("Assistant Hub tables created (new tables only).")

        # Column additions (P2-7 meeting URL capture)
        _run_alter(
            db.engine,
            "ALTER TABLE hub_meetings ADD COLUMN IF NOT EXISTS meeting_url VARCHAR(500)",
            "hub_meetings.meeting_url",
        )

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
