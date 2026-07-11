"""Settings page — LLM configuration, prompt templates, app settings (admin only)."""
from __future__ import annotations
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, get_user

_PROVIDERS  = ["openai", "azure_openai", "anthropic", "ollama"]
_PROVIDER_MODELS = {
    "openai":       ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "azure_openai": ["gpt-4o", "gpt-4-turbo", "gpt-35-turbo"],
    "anthropic":    ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
    "ollama":       ["llama3.2", "llama3.1", "mistral", "codellama", "gemma2"],
}

_DEFAULT_PROMPTS = {
    "system_prompt": (
        "You are a software library upgrade advisor for enterprise mobile SDK teams. "
        "Analyse the library details provided and return a JSON object with exactly "
        "these keys: upgrade_recommended (one of: Yes, No, Sufficient), "
        "upgrade_pros (list of strings), upgrade_cons (list of strings), "
        "no_upgrade_pros (list of strings), no_upgrade_cons (list of strings), "
        "recommendation_summary (concise paragraph). "
        "Be specific and technical. Do not include markdown — pure JSON only."
    ),
    "user_template": (
        "SDK: {package}\nPlatform: {platform}\n"
        "Current version: {current}\nLatest version: {latest}\n"
        "Update priority: {update_needed}\nSDK status: {lib_status}\n"
        "New version released: {new_version}\n"
        "Release notes: {release_notes}\nDeprecation notes: {deprecation_notes}\n\n"
        "Generate the JSON recommendation object."
    ),
}


