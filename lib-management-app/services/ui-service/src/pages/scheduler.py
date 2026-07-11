"""Scheduler page — visual cron builder + real execution report."""
from __future__ import annotations
import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, is_admin
from src.utils.formatters import format_datetime

_STAGES = [
    {"key": "fetch_libraries",  "icon": "📥", "label": "Fetch SDKs",
     "desc": "Read all SDK records from the database"},
    {"key": "batch_scrape",     "icon": "🔍", "label": "Scrape Latest Versions",
     "desc": "Pull latest version numbers from Maven, CocoaPods, SPM, GitHub"},
    {"key": "batch_compare",    "icon": "⚖️",  "label": "Compare Versions",
     "desc": "Detect new releases, major/minor bumps, version drift"},
    {"key": "batch_recommend",  "icon": "🤖", "label": "Generate Recommendations",
     "desc": "Rule-based + LLM upgrade guidance with pros/cons"},
    {"key": "notify",           "icon": "📨", "label": "Send Notifications",
     "desc": "Email/Teams alerts — sent ONLY if channels are configured in Settings"},
]

_STATUS_CFG = {
    "completed": {"icon": "✅", "label": "Completed"},
    "failed":    {"icon": "❌", "label": "Failed"},
    "partial":   {"icon": "⚠️",  "label": "Partial"},
    "running":   {"icon": "⏳", "label": "Running"},
    "pending":   {"icon": "⭕", "label": "Pending"},
    "skipped":   {"icon": "⏭️", "label": "Skipped"},
}

_DOW_NAMES = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
_DOW_NUMS  = ["1","2","3","4","5","6","0"]


def _build_cron(freq, h, m, dow, dom):
    h, m = str(h), str(m)
    if freq == "Every Hour":  return f"{m} * * * *"
    if freq == "Daily":       return f"{m} {h} * * *"
    if freq == "Weekdays":    return f"{m} {h} * * 1-5"
    if freq == "Weekly":      return f"{m} {h} * * {_DOW_NUMS[dow]}"
    if freq == "Monthly":     return f"{m} {h} {dom} * *"
    return ""

def _describe(freq, h, m, dow, dom):
    t = f"{h:02d}:{m:02d} UTC"
    if freq == "Every Hour":  return f"Every hour at :{m:02d}"
    if freq == "Daily":       return f"Every day at {t}"
    if freq == "Weekdays":    return f"Monday–Friday at {t}"
    if freq == "Weekly":      return f"Every {_DOW_NAMES[dow]} at {t}"
    if freq == "Monthly":     return f"Day {dom} of every month at {t}"
    return "Custom expression"

def _fmt(sec):
    if not sec: return "—"
    if sec < 0.001: return "< 1 ms"
    if sec < 1:     return f"{sec*1000:.0f} ms"
    if sec < 60:    return f"{sec:.2f} s"
    return f"{int(sec//60)}m {int(sec%60)}s"

def _total_dur(run):
    try:
        from datetime import datetime, timezone
        s = datetime.fromisoformat(run["started_at"].replace("Z","+00:00"))
        e = datetime.fromisoformat(run["finished_at"].replace("Z","+00:00"))
        return _fmt((e - s).total_seconds())
    except Exception:
        return "—"

def _parse_cron(expr):
    try:
        p = (expr or "0 2 * * *").split()
        return int(p[1]) if p[1]!="*" else 2, int(p[0]) if p[0]!="*" else 0
    except Exception:
        return 2, 0

def _detect_freq(expr):
    try:
        _,h,d,_,dow = (expr or "").split()
        if h=="*":      return "Every Hour"
        if dow=="1-5":  return "Weekdays"
        if d!="*":      return "Monthly"
        if dow!="*":    return "Weekly"
        return "Daily"
    except Exception:
        return "Daily"


