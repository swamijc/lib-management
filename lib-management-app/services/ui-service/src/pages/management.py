"""Management page — full CRUD for SDKs (admin only)."""
from __future__ import annotations
import io
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, is_admin, get_user
from src.utils.formatters import format_registry, format_datetime

_REGISTRIES  = ["maven", "cocoapods", "spm", "github", "custom_http"]
_PRIORITIES  = ["High", "Medium", "Low"]
_STATUSES    = ["Active", "Inactive", "Deprecated", "Legacy", "Maintenance", "Unknown"]
_UPDATE_OPTS = ["mandatory", "recommended", "optional", "none"]
_PLATFORMS   = ["Android", "iOS", "Both"]
_ECOSYSTEMS  = ["mobile", "web", "backend", "data"]

_UPDATE_BADGE = {
    "mandatory":   "🚨 Mandatory",
    "recommended": "⚠️ Recommended",
    "none":        "✅ None",
    "optional":    "✅ Optional",
}
_STATUS_BADGE = {
    "Active":      "🟢 Active",
    "Deprecated":  "🔴 Deprecated",
    "Legacy":      "🟡 Legacy",
    "Maintenance": "🔵 Maintenance",
    "Inactive":    "⚪ Inactive",
    "Unknown":     "❓ Unknown",
}