def render() -> None:
    st.title("⚙️ Settings")

    client = GatewayClient(token=get_token())
    username = (get_user() or {}).get("username", "admin")

    tab_llm, tab_prompts, tab_notif, tab_app = st.tabs([
        "🤖 LLM Configuration",
        "📝 Prompt Templates",
        "🔔 Notifications Config",
        "🔧 App Settings",
    ])

    # ══════════════════════════════════════════════════════════════════════
    # Tab 1 — LLM Configuration
    # ══════════════════════════════════════════════════════════════════════
    with tab_llm:
        st.subheader("LLM Provider Configuration")
        st.caption(
            "Configure which LLM provider powers the recommendation engine. "
            "Requires the recommendation-service to be restarted after saving for env-var changes to take effect."
        )

        try:
            cfg_resp = client.get_llm_config()
            cfg = cfg_resp.get("data", {})
        except APIError as exc:
            st.error(f"Could not load LLM config: {exc.detail}")
            cfg = {}

        # Status badge
        if cfg.get("enabled"):
            st.success("🟢 LLM is **enabled** — recommendations will use AI-generated analysis.")
        else:
            st.warning("⚪ LLM is **disabled** — recommendations use the rule-based engine.")

        st.divider()

        with st.form("llm_config_form"):
            col1, col2 = st.columns(2)

            provider = col1.selectbox(
                "Provider *",
                _PROVIDERS,
                index=_PROVIDERS.index(cfg.get("provider", "openai"))
                if cfg.get("provider") in _PROVIDERS else 0,
            )
            model_options = _PROVIDER_MODELS.get(provider, [])
            current_model = cfg.get("model_name", "")
            if current_model not in model_options:
                model_options = [current_model] + model_options if current_model else model_options
            model_name = col2.selectbox("Model *", model_options) if model_options else \
                         col2.text_input("Model *", value=cfg.get("model_name", "gpt-4o"))

            api_key_placeholder = "••••••••" if cfg.get("api_key_set") else "Enter API key..."
            api_key = st.text_input(
                "API Key" + (" (already set — leave blank to keep)" if cfg.get("api_key_set") else " *"),
                type="password",
                placeholder=api_key_placeholder,
            )

            col3, col4 = st.columns(2)
            api_base_url = col3.text_input(
                "API Base URL",
                value=cfg.get("api_base_url") or "",
                placeholder="https://your-resource.openai.azure.com (Azure / Ollama only)",
            )
            api_version = col4.text_input(
                "API Version",
                value=cfg.get("api_version") or "",
                placeholder="2024-08-01-preview (Azure only)",
            )

            col5, col6, col7 = st.columns(3)
            temperature = col5.slider(
                "Temperature", 0.0, 2.0,
                value=float(cfg.get("temperature", 0.3)), step=0.05,
            )
            max_tokens = col6.number_input(
                "Max Tokens", 64, 32768,
                value=int(cfg.get("max_tokens", 1024)), step=64,
            )
            timeout_sec = col7.number_input(
                "Timeout (s)", 5, 300,
                value=int(cfg.get("timeout_seconds", 30)),
            )

            enabled = st.toggle("Enable LLM for recommendations", value=bool(cfg.get("enabled", False)))

            save_btn = st.form_submit_button("💾 Save LLM Config", type="primary")

        if save_btn:
            payload: dict = {
                "provider": provider,
                "model_name": model_name,
                "api_base_url": api_base_url.strip() or None,
                "api_version": api_version.strip() or None,
                "temperature": temperature,
                "max_tokens": int(max_tokens),
                "timeout_seconds": int(timeout_sec),
                "enabled": enabled,
                "updated_by": username,
            }
            if api_key.strip():                    # only send if user typed something
                payload["api_key"] = api_key.strip()
            try:
                client.update_llm_config(payload)
                st.success("✅ LLM config saved. Restart the recommendation-service to apply.")
                st.rerun()
            except APIError as exc:
                st.error(f"Save failed: {exc.detail}")

        # ── Test LLM connectivity ──────────────────────────────────────────────
        st.divider()
        st.subheader("🧪 Test LLM Connectivity")
        st.caption("Sends a quick test request to the LLM provider via the recommendation-service.")
        if st.button("Run LLM Test", disabled=not cfg.get("enabled")):
            with st.spinner("Testing LLM…"):
                try:
                    result = client.test_llm()
                    data = result.get("data", {})
                    if data.get("llm_enabled"):
                        st.success(
                            f"✅ LLM working — provider: **{data.get('provider')}**  "
                            f"model: **{data.get('model')}**  "
                            f"latency: {data.get('latency_ms', '—')} ms"
                        )
                        if data.get("sample_recommendation"):
                            with st.expander("Sample recommendation"):
                                st.json(data["sample_recommendation"])
                    else:
                        st.warning(f"LLM not enabled: {data.get('message', '')}")
                except APIError as exc:
                    st.error(f"Test failed: {exc.detail}")
        if not cfg.get("enabled"):
            st.caption("Enable LLM above and save first.")

    # ══════════════════════════════════════════════════════════════════════
    # Tab 2 — Prompt Templates
    # ══════════════════════════════════════════════════════════════════════
    with tab_prompts:
        st.subheader("Prompt Templates")
        st.caption(
            "These templates are stored in the database and override the built-in prompts "
            "when the LLM generator runs. Use `{variable}` placeholders shown in the hints."
        )

        try:
            prompts_resp = client.get_prompts()
            prompts = prompts_resp.get("data") or []
        except APIError:
            prompts = []

        prompts_by_key = {p["prompt_key"]: p for p in prompts}

        for key, default_text in _DEFAULT_PROMPTS.items():
            existing = prompts_by_key.get(key, {})
            hint_map = {
                "system_prompt": "No variables — static system context",
                "user_template": "{package}, {platform}, {current}, {latest}, {update_needed}, {lib_status}, {new_version}, {release_notes}, {deprecation_notes}",
            }
            with st.expander(
                f"**{key}**"
                + (f"  — v{existing['version']}" if existing else "  — (using built-in default)"),
                expanded=not existing,
            ):
                if existing:
                    st.caption(f"Last updated by: {existing.get('updated_by','—')}  |  {existing.get('updated_at','')}")

                text_val = existing.get("template_text", default_text)
                new_text = st.text_area(
                    "Template text",
                    value=text_val,
                    height=200,
                    key=f"prompt_{key}",
                    help=hint_map.get(key, ""),
                )

                col_a, col_b = st.columns([1, 3])
                if col_a.button("💾 Save", key=f"save_prompt_{key}"):
                    try:
                        client.upsert_prompt(key, {
                            "template_text": new_text,
                            "variables_hint": hint_map.get(key),
                            "updated_by": username,
                        })
                        st.success(f"✅ `{key}` saved (version bumped).")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Save failed: {exc.detail}")
                if col_b.button("↩️ Reset to default", key=f"reset_prompt_{key}"):
                    try:
                        client.upsert_prompt(key, {
                            "template_text": default_text,
                            "variables_hint": hint_map.get(key),
                            "updated_by": username,
                        })
                        st.success(f"✅ `{key}` reset to default.")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Reset failed: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # Tab 3 — Notifications Config
    # ══════════════════════════════════════════════════════════════════════
    with tab_notif:
        st.subheader("Notification Channel Configuration")
        st.caption(
            "Configure Email (SMTP) and Microsoft Teams credentials here. "
            "These are saved to the database and used by the pipeline automatically — "
            "no .env editing or service restart required."
        )

        with st.spinner("Loading settings…"):
            try:
                app_cfg_raw = client.get_app_settings().get("data") or []
                app_cfg = {s["key"]: s for s in app_cfg_raw}
            except APIError:
                app_cfg = {}

        def _get(key, default=""):
            return (app_cfg.get(key) or {}).get("value", default)

        def _save(key, value):
            client.update_app_setting(key, value, updated_by=username)

        # ── EMAIL (SMTP) ───────────────────────────────────────────────────────
        st.markdown("#### 📧 Email (SMTP)")

        with st.form("email_smtp_form"):
            e_enabled = st.toggle(
                "Enable email notifications",
                value=_get("email_enabled","0") == "1",
                help="Must also fill in SMTP credentials below for emails to send."
            )
            c1, c2 = st.columns(2)
            smtp_host = c1.text_input("SMTP Host *",
                value=_get("smtp_host","smtp.office365.com"),
                placeholder="smtp.office365.com  or  smtp.gmail.com")
            smtp_port = c2.number_input("SMTP Port *",
                value=int(_get("smtp_port","587") or "587"), min_value=1, max_value=65535)
            c3, c4 = st.columns(2)
            smtp_user = c3.text_input("SMTP Username *",
                value=_get("smtp_username",""),
                placeholder="noreply@company.com")
            smtp_pass = c4.text_input("SMTP Password *",
                type="password",
                value="",
                placeholder="Leave blank to keep existing" if _get("smtp_password") else "Enter password")
            c5, c6 = st.columns(2)
            smtp_from = c5.text_input("From Address",
                value=_get("smtp_from_address",""),
                placeholder="SDK Manager <noreply@company.com>")
            smtp_tls  = c6.toggle("Use STARTTLS", value=_get("smtp_use_tls","1") == "1",
                help="Enable for port 587 (Office365, Gmail). Disable for port 465 (SSL).")
            recipients = st.text_area("Email Recipients (JSON array) *",
                value=_get("email_recipients","[]"),
                height=68,
                help='e.g. ["android-team@company.com", "ios-team@company.com"]')

            if st.form_submit_button("💾 Save Email Config", type="primary"):
                try:
                    _save("email_enabled",    "1" if e_enabled else "0")
                    _save("smtp_host",         smtp_host.strip())
                    _save("smtp_port",         str(int(smtp_port)))
                    _save("smtp_username",     smtp_user.strip())
                    _save("smtp_from_address", smtp_from.strip() or smtp_user.strip())
                    _save("smtp_use_tls",      "1" if smtp_tls else "0")
                    _save("email_recipients",  recipients.strip() or "[]")
                    if smtp_pass.strip():     # only overwrite if user typed something
                        _save("smtp_password", smtp_pass.strip())
                    st.success("✅ Email config saved. Will be used on the next pipeline run.")
                    st.rerun()
                except APIError as exc:
                    st.error(f"Save failed: {exc.detail}")

        # Quick send test
        st.markdown("**🧪 Send a test email**")
        st.caption("Tests with actual credentials saved above. Sends a short test message to the first recipient.")
        if st.button("Send Test Email", key="test_email_btn"):
            saved_user = _get("smtp_username")
            saved_pass = _get("smtp_password")
            saved_recs  = _get("email_recipients","[]")
            if not saved_user or not saved_pass:
                st.error("❌ SMTP credentials not saved yet. Fill in and save the form above first.")
            else:
                import json as _json
                try:
                    recs = _json.loads(saved_recs) if saved_recs else []
                except Exception:
                    recs = []
                if not recs:
                    st.error("❌ No email recipients saved. Add at least one email address above.")
                else:
                    with st.spinner("Sending test email…"):
                        try:
                            result = client._request("POST", "/api/v1/notify/email", json={
                                "libraries": [{
                                    "library_id": 1, "package": "test-notification",
                                    "platform": "Android", "current_version": "1.0",
                                    "latest_version": "1.1", "update_needed": "recommended",
                                    "upgrade_recommended": "Yes",
                                    "recommendation_summary": "This is a test notification from SDK Management."
                                }],
                                "recipients": recs,
                                "subject": "✅ SDK Management — Test Notification",
                                "force_send": True,
                                "smtp_override": {
                                    "host": _get("smtp_host","smtp.office365.com"),
                                    "port": int(_get("smtp_port","587") or "587"),
                                    "username": saved_user,
                                    "password": saved_pass,
                                    "from_address": _get("smtp_from_address", saved_user),
                                    "use_tls": _get("smtp_use_tls","1") == "1",
                                }
                            })
                            res_data = result.get("data",{})
                            for r in res_data.get("results",[]):
                                if r.get("status") == "sent":
                                    st.success(f"✅ Test email sent to {', '.join(recs)}")
                                elif r.get("status") == "failed":
                                    st.error(f"❌ Failed: {r.get('message','')}")
                                else:
                                    st.info(f"ℹ️ {r.get('status')}: {r.get('message','')}")
                        except APIError as exc:
                            st.error(f"Test failed: {exc.detail}")

        st.divider()

        # ── MICROSOFT TEAMS ────────────────────────────────────────────────────
        st.markdown("#### 💬 Microsoft Teams")
        with st.form("teams_notif_form"):
            t_enabled = st.toggle(
                "Enable Teams notifications",
                value=_get("teams_enabled","0") == "1",
                help="Must also fill in the webhook URL below."
            )
            webhook = st.text_input(
                "Incoming Webhook URL *",
                value=_get("teams_webhook_url",""),
                type="password",
                placeholder="https://company.webhook.office.com/webhookb2/…",
                help="In Microsoft Teams: right-click a channel → Connectors → Incoming Webhook → Create → Copy URL"
            )
            if st.form_submit_button("💾 Save Teams Config", type="primary"):
                try:
                    _save("teams_enabled",     "1" if t_enabled else "0")
                    if webhook.strip():
                        _save("teams_webhook_url", webhook.strip())
                    st.success("✅ Teams config saved. Will be used on the next pipeline run.")
                    st.rerun()
                except APIError as exc:
                    st.error(f"Save failed: {exc.detail}")

        st.markdown("**🧪 Send a test Teams message**")
        st.caption("Posts a short test card to your Teams channel using the webhook above.")
        if st.button("Send Test Teams Message", key="test_teams_btn"):
            saved_wh = _get("teams_webhook_url")
            if not saved_wh:
                st.error("❌ Teams webhook URL not saved yet. Fill in and save the form above first.")
            else:
                with st.spinner("Posting to Teams…"):
                    try:
                        result = client._request("POST", "/api/v1/notify/teams", json={
                            "libraries": [{
                                "library_id": 1, "package": "test-notification",
                                "platform": "Android", "current_version": "1.0",
                                "latest_version": "1.1", "update_needed": "recommended",
                                "upgrade_recommended": "Yes",
                                "recommendation_summary": "This is a test notification from SDK Management."
                            }],
                            "force_send": True,
                            "teams_webhook_override": saved_wh,
                        })
                        for r in (result.get("data",{}).get("results",[])):
                            if r.get("status") == "sent":
                                st.success("✅ Test message sent to Teams channel.")
                            elif r.get("status") == "failed":
                                st.error(f"❌ Failed: {r.get('message','')}")
                            else:
                                st.info(f"ℹ️ {r.get('status')}: {r.get('message','')}")
                    except APIError as exc:
                        st.error(f"Test failed: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    # Tab 4 — App Settings
    # ══════════════════════════════════════════════════════════════════════
    # Tab 3 — App Settings
    # ══════════════════════════════════════════════════════════════════════
    with tab_app:
        st.subheader("Application Settings")

        try:
            app_resp = client.get_app_settings()
            app_settings = app_resp.get("data") or []
        except APIError as exc:
            st.error(f"Could not load app settings: {exc.detail}")
            app_settings = []

        if not app_settings:
            st.info("No app settings configured yet.")
        else:
            st.caption(f"{len(app_settings)} settings stored in database")

            for s in app_settings:
                with st.expander(f"**{s['key']}**  — {s.get('description') or ''}"):
                    col1, col2 = st.columns([3, 1])
                    new_val = col1.text_input(
                        "Value",
                        value=s["value"],
                        type="password" if s.get("is_sensitive") else "default",
                        key=f"appsetting_{s['key']}",
                    )
                    if col2.button("💾 Save", key=f"savesetting_{s['key']}"):
                        try:
                            client.update_app_setting(s["key"], new_val, updated_by=username)
                            st.success("✅ Saved.")
                            st.rerun()
                        except APIError as exc:
                            st.error(f"Save failed: {exc.detail}")
                    if s.get("is_sensitive"):
                        st.caption("🔒 Sensitive value — masked in display")
                    else:
                        st.caption(f"Updated by: {s.get('updated_by','—')}  |  {s.get('updated_at','')}")