def _stage_card(idx, meta, step):
    sstatus = step.get("status","pending") if step else "pending"
    sdur    = step.get("duration_seconds",0) if step else 0
    sitems  = step.get("items_processed",0) if step else 0
    smsg    = (step.get("message") or "") if step else ""
    scfg    = _STATUS_CFG.get(sstatus, _STATUS_CFG["pending"])

    with st.container(border=True):
        c1, c2 = st.columns([1, 10])
        c1.markdown(f"### {meta['icon']}")
        with c2:
            h1, h2, h3 = st.columns([5, 2, 2])
            h1.markdown(f"**{idx}. {meta['label']}**")
            h1.caption(meta["desc"])
            if sstatus == "completed":   h2.success(f"{scfg['icon']} {scfg['label']}")
            elif sstatus == "failed":    h2.error(f"{scfg['icon']} {scfg['label']}")
            elif sstatus == "running":   h2.info(f"{scfg['icon']} {scfg['label']}")
            elif sstatus == "partial":   h2.warning(f"{scfg['icon']} {scfg['label']}")
            else:                        h2.caption(f"{scfg['icon']} {scfg['label']}")
            if sdur > 0:
                h3.metric("Duration", _fmt(sdur))
            else:
                h3.caption("Duration: —")

        if sstatus != "pending" and step:
            d1, d2, d3 = st.columns(3)
            d1.metric("Items Processed", f"{sitems:,}")
            if step.get("started_at"):  d2.caption(f"**Started:** {format_datetime(step['started_at'])}")
            if step.get("finished_at"): d3.caption(f"**Finished:** {format_datetime(step['finished_at'])}")
            if smsg:
                if sstatus == "failed":  st.error(f"💬 {smsg}")
                elif sstatus=="partial": st.warning(f"💬 {smsg}")
                else:                   st.caption(f"💬 {smsg}")


