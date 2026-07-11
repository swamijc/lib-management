"""
HITL Review page — Human-in-the-Loop approval workflow.

After each pipeline run all 119 SDKs land here as 'awaiting_review'.
Reviewers approve/reject EVERY SDK before any record changes or notifications.

Sections:
    1. SDKs where AI recommends UPGRADE  → Approve Upgrade | Reject/Defer
    2. SDKs where AI says NO ACTION NEEDED → Confirm OK | Flag for Review
  3. After approvals → Send Notification button (approved upgrades only)
"""
from __future__ import annotations
import json
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, get_user, is_admin
from src.utils.formatters import format_datetime

_UPDATE_BADGE = {
    "mandatory":"🚨 Mandatory","recommended":"⚠️ Recommended",
    "none":"✅ None","optional":"✅ Optional",
}
_REC_COLOR = {"Yes":"error","No":"success","Sufficient":"success"}


def _badge(update_needed: str) -> str:
    return _UPDATE_BADGE.get((update_needed or "").lower(), update_needed or "—")


def render() -> None:
    st.title("🧑‍💼 HITL Review — Human Approval Required")
    st.caption(
        "Every library must be reviewed by a human before any record is updated or "
        "any notification is sent. This ensures accountability and accuracy."
    )

    client   = GatewayClient(token=get_token())
    username = (get_user() or {}).get("username","admin")

    # ── Load pending review items ──────────────────────────────────────────────
    with st.spinner("Loading libraries awaiting review…"):
        try:
            resp    = client.get_pending_review()
            pending = resp.get("data") or []
        except APIError as exc:
            st.error(f"Could not load pending review: {exc.detail}")
            return

    if not pending:
        st.success("✅ No libraries awaiting review. Trigger a pipeline run to generate recommendations.")
        st.info(
            "Once a pipeline run completes, all 119 libraries will appear here "
            "for human review before any changes are applied."
        )
        col, _ = st.columns([2,3])
        if col.button("▶️ Trigger Pipeline Run Now", type="primary"):
            try:
                result = client.trigger_run()
                st.success(f"Pipeline triggered. Return here once complete to review.")
            except APIError as exc:
                st.error(f"Trigger failed: {exc.detail}")
        return

    # ── Session state for approvals ────────────────────────────────────────────
    if "hitl_decisions" not in st.session_state:
        st.session_state.hitl_decisions = {}   # lifecycle_id → "approved_upgrade"|"rejected"|"confirmed_ok"|"flagged"

    decisions = st.session_state.hitl_decisions

    # ── Summary strip ──────────────────────────────────────────────────────────
    total          = len(pending)
    need_upgrade   = [p for p in pending if p.get("ai_recommendation") == "Yes"]
    no_action      = [p for p in pending if p.get("ai_recommendation") in ("No","Sufficient")]
    unreviewed_cnt = sum(1 for p in pending if p["lifecycle_id"] not in decisions)
    approved_cnt   = sum(1 for v in decisions.values() if v == "approved_upgrade")
    confirmed_cnt  = sum(1 for v in decisions.values() if v == "confirmed_ok")
    rejected_cnt   = sum(1 for v in decisions.values() if v in ("rejected","flagged"))

    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("Total SDKs",     total)
    m2.metric("🔴 Need Upgrade",    len(need_upgrade))
    m3.metric("✅ No Action",        len(no_action))
    m4.metric("⏳ Awaiting Review",  unreviewed_cnt,   delta_color="inverse")
    m5.metric("✅ Approved Upgrades",approved_cnt)
    m6.metric("❌ Rejected/Deferred",rejected_cnt)

    # Progress bar
    reviewed = total - unreviewed_cnt
    st.progress(reviewed / total, text=f"**{reviewed}/{total} reviewed** ({total-unreviewed_cnt} decisions made)")
    st.divider()

    # ── Bulk actions ───────────────────────────────────────────────────────────
    with st.expander("⚡ Bulk Actions", expanded=False):
        st.caption("Apply decision to multiple libraries at once.")
        bc1, bc2, bc3, bc4 = st.columns(4)
        if bc1.button("✅ Approve ALL Upgrade recommendations", use_container_width=True):
            for p in need_upgrade:
                decisions[p["lifecycle_id"]] = "approved_upgrade"
            st.session_state.hitl_decisions = decisions
            st.rerun()
        if bc2.button("✅ Confirm ALL No-Action libraries", use_container_width=True):
            for p in no_action:
                decisions[p["lifecycle_id"]] = "confirmed_ok"
            st.session_state.hitl_decisions = decisions
            st.rerun()
        if bc3.button("❌ Reject ALL Upgrade recommendations", use_container_width=True):
            for p in need_upgrade:
                decisions[p["lifecycle_id"]] = "rejected"
            st.session_state.hitl_decisions = decisions
            st.rerun()
        if bc4.button("🔄 Reset All Decisions", type="secondary", use_container_width=True):
            st.session_state.hitl_decisions = {}
            st.rerun()

    st.divider()

    # ══════════════════════════════════════════════════════════════════════
    # Section 1: SDKs AI recommends to UPGRADE
    # ══════════════════════════════════════════════════════════════════════
    st.markdown(f"## 🔴 AI Recommends Upgrade ({len(need_upgrade)} libraries)")
    st.caption("Review each library. Approving will update `current_version` to `latest_version` in the database.")

    if not need_upgrade:
        st.info("No libraries flagged for upgrade in this review batch.")
    else:
        for p in need_upgrade:
            lcid    = p["lifecycle_id"]
            pkg     = p.get("sdk_name") or p.get("package","—")
            plat    = p.get("platform","—")
            un      = (p.get("update_needed") or "").lower()
            cur     = p.get("current_version","—") or "—"
            lat     = p.get("latest_version","—") or "—"
            summary = p.get("ai_summary","") or ""
            pros    = p.get("upgrade_pros") or []
            cons    = p.get("upgrade_cons") or []
            decision= decisions.get(lcid)

            # Header color based on decision
            if decision == "approved_upgrade":
                header = f"✅ APPROVED  |  {_badge(un)}  **{pkg}**  `{cur}` → `{lat}`  — {plat}"
            elif decision == "rejected":
                header = f"❌ REJECTED  |  {_badge(un)}  **{pkg}**  `{cur}` → `{lat}`  — {plat}"
            else:
                header = f"⏳ PENDING   |  {_badge(un)}  **{pkg}**  `{cur}` → `{lat}`  — {plat}"

            with st.expander(header, expanded=(decision is None)):
                c1, c2 = st.columns([3,2])
                with c1:
                    st.markdown(f"**AI Summary:** {summary[:200] if summary else '—'}")
                    if pros:
                        st.markdown("**Upgrade Pros:**")
                        for pro in pros[:3]: st.markdown(f"  ✅ {pro}")
                    if cons:
                        st.markdown("**Upgrade Cons:**")
                        for con in cons[:3]: st.markdown(f"  ⚠️ {con}")
                    if p.get("deadline_date"):
                        st.warning(f"📅 Deadline: {p['deadline_date']}")
                    if p.get("deprecation_notes"):
                        st.error(f"⛔ {p['deprecation_notes']}")

                with c2:
                    st.metric("Priority",      p.get("priority","—"))
                    st.metric("Alert Priority", p.get("alert_priority","Normal"))
                    st.metric("Language",       p.get("framework_language","—") or "—")

                    st.markdown("**Decision:**")
                    col_a, col_b = st.columns(2)
                    if col_a.button("✅ Approve Upgrade", key=f"app_{lcid}", type="primary",
                                    use_container_width=True):
                        decisions[lcid] = "approved_upgrade"
                        st.session_state.hitl_decisions = decisions
                        st.rerun()
                    if col_b.button("❌ Reject / Defer", key=f"rej_{lcid}", type="secondary",
                                    use_container_width=True):
                        decisions[lcid] = "rejected"
                        st.session_state.hitl_decisions = decisions
                        st.rerun()

                    if decision == "approved_upgrade":
                        st.success("✅ Approved — will update library record")
                    elif decision == "rejected":
                        st.warning("❌ Rejected — library record unchanged")

    st.divider()

    # ══════════════════════════════════════════════════════════════════════
    # Section 2: SDKs AI says NO ACTION needed
    # ══════════════════════════════════════════════════════════════════════
    st.markdown(f"## ✅ No Upgrade Required ({len(no_action)} libraries)")
    st.caption(
        "These libraries are up to date or no upgrade needed. "
        "Confirm to acknowledge, or flag for manual review if you disagree."
    )

    if not no_action:
        st.info("No 'no-action' libraries in this batch.")
    else:
        # Quick table view for no-action (usually many)
        tab_quick, tab_detailed = st.tabs(["⚡ Quick Review", "📋 Detailed"])

        with tab_quick:
            rows = []
            for p in no_action:
                lcid = p["lifecycle_id"]
                d    = decisions.get(lcid,"pending")
                rows.append({
                    "SDK":   p.get("sdk_name") or p.get("package","—"),
                    "Platform":  p.get("platform","—"),
                    "Version":   p.get("current_version","—"),
                    "Latest":    p.get("latest_version","—"),
                    "AI":        p.get("ai_recommendation","—"),
                    "Decision":  "✅ Confirmed OK" if d=="confirmed_ok" else "⏳ Pending",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            col_ok, col_flag = st.columns(2)
            if col_ok.button("✅ Confirm ALL as OK", type="primary", use_container_width=True):
                for p in no_action:
                    decisions[p["lifecycle_id"]] = "confirmed_ok"
                st.session_state.hitl_decisions = decisions
                st.rerun()

        with tab_detailed:
            for p in no_action:
                lcid    = p["lifecycle_id"]
                pkg     = p.get("sdk_name") or p.get("package","—")
                cur     = p.get("current_version","—") or "—"
                lat     = p.get("latest_version","—") or "—"
                summary = p.get("ai_summary","") or ""
                decision= decisions.get(lcid)

                if decision == "confirmed_ok":
                    head = f"✅ CONFIRMED  |  **{pkg}**  `{cur}` = `{lat}`  — {p.get('platform','—')}"
                else:
                    head = f"⏳ PENDING   |  **{pkg}**  `{cur}` = `{lat}`  — {p.get('platform','—')}"

                with st.expander(head, expanded=False):
                    st.caption(summary[:150] if summary else "No AI summary available.")
                    col_a, col_b = st.columns(2)
                    if col_a.button("✅ Confirm OK", key=f"ok_{lcid}", type="primary",
                                    use_container_width=True):
                        decisions[lcid] = "confirmed_ok"
                        st.session_state.hitl_decisions = decisions
                        st.rerun()
                    if col_b.button("🚩 Flag for Review", key=f"flag_{lcid}",
                                    use_container_width=True):
                        decisions[lcid] = "flagged"
                        st.session_state.hitl_decisions = decisions
                        st.rerun()

    st.divider()

    # ══════════════════════════════════════════════════════════════════════
    # Apply decisions + Send notification
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("## 🚀 Apply Decisions & Send Notification")

    all_reviewed = unreviewed_cnt == 0
    approved_upgrades = [p for p in pending if decisions.get(p["lifecycle_id"]) == "approved_upgrade"]
    confirmed_ok_libs = [p for p in pending if decisions.get(p["lifecycle_id"]) == "confirmed_ok"]

    if not all_reviewed:
        st.warning(f"⚠️ {unreviewed_cnt} libraries still awaiting your decision. Review all before applying.")
    else:
        st.success(f"✅ All {total} libraries reviewed!")

    col_apply, col_notif = st.columns(2)

    with col_apply:
        st.markdown("#### 💾 Apply to Database")
        st.caption(
            f"Will update **{len(approved_upgrades)}** approved library records "
            f"(current_version → latest_version) and mark **{len(confirmed_ok_libs)}** as acknowledged."
        )
        apply_btn = st.button(
            f"💾 Apply {len(approved_upgrades)+len(confirmed_ok_libs)} Decisions",
            type="primary",
            use_container_width=True,
            disabled=not all_reviewed or (not approved_upgrades and not confirmed_ok_libs),
        )

    with col_notif:
        st.markdown("#### 📨 Send Notification")
        st.caption(
            f"Sends notification for **{len(approved_upgrades)}** approved upgrades only. "
            "No notification for no-action or rejected libraries."
        )
        notif_btn = st.button(
            f"📨 Send Notification ({len(approved_upgrades)} upgrades approved)",
            type="secondary",
            use_container_width=True,
            disabled=not approved_upgrades,
        )

    if apply_btn:
        applied = 0; failed = 0
        errors  = []

        # Apply approved upgrades → update library + lifecycle complete
        for p in approved_upgrades:
            lcid = p["lifecycle_id"]
            lat  = p.get("latest_version","")
            try:
                client.complete_lifecycle(
                    lcid,
                    completed_version=lat or p.get("current_version",""),
                    actioned_by=username,
                    reason="Approved via HITL Review",
                )
                applied += 1
            except APIError as exc:
                failed += 1
                errors.append(f"{p.get('package','?')}: {exc.detail}")

        # Confirm OK → acknowledge lifecycle
        for p in confirmed_ok_libs:
            lcid = p["lifecycle_id"]
            try:
                client.approve_no_action(lcid, actioned_by=username)
                applied += 1
            except APIError as exc:
                failed += 1
                errors.append(f"{p.get('package','?')}: {exc.detail}")

        # Reject/defer
        rejected_libs = [p for p in pending if decisions.get(p["lifecycle_id"]) == "rejected"]
        for p in rejected_libs:
            lcid = p["lifecycle_id"]
            try:
                client.reject_upgrade(lcid, actioned_by=username, reason="Rejected via HITL Review")
            except APIError:
                pass

        if applied > 0:
            st.success(
                f"✅ Applied **{applied} decisions** successfully. "
                f"{len(approved_upgrades)} library records updated."
            )
        if failed > 0:
            st.error(f"❌ {failed} failed:\n" + "\n".join(errors[:5]))

        if applied > 0:
            # Clear decisions after apply
            st.session_state.hitl_decisions = {}
            st.rerun()

    if notif_btn:
        # Build notification payload with only approved libs
        notify_libs = [{
            "library_id":          p["library_id"],
            "package":             p.get("package",""),
            "platform":            p.get("platform",""),
            "current_version":     p.get("current_version",""),
            "latest_version":      p.get("latest_version",""),
            "update_needed":       p.get("update_needed",""),
            "library_status":      p.get("status",""),
            "upgrade_recommended": p.get("ai_recommendation","Yes"),
            "recommendation_summary": (
                f"[HUMAN APPROVED] {p.get('ai_summary','') or ''}"
            )[:200],
            "alert_priority":      p.get("alert_priority","Normal"),
            "deadline_date":       p.get("deadline_date"),
        } for p in approved_upgrades]

        # Get notification config
        try:
            app_cfg = {s["key"]: s["value"] for s in (client.get_app_settings().get("data") or [])}
        except APIError:
            app_cfg = {}

        smtp_ov = None
        if app_cfg.get("email_enabled","0") == "1":
            u = app_cfg.get("smtp_username","")
            pw= app_cfg.get("smtp_password","")
            if u and pw:
                smtp_ov = {
                    "host": app_cfg.get("smtp_host","smtp.office365.com"),
                    "port": int(app_cfg.get("smtp_port","587") or "587"),
                    "username": u, "password": pw,
                    "from_address": app_cfg.get("smtp_from_address", u),
                    "use_tls": app_cfg.get("smtp_use_tls","1") == "1",
                }
        teams_wh = app_cfg.get("teams_webhook_url","") if app_cfg.get("teams_enabled","0")=="1" else None
        try:
            recs = json.loads(app_cfg.get("email_recipients","[]"))
        except Exception:
            recs = []

        if not smtp_ov and not teams_wh:
            st.warning(
                "⚠️ No notification channels configured. "
                "Go to ⚙️ Settings → 🔔 Notifications Config to set up email or Teams."
            )
        else:
            with st.spinner("Sending HITL notification…"):
                try:
                    result = client.send_hitl_notification(
                        approved_libs=notify_libs,
                        smtp_override=smtp_ov,
                        teams_webhook=teams_wh,
                        recipients=recs or None,
                    )
                    r_data = result.get("data",{})
                    for r in r_data.get("results",[]):
                        if r.get("status") == "sent":
                            st.success(f"✅ Notification sent via {r.get('channel','?')} — {len(approved_upgrades)} approved upgrades")
                        elif r.get("status") == "failed":
                            st.error(f"❌ Failed ({r.get('channel','?')}): {r.get('message','')}")
                        elif r.get("status") == "skipped":
                            st.info(f"ℹ️ Skipped ({r.get('channel','?')}): {r.get('message','')}")
                except APIError as exc:
                    st.error(f"Notification failed: {exc.detail}")
