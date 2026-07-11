"""Package Profile page — detailed library view: CVE, release notes, lifecycle, teams, chat stub."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, get_user, is_admin
from src.utils.formatters import format_datetime, format_registry

_UPDATE_BADGE = {"mandatory":"🚨 Mandatory","recommended":"⚠️ Recommended","none":"✅ None","optional":"✅ Optional"}
_STATUS_BADGE = {"Active":"🟢 Active","Deprecated":"🔴 Deprecated","Legacy":"🟡 Legacy","Maintenance":"🔵 Maintenance","Unknown":"❓ Unknown"}


def render() -> None:
    st.title("📦 Package Profile")
    client  = GatewayClient(token=get_token())
    username = (get_user() or {}).get("username","user")

    # ── SDK selector ──────────────────────────────────────────────────────
    with st.spinner("Loading libraries…"):
        try:
            libs = client.get_libraries().get("data",{}).get("libraries",[])
        except APIError as exc:
            st.error(f"Failed to load libraries: {exc.detail}"); return

    options = {f"[{l['id']}] {l.get('sdk_name') or l.get('package','—')} ({l.get('platform','—')})": l for l in libs}
    selected_key = st.selectbox("Select SDK", list(options.keys()))
    lib = options[selected_key]
    lid = lib["id"]

    # ── Header ────────────────────────────────────────────────────────────────
    un    = (lib.get("update_needed") or "").lower()
    badge = _UPDATE_BADGE.get(un, un or "—")
    icon  = badge.split()[0] if badge else "📦"
    st.markdown(f"## {icon} {lib.get('sdk_name') or lib.get('package','—')}")
    st.markdown(
        f"`{lib.get('package','—')}`  |  **{lib.get('platform','—')}**  |  "
        f"**{lib.get('framework_language','—')}**  |  "
        f"{_STATUS_BADGE.get(lib.get('status',''), lib.get('status','—'))}  |  "
        f"{badge}"
    )

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Current Version",  lib.get("current_version","—"))
    h2.metric("Latest Version",   lib.get("latest_version","—"))
    h3.metric("Priority",         lib.get("priority","—"))
    h4.metric("Alert Priority",   lib.get("alert_priority","Normal"))
    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_overview, tab_cve, tab_release, tab_rec, tab_lifecycle, tab_teams, tab_history, tab_chat = st.tabs([
        "ℹ️ Overview", "🔐 CVE / Security", "📰 Release Notes",
        "💡 AI Recommendation", "🔄 Lifecycle", "👥 Team Ownership",
        "📅 Version History", "💬 AI Chat"
    ])

    # ─── OVERVIEW ─────────────────────────────────────────────────────────────
    with tab_overview:
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**SDK Name:** {lib.get('sdk_name') or lib.get('package','—')}")
        c1.markdown(f"**Package ID:** `{lib.get('package','—')}`")
        c1.markdown(f"**Platform:** {lib.get('platform','—')}")
        c1.markdown(f"**Language:** {lib.get('framework_language','—')}")
        c1.markdown(f"**Ecosystem:** {lib.get('ecosystem','—')}")
        c2.markdown(f"**Registry:** {format_registry(lib.get('registry'))}")
        c2.markdown(f"**Repo URL:** {lib.get('repo_url') or '—'}")
        c2.markdown(f"**Source Date:** {lib.get('source_date') or '—'}")
        c2.markdown(f"**Last Checked:** {lib.get('last_checked_date') or '—'}")
        c3.markdown(f"**Update Needed:** {badge}")
        c3.markdown(f"**Priority:** {lib.get('priority','—')}")
        c3.markdown(f"**Alert Priority:** {lib.get('alert_priority','Normal')}")
        c3.markdown(f"**Deadline:** {lib.get('deadline_date') or '—'}")
        if lib.get("deadline_notes"):
            st.info(f"📋 {lib['deadline_notes']}")
        if lib.get("deprecation_notes"):
            st.warning(f"⚠️ Deprecation: {lib['deprecation_notes']}")
        if lib.get("comments"):
            st.caption(f"💬 {lib['comments']}")
        st.caption(f"SDK ID: {lid}  |  Updated: {format_datetime(lib.get('updated_at'))}")

    # ─── CVE / SECURITY ───────────────────────────────────────────────────────
    with tab_cve:
        st.markdown("#### Security Vulnerability Scan (OSV.dev)")
        col_scan, col_force = st.columns([2, 1])
        run_scan    = col_scan.button("🔍 Scan for CVEs", type="primary", key=f"cve_scan_{lid}")
        force_fresh = col_force.checkbox("Force re-scan (bypass cache)", key=f"cve_force_{lid}")

        if run_scan:
            with st.spinner("Querying OSV.dev…"):
                try:
                    result = client.scan_cve(lid, force_refresh=force_fresh)
                    data = result.get("data", {})
                    vulns = data.get("vulnerabilities", [])
                    st.caption(f"Scanned at: {format_datetime(data.get('scanned_at'))}  |  Source: {data.get('status')}  |  Ecosystem: {data.get('ecosystem')}")
                    if data.get("vuln_count", 0) == 0:
                        st.success(f"✅ No known vulnerabilities found for `{lib.get('package')}` v{data.get('version')}")
                    else:
                        critical = sum(1 for v in vulns if v.get("severity") in ("CRITICAL","HIGH"))
                        if critical > 0:
                            st.error(f"🚨 {data['vuln_count']} vulnerabilities — {critical} CRITICAL/HIGH")
                        else:
                            st.warning(f"⚠️ {data['vuln_count']} vulnerabilities found")
                        for v in vulns:
                            sev_icon = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢"}.get(v.get("severity",""),"⚪")
                            with st.expander(f"{sev_icon} **{v.get('id','')}** — {v.get('severity','')}  ({v.get('published','')})", expanded=v.get("severity") in ("CRITICAL","HIGH")):
                                st.markdown(v.get("summary","No summary available."))
                                st.markdown(f"[View on OSV.dev]({v.get('url','')})")
                                if v.get("cvss"):
                                    st.metric("CVSS Score", v["cvss"])
                except APIError as exc:
                    st.error(f"CVE scan failed: {exc.detail}")
        else:
            st.caption("Click 'Scan for CVEs' to check this library against the OSV.dev vulnerability database. Results are cached per version.")

    # ─── RELEASE NOTES ────────────────────────────────────────────────────────
    with tab_release:
        st.markdown("#### Release Notes")
        if st.button("📰 Fetch Release Notes", type="primary", key=f"rn_{lid}"):
            with st.spinner("Fetching from GitHub…"):
                try:
                    rn = client.get_release_notes(lid)
                    data = rn.get("data",{})
                    if data.get("error"):
                        st.warning(f"Note: {data['error']}")
                    if data.get("source") == "none":
                        st.info("No GitHub repo URL configured for this library. Edit the library to add `repo_url` pointing to a GitHub repository.")
                    elif not data.get("release_notes"):
                        st.info(f"No releases found on GitHub for `{data.get('package')}`")
                    else:
                        st.caption(f"Source: {data.get('source')}  |  {data.get('notes_count')} releases found")
                        for rel in data.get("release_notes",[]):
                            pre = " (pre-release)" if rel.get("prerelease") else ""
                            with st.expander(f"**{rel.get('version','')}** — {rel.get('name','')}{pre}  ·  {rel.get('published_at','')}", expanded=False):
                                body = rel.get("body","") or "No release notes provided."
                                st.markdown(body[:500] + ("…" if len(body) > 500 else ""))
                                if rel.get("url"):
                                    st.markdown(f"[Full release on GitHub]({rel['url']})")
                except APIError as exc:
                    st.error(f"Failed: {exc.detail}")
        else:
            if lib.get("repo_url"):
                st.caption(f"Repo: {lib['repo_url']}")
            st.caption("Click to fetch the latest release notes from GitHub.")

    # ─── AI RECOMMENDATION ────────────────────────────────────────────────────
    with tab_rec:
        with st.spinner("Loading recommendation…"):
            try:
                rec_resp = client.get_recommendations()
                recs     = rec_resp.get("data") or []
                rec = next((r for r in recs if r.get("library_id") == lid), None)
            except APIError:
                rec = None
        if rec:
            decision = rec.get("upgrade_recommended","")
            summary  = rec.get("recommendation_summary","")
            if decision == "Yes":
                st.error(f"🔴 **Recommendation: Upgrade Required**\n\n{summary}")
            elif decision in ("No","Sufficient"):
                st.success(f"✅ **Recommendation: No Action Needed**\n\n{summary}")
            else:
                st.info(f"🟡 {summary}")
            pros = rec.get("upgrade_pros") or []
            cons = rec.get("upgrade_cons") or []
            if pros or cons:
                pc1, pc2 = st.columns(2)
                if pros:
                    pc1.markdown("**Upgrade Pros:**")
                    for p in pros: pc1.markdown(f"  ✅ {p}")
                if cons:
                    pc2.markdown("**Upgrade Cons:**")
                    for c in cons: pc2.markdown(f"  ⚠️ {c}")
        else:
            st.info("No AI recommendation yet for this library. Trigger a pipeline run to generate one.")

    # ─── LIFECYCLE ────────────────────────────────────────────────────────────
    with tab_lifecycle:
        with st.spinner("Loading lifecycle…"):
            try:
                lc_resp = client.get_library_lifecycle(lid)
                lc = lc_resp.get("data")
            except APIError:
                lc = None

        _STATUS_ICON = {"Pending":"⏳ Pending","Acknowledged":"👁️ Acknowledged","Scheduled":"📅 Scheduled","In Progress":"🔧 In Progress","Completed":"✅ Completed","Skipped":"⏭️ Skipped"}
        if lc:
            s = lc.get("status","—")
            st.markdown(f"**Current Status:** {_STATUS_ICON.get(s, s)}")
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**Sprint:** {lc.get('target_sprint') or '—'}")
            c1.markdown(f"**Target Version:** {lc.get('target_version') or '—'}")
            c2.markdown(f"**Target Date:** {lc.get('target_date') or '—'}")
            c2.markdown(f"**Actioned By:** {lc.get('actioned_by') or '—'}")
            c3.markdown(f"**Completed Version:** {lc.get('completed_version') or '—'}")
            c3.markdown(f"**Updated:** {format_datetime(lc.get('updated_at'))}")
            if lc.get("skip_reason"):
                st.caption(f"Skip reason: {lc['skip_reason']}")
        else:
            st.info("No lifecycle tracking entry yet.")
            if is_admin() or True:   # viewers can init lifecycle
                if st.button("➕ Add to Governance Workflow", type="primary"):
                    try:
                        client.init_lifecycle(lid, actioned_by=username)
                        st.success("Added to governance workflow.")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Failed: {exc.detail}")

    # ─── TEAMS ────────────────────────────────────────────────────────────────
    with tab_teams:
        with st.spinner("Loading team assignments…"):
            try:
                teams_resp = client.get_library_teams(lid)
                lib_teams  = teams_resp.get("data") or []
            except APIError:
                lib_teams = []
        if lib_teams:
            for t in lib_teams:
                prim = "⭐ Primary" if t.get("is_primary") else "Secondary"
                st.markdown(f"**{t.get('team_name','—')}** — {prim}")
                st.caption(f"Assigned by: {t.get('assigned_by','—')}  |  {format_datetime(t.get('assigned_at'))}")
                if t.get("team_email"):
                    st.caption(f"Contact: {t['team_email']}")
        else:
            st.info("No team assignment. Go to **👥 Teams** page to assign this library to a squad.")

    # ─── VERSION HISTORY ──────────────────────────────────────────────────────
    with tab_history:
        with st.spinner("Loading version history…"):
            try:
                vh_resp = client.get_version_history(lid)
                vh = vh_resp.get("data") or []
            except APIError:
                vh = []
        if vh:
            df = pd.DataFrame([{
                "Version":     h.get("version_number","—"),
                "Type":        h.get("record_type","—"),
                "Source":      h.get("source","—"),
                "Recorded At": format_datetime(h.get("recorded_at")),
                "Notes":       h.get("notes",""),
            } for h in vh])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No version history records for this library.")

    # ─── AI CHAT (stub — ready for LLM when configured) ───────────────────────
    with tab_chat:
        st.markdown("#### Ask the AI about this library")
        st.caption(
            f"Context pre-loaded: `{lib.get('package','—')}` v{lib.get('current_version','—')} → v{lib.get('latest_version','—')} "
            f"on {lib.get('platform','—')}. AI recommendation available: {'Yes' if rec else 'No'}."
        )

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = {}
        chat_key = f"chat_{lid}"
        if chat_key not in st.session_state.chat_history:
            st.session_state.chat_history[chat_key] = []

        history = st.session_state.chat_history[chat_key]
        for msg in history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        prompt = st.chat_input(f"Ask about {lib.get('sdk_name') or lib.get('package','this library')}…")
        if prompt:
            history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Build context-rich answer using rule-based logic (no LLM needed)
            context = (
                f"SDK: {lib.get('sdk_name') or lib.get('package')}\n"
                f"Platform: {lib.get('platform')}\n"
                f"Current: {lib.get('current_version')} → Latest: {lib.get('latest_version')}\n"
                f"Update needed: {lib.get('update_needed')}\n"
                f"Status: {lib.get('status')}\n"
            )
            rec_context = ""
            if rec:
                rec_context = f"\nAI Recommendation: {rec.get('upgrade_recommended')} — {rec.get('recommendation_summary','')[:200]}"

            try:
                result = client.test_llm(
                    package=lib.get("package",""),
                    platform=lib.get("platform","Android"),
                    current_version=lib.get("current_version",""),
                    latest_version=lib.get("latest_version",""),
                )
                llm_data = result.get("data",{})
                if llm_data.get("llm_enabled"):
                    reply = f"Based on the library context:\n\n{context}{rec_context}\n\n*LLM is enabled — for full conversational AI, the chat endpoint is ready to be wired to the configured provider.*"
                else:
                    reply = _rule_based_answer(prompt.lower(), lib, rec)
            except Exception:
                reply = _rule_based_answer(prompt.lower(), lib, rec)

            history.append({"role": "assistant", "content": reply})
            with st.chat_message("assistant"):
                st.markdown(reply)


def _rule_based_answer(question: str, lib: dict, rec: dict | None) -> str:
    """Provide helpful answers without LLM based on library data."""
    pkg  = lib.get("sdk_name") or lib.get("package","this library")
    cur  = lib.get("current_version","unknown")
    lat  = lib.get("latest_version","unknown")
    un   = (lib.get("update_needed") or "").lower()
    plat = lib.get("platform","")

    if any(w in question for w in ["upgrade","update","should i","do i need"]):
        if un == "mandatory":
            return f"**Yes, upgrade is mandatory.** {pkg} needs to be upgraded from {cur} to {lat}. {rec.get('recommendation_summary','') if rec else ''}"
        elif un == "recommended":
            return f"**Upgrade is recommended** for {pkg} ({cur} → {lat}). {rec.get('recommendation_summary','') if rec else ''}"
        else:
            return f"{pkg} is currently up to date at version {cur}. No immediate upgrade required."
    elif any(w in question for w in ["version","current","latest","new"]):
        return f"**{pkg}** current version: `{cur}`, latest available: `{lat}`. Gap: {un}."
    elif any(w in question for w in ["platform","android","ios","swift","kotlin"]):
        return f"{pkg} is used on **{plat}** platform with {lib.get('framework_language','—')} language."
    elif any(w in question for w in ["risk","security","cve","vuln"]):
        return f"Run the **CVE scan** in the '🔐 CVE / Security' tab to check {pkg} for known vulnerabilities. Alert priority: {lib.get('alert_priority','Normal')}."
    elif any(w in question for w in ["deadline","when","sprint","schedule"]):
        dl = lib.get("deadline_date")
        return f"Deadline for {pkg}: **{dl or 'not set'}**. {lib.get('deadline_notes') or ''}\nGo to the **🔄 Lifecycle** tab to schedule the upgrade."
    elif any(w in question for w in ["pros","benefit","advantage"]):
        if rec and rec.get("upgrade_pros"):
            return "**Upgrade pros:**\n" + "\n".join(f"• {p}" for p in rec["upgrade_pros"])
        return f"Run a pipeline to generate AI-powered pros/cons for upgrading {pkg}."
    elif any(w in question for w in ["cons","risk","break","impact"]):
        if rec and rec.get("upgrade_cons"):
            return "**Upgrade cons:**\n" + "\n".join(f"• {c}" for c in rec["upgrade_cons"])
        return f"Run a pipeline to generate AI-powered pros/cons for upgrading {pkg}."
    else:
        return (
            f"I have context about **{pkg}**: version {cur} → {lat} ({un}), {plat}, "
            f"status: {lib.get('status','—')}.\n\n"
            f"Configure an LLM provider in **⚙️ Settings → 🤖 LLM Configuration** "
            f"for full conversational AI about this library."
        )
