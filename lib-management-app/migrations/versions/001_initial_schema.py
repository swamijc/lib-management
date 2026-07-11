"""
Migration 001: Add all new tables defined in architecture document v2.4
Sections 6 (gap tables) + B1-B4 (business gaps) + T1, T5, T11 (tech gaps)

Existing tables (already in DB from PDF import):
  libraries, version_history, recommendations, notifications, scrape_log

Tables added here:
  users, llm_config, llm_prompt_templates, scraper_registry_config,
  app_settings, library_update_log, library_external_sources,
  pipeline_runs, pipeline_run_details, notification_schedule,
  upgrade_lifecycle, notification_sent_log, bulk_import_job,
  application_teams, library_ownership, scrape_cache, llm_usage_log
  + immutability triggers on library_update_log
  + new columns on libraries table (alert_priority, deadline_date,
    deadline_notes, ecosystem, framework_language)
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("full_name", sa.Text),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text, server_default=sa.func.datetime("now")),
        sa.Column("last_login", sa.Text),
        sa.CheckConstraint("role IN ('admin','viewer')", name="ck_users_role"),
    )

    # ── LLM Config ───────────────────────────────────────────────────────────
    op.create_table(
        "llm_config",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.Text, nullable=False, server_default="openai"),
        sa.Column("model_name", sa.Text, nullable=False, server_default="gpt-4o"),
        sa.Column("api_base_url", sa.Text),
        sa.Column("api_key_encrypted", sa.Text),
        sa.Column("api_version", sa.Text),
        sa.Column("temperature", sa.Float, nullable=False, server_default="0.3"),
        sa.Column("max_tokens", sa.Integer, nullable=False, server_default="1024"),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="30"),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_by", sa.Text),
        sa.Column("updated_at", sa.Text, server_default=sa.func.datetime("now")),
        sa.CheckConstraint(
            "provider IN ('openai','azure_openai','anthropic','ollama')",
            name="ck_llm_provider",
        ),
    )

    # ── LLM Prompt Templates ─────────────────────────────────────────────────
    op.create_table(
        "llm_prompt_templates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prompt_key", sa.Text, nullable=False, unique=True),
        sa.Column("template_text", sa.Text, nullable=False),
        sa.Column("variables_hint", sa.Text),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Text),
        sa.Column("updated_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Scraper Registry Config ───────────────────────────────────────────────
    op.create_table(
        "scraper_registry_config",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("registry_key", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("ecosystem", sa.Text, nullable=False, server_default="mobile"),
        sa.Column("framework_language", sa.Text),
        sa.Column("base_url", sa.Text),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="10"),
        sa.Column("rate_limit_per_min", sa.Integer, nullable=False, server_default="60"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("circuit_breaker_threshold", sa.Integer, nullable=False, server_default="5"),
        sa.Column("circuit_breaker_cooldown", sa.Integer, nullable=False, server_default="60"),
        sa.Column("custom_headers", sa.Text),
        sa.Column("strategy_class", sa.Text),
        sa.Column("release_phase", sa.Text, nullable=False, server_default="mvp"),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Text),
        sa.Column("updated_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── App Settings (key-value store for all runtime config) ─────────────────
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_sensitive", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_by", sa.Text),
        sa.Column("updated_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Library Update Audit Log (append-only) ───────────────────────────────
    op.create_table(
        "library_update_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
        sa.Column("update_type", sa.Text, nullable=False),
        sa.Column("field_changed", sa.Text, nullable=False),
        sa.Column("old_value", sa.Text),
        sa.Column("new_value", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("updated_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Library External Sources ──────────────────────────────────────────────
    op.create_table(
        "library_external_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("source_type", sa.Text, nullable=False, server_default="custom"),
        sa.Column("added_by", sa.Text, nullable=False),
        sa.Column("is_active", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Pipeline Runs ─────────────────────────────────────────────────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text, nullable=False, unique=True),
        sa.Column("triggered_by", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        sa.Column("libraries_processed", sa.Integer, server_default="0"),
        sa.Column("libraries_updated", sa.Integer, server_default="0"),
        sa.Column("errors_count", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.Text, server_default=sa.func.datetime("now")),
        sa.Column("finished_at", sa.Text),
    )

    # ── Pipeline Run Details ─────────────────────────────────────────────────
    op.create_table(
        "pipeline_run_details",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text, sa.ForeignKey("pipeline_runs.run_id"), nullable=False),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id")),
        sa.Column("step", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("message", sa.Text),
        sa.Column("recorded_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Notification Schedule Config ─────────────────────────────────────────
    op.create_table(
        "notification_schedule",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("cron_expression", sa.Text, nullable=False, server_default="0 8 * * 1"),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
        sa.Column("channels", sa.Text, nullable=False, server_default="both"),
        sa.Column("email_recipients", sa.Text),
        sa.Column("teams_webhook_url", sa.Text),
        sa.Column("updated_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Upgrade Lifecycle (B1) ────────────────────────────────────────────────
    op.create_table(
        "upgrade_lifecycle",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("recommendation_id", sa.Integer, sa.ForeignKey("recommendations.id")),
        sa.Column("status", sa.Text, nullable=False, server_default="Pending"),
        sa.Column("target_version", sa.Text),
        sa.Column("target_sprint", sa.Text),
        sa.Column("target_date", sa.Text),
        sa.Column("completed_version", sa.Text),
        sa.Column("skip_reason", sa.Text),
        sa.Column("actioned_by", sa.Text),
        sa.Column("created_at", sa.Text, server_default=sa.func.datetime("now")),
        sa.Column("updated_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Notification Sent Log / Dedup (B2) ────────────────────────────────────
    op.create_table(
        "notification_sent_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("notification_id", sa.Integer, sa.ForeignKey("notifications.id")),
        sa.Column("latest_version_at_send", sa.Text),
        sa.Column("update_needed_at_send", sa.Text),
        sa.Column("status_at_send", sa.Text),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("sent_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Bulk Import Job (B3) ──────────────────────────────────────────────────
    op.create_table(
        "bulk_import_job",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Text, nullable=False, unique=True),
        sa.Column("import_format", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("total_rows", sa.Integer, server_default="0"),
        sa.Column("imported", sa.Integer, server_default="0"),
        sa.Column("skipped", sa.Integer, server_default="0"),
        sa.Column("failed", sa.Integer, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="processing"),
        sa.Column("error_log", sa.Text),
        sa.Column("imported_by", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, server_default=sa.func.datetime("now")),
        sa.Column("finished_at", sa.Text),
    )

    # ── Application Teams + Library Ownership (B4) ────────────────────────────
    op.create_table(
        "application_teams",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("team_name", sa.Text, nullable=False, unique=True),
        sa.Column("team_email", sa.Text),
        sa.Column("teams_channel", sa.Text),
        sa.Column("created_at", sa.Text, server_default=sa.func.datetime("now")),
    )
    op.create_table(
        "library_ownership",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("application_teams.id"), nullable=False),
        sa.Column("is_primary", sa.Integer, nullable=False, server_default="1"),
        sa.Column("assigned_by", sa.Text, nullable=False),
        sa.Column("assigned_at", sa.Text, server_default=sa.func.datetime("now")),
        sa.UniqueConstraint("library_id", "team_id", name="uq_lib_ownership"),
    )

    # ── Scrape Cache / TTL (T1) ───────────────────────────────────────────────
    op.create_table(
        "scrape_cache",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("registry_key", sa.Text, nullable=False),
        sa.Column("scraped_version", sa.Text, nullable=False),
        sa.Column("release_notes", sa.Text),
        sa.Column("raw_response", sa.Text),
        sa.Column("expires_at", sa.Text, nullable=False),
        sa.Column("scraped_at", sa.Text, server_default=sa.func.datetime("now")),
        sa.UniqueConstraint("library_id", "registry_key", name="uq_scrape_cache"),
    )

    # ── LLM Usage / Cost Log (T5) ─────────────────────────────────────────────
    op.create_table(
        "llm_usage_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text, sa.ForeignKey("pipeline_runs.run_id")),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id")),
        sa.Column("prompt_key", sa.Text),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("logged_at", sa.Text, server_default=sa.func.datetime("now")),
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index("idx_upd_log_library", "library_update_log", ["library_id"])
    op.create_index("idx_pipeline_status", "pipeline_runs", ["status"])
    op.create_index("idx_scrape_cache_expiry", "scrape_cache", ["expires_at"])
    op.create_index("idx_notif_sent_library", "notification_sent_log", ["library_id"])
    op.create_index("idx_lifecycle_library", "upgrade_lifecycle", ["library_id"])
    op.create_index("idx_llm_usage_run", "llm_usage_log", ["run_id"])

    # ── New columns on libraries table (B7 critical alerts + multi-framework) ─
    op.add_column("libraries", sa.Column("alert_priority", sa.Text, server_default="Normal"))
    op.add_column("libraries", sa.Column("deadline_date", sa.Text))
    op.add_column("libraries", sa.Column("deadline_notes", sa.Text))
    op.add_column("libraries", sa.Column("ecosystem", sa.Text, server_default="mobile"))
    op.add_column("libraries", sa.Column("framework_language", sa.Text))

    # ── Immutability triggers on library_update_log (T11) ────────────────────
    # Raw SQL triggers — not expressible via Alembic column API
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS audit_log_immutable_update
            BEFORE UPDATE ON library_update_log
        BEGIN
            SELECT RAISE(ABORT, 'library_update_log is immutable — no updates allowed');
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS audit_log_immutable_delete
            BEFORE DELETE ON library_update_log
        BEGIN
            SELECT RAISE(ABORT, 'library_update_log is immutable — no deletes allowed');
        END
    """)

    # ── Seed data ────────────────────────────────────────────────────────────
    # Default scraper registry configs (MVP registries)
    op.execute("""
        INSERT INTO scraper_registry_config
            (registry_key, display_name, ecosystem, framework_language,
             base_url, timeout_seconds, rate_limit_per_min, release_phase)
        VALUES
            ('maven',     'Maven Central',       'mobile',  'kotlin',
             'https://search.maven.org/solrsearch/select', 10, 60, 'mvp'),
            ('cocoapods', 'CocoaPods Trunk',      'mobile',  'swift',
             'https://trunk.cocoapods.org/api/v1/pods', 10, 30, 'mvp'),
            ('spm',       'Swift Package Index',  'mobile',  'swift',
             'https://swiftpackageindex.com/api/packages', 10, 30, 'mvp'),
            ('github',    'GitHub Releases',      'mobile',  NULL,
             'https://api.github.com/repos', 15, 60, 'mvp'),
            ('custom',    'Custom HTTP',          'mobile',  NULL,
             NULL, 10, 30, 'mvp')
    """)

    # Default notification schedule (Monday 8am UTC)
    op.execute("""
        INSERT INTO notification_schedule (cron_expression, enabled, channels)
        VALUES ('0 8 * * 1', 1, 'both')
    """)

    # Default app settings
    op.execute("""
        INSERT INTO app_settings (key, value, description, is_sensitive) VALUES
            ('schedule_cron',                 '0 8 * * 1', 'Pipeline cron expression', 0),
            ('schedule_timezone',             'UTC',        'Cron timezone (IANA)', 0),
            ('schedule_enabled',              '1',          'Enable scheduled pipeline', 0),
            ('email_enabled',                 '0',          'Enable email notifications', 0),
            ('teams_enabled',                 '0',          'Enable Teams notifications', 0),
            ('email_recipients',              '[]',         'JSON array of email recipients', 0),
            ('scraper_cache_ttl_hours',       '6',          'Scrape cache TTL in hours', 0),
            ('db_backup_keep_count',          '7',          'Number of DB backups to keep', 0),
            ('retention_version_history_days','365',        'Keep version history N days', 0),
            ('retention_scrape_log_days',     '90',         'Keep scrape log N days', 0),
            ('retention_pipeline_run_days',   '180',        'Keep pipeline run details N days', 0),
            ('retention_notification_log_days','365',       'Keep notification log N days', 0),
            ('retention_library_update_log_days','730',     'Keep audit log N days', 0)
    """)

    # Pre-seed ACI-OPPWAMobile as Critical (B7 — Mastercard cert expiry)
    op.execute("""
        UPDATE libraries SET
            alert_priority = 'Critical',
            deadline_date  = '2026-07-15',
            deadline_notes = 'Mastercard certificate expires 15 July 2026. '
                             'Must upgrade to mSDK 7.11.0 + IPWorks 2.4.9625 by 7 July 2026.'
        WHERE package LIKE '%OPPWA%' OR package LIKE '%ipworks%'
           OR sdk_name LIKE '%OPPWA%' OR sdk_name LIKE '%ipworks%'
    """)


def downgrade() -> None:
    # Drop triggers first (SQLite-specific)
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutable_update")
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutable_delete")

    # Drop new columns from libraries
    # Note: SQLite doesn't support DROP COLUMN before 3.35; use recreate approach in prod
    # op.drop_column("libraries", "alert_priority")  # handled manually if needed

    for table in [
        "llm_usage_log", "scrape_cache", "library_ownership", "application_teams",
        "bulk_import_job", "notification_sent_log", "upgrade_lifecycle",
        "notification_schedule", "pipeline_run_details", "pipeline_runs",
        "library_external_sources", "library_update_log",
        "app_settings", "scraper_registry_config", "llm_prompt_templates",
        "llm_config", "users",
    ]:
        op.drop_table(table)