def render() -> None:
    st.title("⚙️ SDK Management")

    if not is_admin():
        st.error("🔒 Admin access required.")
        return

    client  = GatewayClient(token=get_token())
    username = (get_user() or {}).get("username", "admin")

    with st.spinner("Loading SDKs…"):
        try:
            libraries = client.get_libraries().get("data", {}).get("libraries", [])
        except APIError as exc:
            st.error(f"Failed to load SDKs: {exc.detail}")
            return

    tab_list, tab_add = st.tabs(["📋 SDK List", "➕ Add New SDK"])

    # ══════════════════════════════════════════════════════════════════════
    # Tab 1: SDK list with inline search, edit and delete
    # ══════════════════════════════════════════════════════════════════════
    with tab_list:
        st.caption(f"**{len(libraries)}** SDKs in the system")

        # ── Search/filter bar ──────────────────────────────────────────────
        f1, f2, f3 = st.columns([3, 2, 2])
        search      = f1.text_input("🔍 Search package / SDK name", "", placeholder="e.g. retrofit, firebase…")
        plat_filter = f2.selectbox("Platform", ["All"] + _PLATFORMS)
        upd_filter  = f3.selectbox("Update Needed", ["All"] + [v.capitalize() for v in _UPDATE_OPTS])

        filtered = [
            l for l in libraries
            if (not search or search.lower() in (l.get("package","") + " " + (l.get("sdk_name") or "")).lower())
            and (plat_filter == "All" or l.get("platform") == plat_filter)
            and (upd_filter  == "All" or l.get("update_needed","").lower() == upd_filter.lower())
        ]
        st.caption(f"Showing {len(filtered)} of {len(libraries)} SDKs")

        # ── Summary table ──────────────────────────────────────────────────
        rows = [{
            "ID":            l.get("id"),
            "Package":       l.get("package", "—"),
            "SDK Name":      l.get("sdk_name") or l.get("package", "—"),
            "Platform":      l.get("platform", "—"),
            "Language":      l.get("framework_language", "—"),
            "Registry":      format_registry(l.get("registry")),
            "Current":       l.get("current_version", "—"),
            "Latest":        l.get("latest_version", "—"),
            "Update Needed": _UPDATE_BADGE.get((l.get("update_needed") or "").lower(), l.get("update_needed","—")),
            "Status":        _STATUS_BADGE.get(l.get("status",""), l.get("status","—")),
            "Priority":      l.get("priority","—"),
            "Deadline":      l.get("deadline_date") or "—",
        } for l in filtered]

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True,
            column_config={
                "ID":           st.column_config.NumberColumn("ID",      width="small"),
                "Package":      st.column_config.TextColumn("Package",   width="medium"),
                "SDK Name":     st.column_config.TextColumn("SDK Name",  width="medium"),
                "Platform":     st.column_config.TextColumn("Platform",  width="small"),
                "Current":      st.column_config.TextColumn("Current",   width="small"),
                "Latest":       st.column_config.TextColumn("Latest",    width="small"),
                "Update Needed":st.column_config.TextColumn("Update",    width="medium"),
                "Status":       st.column_config.TextColumn("Status",    width="small"),
            })

        # ── CSV export ──────────────────────────────────────────────────────
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        st.download_button("⬇️ Export to CSV", csv_buf.getvalue(),
                           file_name="libraries.csv", mime="text/csv")

        st.divider()

        # ── Edit / Delete expanders ────────────────────────────────────────
        st.markdown("#### ✏️ Edit / Delete SDK")
        st.caption("Expand an SDK to update its fields or delete it.")

        for lib in filtered:
            lib_id = lib.get("id")
            un     = (lib.get("update_needed") or "").lower()
            badge  = _UPDATE_BADGE.get(un, un or "—").split()[0]
            label  = f"{badge}  **{lib.get('sdk_name') or lib.get('package','—')}**  `{lib.get('current_version','—')}` → `{lib.get('latest_version','—')}`  — {lib.get('platform','—')}"

            with st.expander(label):
                with st.form(f"edit_{lib_id}"):
                    c1, c2 = st.columns(2)
                    new_cur = c1.text_input("Current Version *", value=lib.get("current_version",""))
                    new_lat = c2.text_input("Latest Version",    value=lib.get("latest_version",""))
                    c3, c4 = st.columns(2)
                    new_upd = c3.selectbox("Update Needed", _UPDATE_OPTS,
                        index=_UPDATE_OPTS.index(un) if un in _UPDATE_OPTS else 3)
                    new_pri = c4.selectbox("Priority", _PRIORITIES,
                        index=_PRIORITIES.index(lib.get("priority","Medium")) if lib.get("priority") in _PRIORITIES else 1)
                    c5, c6 = st.columns(2)
                    new_sta = c5.selectbox("Status", _STATUSES,
                        index=_STATUSES.index(lib.get("status","Active")) if lib.get("status") in _STATUSES else 0)
                    new_ded = c6.text_input("Deadline Date (YYYY-MM-DD)", value=lib.get("deadline_date") or "")
                    new_com = st.text_area("Comments", value=lib.get("comments") or "", height=60)
                    new_dep = st.text_area("Deprecation Notes", value=lib.get("deprecation_notes") or "", height=60)
                    new_ded_notes = st.text_input("Deadline Notes", value=lib.get("deadline_notes") or "")

                    btn_save, btn_del = st.columns(2)
                    save = btn_save.form_submit_button("💾 Save Changes", type="primary")
                    delete = btn_del.form_submit_button("🗑️ Delete SDK", type="secondary")

                if save:
                    if not new_cur.strip():
                        st.error("Current version is required.")
                    else:
                        try:
                            client.update_library(lib_id, {
                                "current_version":   new_cur.strip(),
                                "latest_version":    new_lat.strip() or None,
                                "update_needed":     new_upd,
                                "priority":          new_pri,
                                "status":            new_sta,
                                "comments":          new_com.strip() or None,
                                "deprecation_notes": new_dep.strip() or None,
                                "deadline_date":     new_ded.strip() or None,
                                "deadline_notes":    new_ded_notes.strip() or None,
                                "updated_by":        username,
                            })
                            st.success(f"✅ **{lib.get('package')}** updated.")
                            st.rerun()
                        except APIError as exc:
                            st.error(f"Update failed: {exc.detail}")

                if delete:
                    try:
                        client.delete_library(lib_id)
                        st.success(f"🗑️ **{lib.get('package')}** deleted.")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Delete failed: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    # Tab 2: Add New SDK
    # ══════════════════════════════════════════════════════════════════════
    with tab_add:
        st.markdown("#### Add New SDK")
        st.caption("All fields marked * are required.")

        with st.form("add_library_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            pkg      = c1.text_input("Package *", placeholder="com.squareup.retrofit2:retrofit")
            sdk_name = c2.text_input("SDK Name",  placeholder="Retrofit")
            c3, c4 = st.columns(2)
            platform = c3.selectbox("Platform *", _PLATFORMS)
            registry = c4.selectbox("Registry",   _REGISTRIES)
            c5, c6 = st.columns(2)
            cur_ver  = c5.text_input("Current Version *", placeholder="2.9.0")
            lat_ver  = c6.text_input("Latest Version",    placeholder="2.11.0")
            c7, c8 = st.columns(2)
            update_needed = c7.selectbox("Update Needed", _UPDATE_OPTS)
            priority      = c8.selectbox("Priority", _PRIORITIES, index=1)
            c9, c10 = st.columns(2)
            status    = c9.selectbox("Status", _STATUSES)
            ecosystem = c10.selectbox("Ecosystem", _ECOSYSTEMS)
            c11, c12 = st.columns(2)
            framework_lang = c11.text_input("Language", placeholder="Kotlin / Swift")
            repo_url       = c12.text_input("Repo URL", placeholder="https://github.com/…")
            comments = st.text_area("Comments", height=60)

            submitted = st.form_submit_button("➕ Add SDK", type="primary")

        if submitted:
            if not pkg.strip() or not cur_ver.strip():
                st.error("Package and Current Version are required.")
            else:
                try:
                    result = client.create_library({
                        "package":            pkg.strip(),
                        "sdk_name":           sdk_name.strip() or None,
                        "platform":           platform,
                        "registry":           registry,
                        "current_version":    cur_ver.strip(),
                        "latest_version":     lat_ver.strip() or None,
                        "update_needed":      update_needed,
                        "priority":           priority,
                        "status":             status,
                        "ecosystem":          ecosystem,
                        "framework_language": framework_lang.strip() or None,
                        "repo_url":           repo_url.strip() or None,
                        "comments":           comments.strip() or None,
                        "created_by":         username,
                    })
                    new_id = result.get("data", {}).get("id", "?")
                    st.success(f"✅ SDK **{pkg}** added (ID: {new_id}).")
                    st.rerun()
                except APIError as exc:
                    st.error(f"Failed to add library: {exc.detail}")