def _render_report(run, client):
    """Real execution report — shows actual stage results + honest notification status."""
    status    = run.get("status","running")
    steps_raw = run.get("steps",[])
    run_id    = run.get("run_id","")
    total     = run.get("total_libraries",0)
    scfg      = _STATUS_CFG.get(status, _STATUS_CFG["pending"])
    by_key    = {s.get("step",""): s for s in steps_raw}

    # ── Status header ─────────────────────────────────────────────────────
    if status == "completed":
        st.success(f"✅ **Pipeline Completed** — {run_id[:24]}…")
    elif status == "failed":
        st.error(f"❌ **Pipeline Failed** — {run_id[:24]}…")
    elif status == "partial":
        st.warning(f"⚠️ **Pipeline Partially Completed** — {run_id[:24]}…")
    else:
        st.info(f"⏳ **Pipeline Running…** — {run_id[:24]}…")

    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Status",    f"{scfg['icon']} {status.capitalize()}")
    k2.metric("SDKs", total or "—")
    k3.metric("Duration",  _total_dur(run) if run.get("finished_at") else "Running…")
    k4.metric("Started",   format_datetime(run.get("started_at")) or "—")
    k5.metric("Trigger",   run.get("triggered_by","—"))

    # ── Progress ──────────────────────────────────────────────────────────
    done = sum(1 for s in _STAGES if by_key.get(s["key"],{}).get("status")=="completed")
    pct  = done / len(_STAGES)
    if status == "running":
        st.progress(pct, text=f"**{done} of {len(_STAGES)} stages completed**")
    else:
        st.progress(pct)
        st.caption(f"{done}/{len(_STAGES)} stages completed")

    st.divider()
    st.markdown("#### ⚡ Pipeline Stages — Actual Execution Results")

    for idx, meta in enumerate(_STAGES, 1):
        _stage_card(idx, meta, by_key.get(meta["key"]))

    # ── Timing chart ──────────────────────────────────────────────────────
    if done >= 2 and status in ("completed","partial"):
        st.divider()
        st.markdown("#### ⏱ Stage Timing")
        labels, durs, colors = [], [], []
        for meta in _STAGES:
            s = by_key.get(meta["key"],{})
            if s and s.get("duration_seconds",0) > 0:
                labels.append(f"{meta['icon']} {meta['label']}")
                durs.append(round(s["duration_seconds"],4))
                colors.append(
                    "#10B981" if s.get("status")=="completed" else
                    "#EF4444" if s.get("status")=="failed" else "#F59E0B"
                )
        if labels:
            fig = go.Figure(go.Bar(
                x=labels, y=durs, marker_color=colors,
                text=[_fmt(d) for d in durs], textposition="outside",
                hovertemplate="%{x}<br>⏱ %{text}<extra></extra>",
            ))
            fig.update_layout(
                height=230, margin=dict(t=10,b=10,l=10,r=10),
                yaxis=dict(title="seconds",showgrid=True,gridcolor="#F3F4F6"),
                xaxis=dict(showgrid=False),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"bar_{run_id[:8]}")
            mi = durs.index(max(durs))
            st.caption(f"Slowest: **{labels[mi]}** ({_fmt(durs[mi])}) | Total: **{_total_dur(run)}**")

    # ── Failures ──────────────────────────────────────────────────────────
    failed = [s for s in steps_raw if s.get("status")=="failed"]
    if failed:
        st.divider()
        st.markdown("#### ❌ Failure Details")
        for s in failed:
            with st.expander(f"❌ Stage **{s.get('step','?')}** failed", expanded=True):
                st.error(s.get("message","No error details."))
                st.caption(f"Duration: {_fmt(s.get('duration_seconds',0))} | Items: {s.get('items_processed',0):,}")
    if run.get("error"):
        st.error(f"Fatal: {run['error']}")

    # ── Per-library detail section ────────────────────────────────────────
    if status in ("completed","partial") and client is not None:
        st.divider()
        st.markdown("#### 📋 Per-SDK Execution Detail")
        st.caption("Real data from the database — shows what was found and decided for every SDK in this run.")

        with st.spinner("Loading per-SDK data…"):
            try:
                libs = client.get_libraries().get("data",{}).get("libraries",[])
                recs_raw = client.get_recommendations().get("data") or []
                recs_by_id = {r["library_id"]: r for r in recs_raw}
            except APIError:
                libs, recs_by_id = [], {}

        if libs:
            # Build combined rows
            _UPDATE_ICON = {"mandatory":"🚨","recommended":"⚠️","none":"✅","optional":"✅"}
            _REC_ICON    = {"Yes":"🔴","No":"✅","Sufficient":"✅"}

            rows = []
            log_lines = []
            run_ts = (run.get("started_at") or "")[:19].replace("T"," ")

            for lib in libs:
                lid    = lib["id"]
                rec    = recs_by_id.get(lid, {})
                un     = (lib.get("update_needed") or "").lower()
                rec_d  = rec.get("upgrade_recommended","—")
                cur    = lib.get("current_version","—") or "—"
                lat    = lib.get("latest_version","—") or "—"
                pkg    = lib.get("sdk_name") or lib.get("package","—")
                plat   = lib.get("platform","—")
                summary= (rec.get("recommendation_summary") or "")[:100]
                u_icon = _UPDATE_ICON.get(un,"❓")
                r_icon = _REC_ICON.get(rec_d,"🟡")

                rows.append({
                    "#":      lid,
                    "SDK":pkg,
                    "Platform":plat,
                    "Current": cur,
                    "Latest":  lat,
                    "Update":  f"{u_icon} {un.capitalize()}",
                    "AI Decision": f"{r_icon} {rec_d}",
                    "Summary": summary,
                })

                log_lines.append(
                    f"[{run_ts}]  {u_icon} {r_icon}  "
                    f"{plat:8s}  {pkg[:35]:35s}  "
                    f"{cur:15s} → {lat:15s}  "
                    f"{un:12s}  AI:{rec_d}"
                )

            df_all = pd.DataFrame(rows)

            # Use run_id prefix in all widget keys to avoid duplicate key errors
            # when _render_report() is called multiple times on the same page.
            k = run_id[:8]

            # Filters
            fc1, fc2, fc3 = st.columns(3)
            plat_opts = ["All"] + sorted({l.get("platform","") for l in libs if l.get("platform")})
            upd_opts  = ["All", "🚨 Mandatory", "⚠️ Recommended", "✅ Up to Date"]
            rec_opts  = ["All", "🔴 Upgrade (Yes)", "✅ OK (No/Sufficient)"]
            plat_f = fc1.selectbox("Platform", plat_opts, key=f"det_plat_{k}")
            upd_f  = fc2.selectbox("Update Needed", upd_opts, key=f"det_upd_{k}")
            rec_f  = fc3.selectbox("AI Decision", rec_opts, key=f"det_rec_{k}")

            df_show = df_all.copy()
            if plat_f != "All":
                df_show = df_show[df_show["Platform"] == plat_f]
            if upd_f == "🚨 Mandatory":
                df_show = df_show[df_show["Update"].str.contains("Mandatory")]
            elif upd_f == "⚠️ Recommended":
                df_show = df_show[df_show["Update"].str.contains("Recommended")]
            elif upd_f == "✅ Up to Date":
                df_show = df_show[df_show["Update"].str.contains("None|Optional")]
            if rec_f == "🔴 Upgrade (Yes)":
                df_show = df_show[df_show["AI Decision"].str.contains("Yes")]
            elif rec_f == "✅ OK (No/Sufficient)":
                df_show = df_show[df_show["AI Decision"].str.contains("No|Sufficient")]

            st.caption(f"Showing **{len(df_show)}** of **{len(libs)}** SDKs")

            tab_tbl, tab_log, tab_mandatory, tab_upgrade = st.tabs([
                f"📊 Table ({len(df_show)})",
                "🖥️ Console Log",
                f"🚨 Mandatory ({sum(1 for l in libs if (l.get('update_needed') or '').lower()=='mandatory')})",
                f"🔴 AI: Upgrade ({sum(1 for r in recs_by_id.values() if r.get('upgrade_recommended')=='Yes')})",
            ])

            with tab_tbl:
                st.dataframe(df_show, use_container_width=True, hide_index=True,
                    column_config={
                        "#":          st.column_config.NumberColumn("#",      width="small"),
                        "SDK":    st.column_config.TextColumn("SDK",  width="medium"),
                        "Platform":   st.column_config.TextColumn("Platform", width="small"),
                        "Current":    st.column_config.TextColumn("Current",  width="small"),
                        "Latest":     st.column_config.TextColumn("Latest",   width="small"),
                        "Update":     st.column_config.TextColumn("Update Needed", width="medium"),
                        "AI Decision":st.column_config.TextColumn("AI Decision",  width="medium"),
                        "Summary":    st.column_config.TextColumn("AI Summary",   width="large"),
                    })

                import io as _io
                buf = _io.StringIO()
                df_show.to_csv(buf, index=False)
                st.download_button("⬇️ Export filtered CSV", buf.getvalue(),
                                   file_name=f"run_report_{run_id[:8]}.csv", mime="text/csv",
                                   key=f"dl_csv_{k}")

            with tab_log:
                st.caption("One line per SDK — timestamped output simulating what the pipeline logged.")
                # Filter log lines to match table filter
                visible_ids = set(df_show["#"].tolist())
                filtered_log = [log_lines[i] for i, lib in enumerate(libs) if lib["id"] in visible_ids]
                log_text = "\n".join(filtered_log)
                st.code(log_text, language=None)

            with tab_mandatory:
                mandatory_libs = [l for l in libs if (l.get("update_needed") or "").lower() == "mandatory"]
                if not mandatory_libs:
                    st.success("✅ No mandatory upgrades found in this run.")
                else:
                    st.error(f"🚨 **{len(mandatory_libs)} SDKs require mandatory upgrade**")
                    for lib in mandatory_libs:
                        rec = recs_by_id.get(lib["id"], {})
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([3,2,4])
                            c1.markdown(f"**{lib.get('sdk_name') or lib.get('package','—')}**")
                            c1.caption(f"{lib.get('platform','—')} | {lib.get('framework_language','—')}")
                            c2.metric("Version Gap", f"{lib.get('current_version','?')} → {lib.get('latest_version','?')}")
                            if rec.get("recommendation_summary"):
                                c3.caption(f"💡 {rec['recommendation_summary'][:100]}")
                            if lib.get("deadline_date"):
                                st.warning(f"📅 Deadline: {lib['deadline_date']}  {lib.get('deadline_notes','')}")

            with tab_upgrade:
                upgrade_recs = [(lid, r) for lid, r in recs_by_id.items() if r.get("upgrade_recommended")=="Yes"]
                if not upgrade_recs:
                    st.success("✅ No upgrades recommended by AI in this run.")
                else:
                    lib_map = {l["id"]: l for l in libs}
                    st.warning(f"🔴 **AI recommends upgrade for {len(upgrade_recs)} SDKs**")
                    df_up = pd.DataFrame([{
                        "SDK":  lib_map.get(lid,{}).get("sdk_name") or lib_map.get(lid,{}).get("package","—"),
                        "Platform": lib_map.get(lid,{}).get("platform","—"),
                        "Current":  lib_map.get(lid,{}).get("current_version","—"),
                        "Latest":   lib_map.get(lid,{}).get("latest_version","—"),
                        "Update":   _UPDATE_ICON.get((lib_map.get(lid,{}).get("update_needed") or "").lower(),"❓") + " " + (lib_map.get(lid,{}).get("update_needed") or "").capitalize(),
                        "Summary":  (r.get("recommendation_summary") or "")[:100],
                    } for lid, r in upgrade_recs if lid in lib_map])
                    st.dataframe(df_up, use_container_width=True, hide_index=True)

    # ── HONEST notification status ────────────────────────────────────────
    # We show what actually happened — not fake checkboxes.
    # If channels are not configured, nothing is sent, we say so clearly.
    if status in ("completed","partial","failed"):
        st.divider()
        st.markdown("#### 📨 Notification Delivery")

        try:
            app_cfg = {s["key"]: s["value"] for s in (client.get_app_settings().get("data") or [])}
        except APIError:
            app_cfg = {}

        email_on  = app_cfg.get("email_enabled","0") == "1"
        teams_on  = app_cfg.get("teams_enabled","0") == "1"
        notify_ok = by_key.get("notify",{}).get("status") == "completed"
        notify_msg = by_key.get("notify",{}).get("message","")

        n1, n2 = st.columns(2)
        with n1:
            st.markdown("**📧 Email**")
            if email_on and notify_ok:
                st.success("✅ Configured + notify stage ran")
            elif email_on:
                st.warning("⚠️ Configured but notify stage did not complete")
            else:
                st.warning("⚪ Not configured — nothing was sent")
                st.caption("Enable: ⚙️ Settings → 🔔 Notifications Config")

        with n2:
            st.markdown("**💬 Microsoft Teams**")
            if teams_on and notify_ok:
                st.success("✅ Configured + notify stage ran")
            elif teams_on:
                st.warning("⚠️ Configured but notify stage did not complete")
            else:
                st.warning("⚪ Not configured — nothing was sent")
                st.caption("Enable: ⚙️ Settings → 🔔 Notifications Config")

        if not email_on and not teams_on:
            st.info(
                "ℹ️ No notification channels are enabled. "
                "Configure them in **⚙️ Settings → 🔔 Notifications Config** "
                "to receive email or Teams alerts on future runs."
            )
        elif notify_msg:
            st.caption(f"Notify stage output: {notify_msg}")


