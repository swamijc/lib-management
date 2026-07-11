"""Analytics page — LLM usage, token costs, pipeline metrics."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token
from src.utils.formatters import format_datetime


def render() -> None:
    st.title("📊 Analytics")
    st.caption("LLM token usage, cost metrics, and pipeline performance intelligence.")

    client = GatewayClient(token=get_token())

    with st.spinner("Loading analytics…"):
        try:
            usage_resp = client.get_llm_usage(limit=200)
            usage_data = usage_resp.get("data", {})
        except APIError as exc:
            st.error(f"Could not load analytics: {exc.detail}")
            return

        try:
            runs = client.get_runs().get("data") or []
            runs = runs if isinstance(runs, list) else []
        except APIError:
            runs = []

    stats           = usage_data.get("stats", {})
    models_breakdown = usage_data.get("models_breakdown", [])
    per_library     = usage_data.get("per_library_cost", [])
    recent_entries  = usage_data.get("recent_entries", [])

    # ── Top KPIs ───────────────────────────────────────────────────────────────
    st.markdown("### 🤖 LLM Usage & Cost")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total LLM Calls",      stats.get("total_calls", 0))
    k2.metric("Total Tokens",          f"{stats.get('total_tokens', 0):,}")
    k3.metric("Total Cost (USD)",      f"${stats.get('total_cost_usd', 0):.4f}")
    k4.metric("This Month Cost",       f"${stats.get('cost_this_month', 0):.4f}")
    k5.metric("Avg Latency",           f"{stats.get('avg_latency_ms') or 0:.0f} ms")

    if stats.get("total_calls", 0) == 0:
        st.info(
            "No LLM calls logged yet. Configure a provider in ⚙️ Settings → 🤖 LLM Configuration "
            "and enable it, then trigger a pipeline run to start collecting usage data."
        )

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Models Used")
        if models_breakdown:
            df_models = pd.DataFrame(models_breakdown)
            fig = go.Figure(go.Bar(
                x=[m["model"] for m in models_breakdown],
                y=[m["calls"] for m in models_breakdown],
                marker_color="#3B82F6",
                text=[m["calls"] for m in models_breakdown],
                textposition="outside",
            ))
            fig.update_layout(
                height=220, margin=dict(t=10, b=10, l=10, r=10),
                yaxis=dict(showgrid=False, showticklabels=False),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key="models_bar")
        else:
            st.info("No model usage data yet.")

        st.markdown("#### Token Breakdown")
        if stats.get("total_tokens", 0) > 0:
            prompt = stats.get("total_prompt_tokens", 0)
            completion = stats.get("total_completion_tokens", 0)
            fig2 = go.Figure(go.Pie(
                labels=["Prompt Tokens", "Completion Tokens"],
                values=[prompt, completion],
                marker_colors=["#3B82F6", "#10B981"],
                hole=0.5,
            ))
            fig2.update_layout(
                height=200, margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
            )
            st.plotly_chart(fig2, use_container_width=True, key="token_pie")
        else:
            st.info("No token data yet.")

    with col_right:
        st.markdown("#### Top 10 Costliest SDKs")
        if per_library:
            try:
                libraries = client.get_libraries().get("data", {}).get("libraries", [])
                lib_names = {l["id"]: l.get("sdk_name") or l.get("package","") for l in libraries}
            except APIError:
                lib_names = {}

            df_lib = pd.DataFrame([{
                "SDK":    lib_names.get(r["library_id"], f"ID:{r['library_id']}"),
                "Tokens":     r.get("total_tokens", 0),
                "Calls":      r.get("calls", 0),
                "Cost (USD)": f"${r.get('cost_usd', 0):.6f}",
            } for r in per_library])
            st.dataframe(df_lib, use_container_width=True, hide_index=True)
        else:
            st.info("No per-library cost data yet.")

        st.markdown("#### ROI Estimate")
        total_calls = stats.get("total_calls", 0)
        total_cost  = stats.get("total_cost_usd", 0.0)
        # Assumption: each manual review = 45 minutes of dev time at $80/hr
        hrs_saved   = total_calls * 0.75
        dev_cost    = hrs_saved * 80
        saving      = dev_cost - total_cost
        st.metric("Estimated Dev Hours Saved", f"{hrs_saved:.1f} hrs",
                  delta=f"${dev_cost:.0f} value vs ${total_cost:.4f} AI cost",
                  delta_color="normal")
        if total_calls > 0:
            st.caption(f"ROI: **{dev_cost/max(total_cost,0.001):.0f}×** return — "
                       f"${saving:.2f} net saving (assuming 45 min/review at $80/hr)")

    st.divider()

    # ── Pipeline metrics ───────────────────────────────────────────────────────
    st.markdown("### 🔄 Pipeline Performance")
    if not runs:
        st.info("No pipeline runs yet.")
    else:
        completed_runs = [r for r in runs if r.get("status") in ("completed","partial","failed")]
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Total Runs",        len(runs))
        p2.metric("✅ Completed",      sum(1 for r in runs if r.get("status")=="completed"))
        p3.metric("⚠️ Partial",        sum(1 for r in runs if r.get("status")=="partial"))
        p4.metric("❌ Failed",         sum(1 for r in runs if r.get("status")=="failed"))

        df_runs = pd.DataFrame([{
            "Run ID":    str(r.get("run_id",""))[:16] + "…",
            "Status":    r.get("status","—"),
            "SDKs": r.get("libraries_processed", 0),
            "Updated":   r.get("libraries_updated", 0),
            "Errors":    r.get("errors_count", 0),
            "Started":   format_datetime(r.get("started_at")),
        } for r in runs[:20]])
        st.dataframe(df_runs, use_container_width=True, hide_index=True)

    st.divider()

    # ── Recent LLM call log ────────────────────────────────────────────────────
    if recent_entries:
        st.markdown("### 📋 Recent LLM Calls")
        rows_log = [{
            "Logged At":   format_datetime(e.get("logged_at")),
            "Model":       e.get("model","—"),
            "Prompt Tok":  e.get("prompt_tokens", 0),
            "Completion":  e.get("completion_tokens", 0),
            "Total Tok":   e.get("total_tokens", 0),
            "Cost (USD)":  f"${e.get('estimated_cost_usd', 0):.6f}",
            "Latency ms":  e.get("latency_ms") or "—",
            "SDK ID":  e.get("library_id") or "—",
        } for e in recent_entries[:50]]
        st.dataframe(pd.DataFrame(rows_log), use_container_width=True, hide_index=True)