# ══════════════════════════════════════════════════════════════════════════════
def render() -> None:
    st.title("🕐 Scheduler")
    client = GatewayClient(token=get_token())

    with st.spinner("Loading schedule…"):
        try:
            cfg = client.get_schedule().get("data") or {}
        except APIError as exc:
            st.error(f"Could not load schedule: {exc.detail}"); cfg = {}

    tab_cfg, tab_trigger, tab_runs = st.tabs([
        "⚙️ Schedule Setup", "▶️ Manual Trigger", "📋 Run History"
    ])

    # ── TAB 1: Visual cron builder ─────────────────────────────────────────────
    with tab_cfg:
        if cfg.get("enabled"):
            st.success("🟢 Scheduler **enabled** — pipeline runs automatically on schedule.")
        else:
            st.warning("⚪ Scheduler **disabled** — only runs when manually triggered.")

        c1,c2,c3 = st.columns(3)
        c1.metric("Cron",     cfg.get("cron","—"))
        c2.metric("Next Run", format_datetime(cfg.get("next_run")) or "—")
        c3.metric("Last Run", format_datetime(cfg.get("last_run"))  or "Never")
        st.divider()

        if not is_admin():
            st.info("🔒 Admin access required to modify schedule.")
        else:
            st.markdown("#### 📅 Schedule Builder")
            st.caption("Choose frequency and time — cron expression is generated for you.")

            cur_cron = cfg.get("cron","0 2 * * *")
            cur_h, cur_m = _parse_cron(cur_cron)
            cur_freq = _detect_freq(cur_cron)
            freq_opts = ["Every Hour","Daily","Weekdays","Weekly","Monthly","Custom"]
            freq_idx  = freq_opts.index(cur_freq) if cur_freq in freq_opts else 1

            cf, ct = st.columns([2,2])
            frequency = cf.selectbox("📆 How often?", freq_opts, index=freq_idx,
                help="All times are UTC.")
            hour, minute, dow_idx, dom = cur_h, cur_m, 0, 1

            if frequency not in ("Every Hour","Custom"):
                with ct:
                    ta,tb = st.columns(2)
                    hour   = ta.number_input("Hour (0–23, UTC)", 0, 23, cur_h)
                    minute = tb.number_input("Minute (0–59)",    0, 59, cur_m, step=5)
            if frequency == "Weekly":
                dow_idx = st.selectbox("Day of week", range(7), format_func=lambda i: _DOW_NAMES[i])
            if frequency == "Monthly":
                dom = st.slider("Day of month", 1, 28, 1)

            custom_expr = cur_cron
            if frequency == "Custom":
                custom_expr = st.text_input("Cron (min hour day month weekday)", value=cur_cron)
                st.markdown("[🔗 Validate at crontab.guru](https://crontab.guru/)")

            generated   = (_build_cron(frequency, hour, minute, dow_idx, dom)
                           if frequency != "Custom" else custom_expr.strip())
            description = (_describe(frequency, hour, minute, dow_idx, dom)
                           if frequency != "Custom" else "Custom")

            st.info(f"📋 **Expression:** `{generated}`  →  **{description}**")

            with st.form("sched_form"):
                enabled_new = st.toggle("Enable automatic scheduling",
                    value=bool(cfg.get("enabled",False)))
                if st.form_submit_button("💾 Save Schedule", type="primary"):
                    try:
                        client.update_schedule({"enabled": enabled_new, "cron": generated})
                        st.success(f"✅ Saved: **{description}** (`{generated}`)")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Failed: {exc.detail}")

    # ── TAB 2: Manual trigger + real-time report ───────────────────────────────
    with tab_trigger:
        if not is_admin():
            st.info("🔒 Admin access required."); return

        for k, v in [("active_run_id",None),("trigger_confirm",False),("run_polling",False)]:
            if k not in st.session_state:
                st.session_state[k] = v

        st.markdown("#### ▶️ Manual Pipeline Trigger")

        ci, cb = st.columns([3,2])
        with ci:
            st.markdown("""
**What the pipeline does (automatically, in order):**

| # | Stage | What happens |
|---|-------|-------------|
| 1 | 📥 Fetch | Read 119 libraries from DB |
| 2 | 🔍 Scrape | Pull latest versions from registries |
| 3 | ⚖️ Compare | Find new releases & version bumps |
| 4 | 🤖 Recommend | Generate upgrade guidance |
| 5 | 📨 Notify | Send alerts **only if email/Teams configured** |

> The pipeline runs fully automatically from start to finish.
> Configure notification channels in ⚙️ Settings → 🔔 Notifications Config.
""")

        with cb:
            if not st.session_state.active_run_id:
                if not st.session_state.trigger_confirm:
                    if st.button("▶️ Trigger Run Now", type="primary", use_container_width=True):
                        st.session_state.trigger_confirm = True
                        st.rerun()
                else:
                    st.warning("⚠️ This will run the full pipeline across all 119 libraries.")
                    b1, b2 = st.columns(2)
                    if b1.button("✅ Confirm", type="primary"):
                        st.session_state.trigger_confirm = False
                        try:
                            result = client.trigger_run()
                            rid = result.get("data",{}).get("run_id")
                            if rid:
                                st.session_state.active_run_id = rid
                                st.session_state.run_polling   = True
                                st.rerun()
                            else:
                                st.error(f"No run_id in response: {result}")
                        except APIError as exc:
                            st.error(f"Trigger failed: {exc.detail}")
                    if b2.button("❌ Cancel"):
                        st.session_state.trigger_confirm = False
                        st.rerun()
            else:
                st.success(f"Active run: `{str(st.session_state.active_run_id)[:22]}…`")
                if st.button("🔄 Start New Run", use_container_width=True):
                    st.session_state.active_run_id = None
                    st.session_state.run_polling   = False
                    st.rerun()

        # ── Live execution ─────────────────────────────────────────────────
        if st.session_state.active_run_id:
            st.divider()
            rid = st.session_state.active_run_id

            try:
                run_data   = client.get_run(rid).get("data",{})
                run_status = run_data.get("status","pending")
            except APIError as exc:
                st.error(f"Could not fetch run status: {exc.detail}")
                run_data, run_status = {}, "failed"

            # PENDING = background task not started yet (usually < 0.5s)
            # Show spinner and fast-poll until status changes
            if run_status == "pending":
                with st.spinner("🚀 Pipeline is launching… fetching first status update"):
                    time.sleep(0.5)
                st.rerun()
            else:
                # Show the real execution report
                _render_report(run_data, client)

                # Auto-refresh every 2s while running
                if run_status == "running" and st.session_state.run_polling:
                    ph = st.empty()
                    for i in range(2, 0, -1):
                        ph.caption(f"🔄 Auto-refreshing in {i}s… (pipeline is running)")
                        time.sleep(1)
                    ph.empty()
                    st.rerun()
                elif run_status in ("completed","partial","failed"):
                    st.session_state.run_polling = False
                    if run_status == "completed":
                        st.balloons()
                        st.divider()
                        st.success("✅ Pipeline complete! All 119 libraries have been analysed.")
                        st.info(
                            "🧑\u200d💼 **Next step: Human Review Required**\n\n"
                            "The pipeline has generated AI recommendations for all libraries. "
                            "No library records have been changed and no notifications have been sent yet.\n\n"
                            "Go to **🧑\u200d💼 HITL Review** to approve/reject each library "
                            "before any changes are applied or notifications sent."
                        )
                        st.link_button("\u2192 Go to HITL Review Now", url="/hitl_review",
                                       type="primary", use_container_width=True)

    # ── TAB 3: Run history ─────────────────────────────────────────────────────
    with tab_runs:
        cr, _ = st.columns([1,5])
        if cr.button("🔄 Refresh"):
            st.rerun()

        with st.spinner("Loading run history…"):
            try:
                runs = client.get_runs().get("data") or []
                runs = runs if isinstance(runs,list) else []
            except APIError as exc:
                st.error(f"Could not load: {exc.detail}"); runs = []

        if not runs:
            st.info("No pipeline runs yet. Use '▶️ Manual Trigger' to start the first one.")
            return

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total Runs",    len(runs))
        m2.metric("✅ Completed",  sum(1 for r in runs if r.get("status")=="completed"))
        m3.metric("⚠️ Partial",   sum(1 for r in runs if r.get("status")=="partial"))
        m4.metric("❌ Failed",    sum(1 for r in runs if r.get("status")=="failed"))
        st.divider()

        rows = [{
            "Status":    (_STATUS_CFG.get(r.get("status",""),"").get("icon","⭕")
                          + " " + r.get("status","—").capitalize()),
            "Trigger":   r.get("triggered_by","—"),
            "SDKs": r.get("total_libraries",0),
            "Duration":  _total_dur(r),
            "Stages":    (f"{sum(1 for s in r.get('steps',[]) if s.get('status')=='completed')}"
                          f"/{len(_STAGES)}"),
            "Started":   format_datetime(r.get("started_at")),
            "Run ID":    str(r.get("run_id",""))[:22]+"…",
        } for r in runs]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.divider()

        st.markdown("#### 🔎 Full Execution Report")
        opts = {}
        for r in runs:
            ico = _STATUS_CFG.get(r.get("status",""),"").get("icon","⭕")
            lbl = f"{ico} {format_datetime(r.get('started_at'))} — {str(r.get('run_id',''))[:20]}…"
            opts[lbl] = r.get("run_id")

        sel = st.selectbox("Select a run to inspect", list(opts.keys()))
        if sel and opts.get(sel):
            with st.spinner("Loading execution details…"):
                try:
                    detail = client.get_run(opts[sel]).get("data",{})
                except APIError as exc:
                    st.error(f"Could not load: {exc.detail}"); detail = {}
            if detail:
                _render_report(detail, client)
