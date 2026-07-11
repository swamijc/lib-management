"""
Notification Service — Jinja2 templates for email HTML and Teams Adaptive Card.

Templates are kept as module-level strings so the service has zero external
file dependencies and works identically inside or outside Docker.
"""
from __future__ import annotations
from jinja2 import Environment, BaseLoader

_env = Environment(loader=BaseLoader(), autoescape=True)

# ── Email HTML template ───────────────────────────────────────────────────────

_EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 14px; color: #333; }
  h1 { color: #0078d4; font-size: 20px; }
  h2 { color: #444; font-size: 16px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
  th { background: #0078d4; color: #fff; padding: 8px 12px; text-align: left; }
  td { padding: 6px 12px; border-bottom: 1px solid #eee; }
  tr:hover td { background: #f5f9ff; }
  .badge-critical { background:#c00; color:#fff; padding:2px 7px; border-radius:3px; font-size:11px; }
  .badge-mandatory { background:#d83b01; color:#fff; padding:2px 7px; border-radius:3px; font-size:11px; }
  .badge-recommended { background:#f0ac00; color:#fff; padding:2px 7px; border-radius:3px; font-size:11px; }
  .badge-sufficient { background:#107c10; color:#fff; padding:2px 7px; border-radius:3px; font-size:11px; }
  .badge-deprecated { background:#5c2d91; color:#fff; padding:2px 7px; border-radius:3px; font-size:11px; }
  .section-critical { background: #fff0f0; border-left: 4px solid #c00; padding: 8px 12px; margin-bottom: 12px; }
  .footer { color: #888; font-size: 12px; margin-top: 24px; border-top: 1px solid #eee; padding-top: 8px; }
</style>
</head>
<body>
<h1>📦 SDK Management — Upgrade Report</h1>
<p>Generated: {{ generated_at }}</p>

{% if critical_items %}
<div class="section-critical">
  <strong>⚠️ CRITICAL ALERTS</strong> — Action required before deadline:
  <ul>
  {% for lib in critical_items %}
    <li><strong>{{ lib.package }}</strong> — {{ lib.deadline_notes or 'Deadline approaching' }}
        {% if lib.deadline_date %} | Deadline: <strong>{{ lib.deadline_date }}</strong>{% endif %}
    </li>
  {% endfor %}
  </ul>
</div>
{% endif %}

<h2>Summary ({{ libraries | length }} libraries)</h2>
<table>
  <tr>
    <th>Library</th><th>Platform</th><th>Current</th><th>Latest</th>
    <th>Priority</th><th>Status</th><th>Recommendation</th>
  </tr>
  {% for lib in libraries %}
  <tr>
    <td>{{ lib.package }}</td>
    <td>{{ lib.platform }}</td>
    <td>{{ lib.current_version }}</td>
    <td>{{ lib.latest_version }}</td>
    <td>
      {% if lib.update_needed == 'Mandatory' %}<span class="badge-mandatory">Mandatory</span>
      {% elif lib.update_needed == 'Recommended' %}<span class="badge-recommended">Recommended</span>
      {% else %}{{ lib.update_needed or '—' }}{% endif %}
    </td>
    <td>
      {% if lib.library_status == 'Deprecated' %}<span class="badge-deprecated">Deprecated</span>
      {% else %}{{ lib.library_status or '—' }}{% endif %}
    </td>
    <td>
      {% if lib.upgrade_recommended == 'Yes' %}<span class="badge-mandatory">Upgrade</span>
      {% elif lib.upgrade_recommended == 'Sufficient' %}<span class="badge-sufficient">✓ Current</span>
      {% else %}{{ lib.upgrade_recommended or '—' }}{% endif %}
    </td>
  </tr>
  {% endfor %}
</table>

{% if mandatory_items %}
<h2>🔴 Mandatory Upgrades ({{ mandatory_items | length }})</h2>
<ul>{% for lib in mandatory_items %}<li><strong>{{ lib.package }}</strong> — {{ lib.current_version }} → {{ lib.latest_version }}{% if lib.recommendation_summary %}<br><em>{{ lib.recommendation_summary }}</em>{% endif %}</li>{% endfor %}</ul>
{% endif %}

{% if deprecated_items %}
<h2>🟣 Deprecated Libraries ({{ deprecated_items | length }})</h2>
<ul>{% for lib in deprecated_items %}<li><strong>{{ lib.package }}</strong> ({{ lib.platform }}){% if lib.recommendation_summary %}<br><em>{{ lib.recommendation_summary }}</em>{% endif %}</li>{% endfor %}</ul>
{% endif %}

{% if recommended_items %}
<h2>🟡 Recommended Upgrades ({{ recommended_items | length }})</h2>
<ul>{% for lib in recommended_items %}<li><strong>{{ lib.package }}</strong> — {{ lib.current_version }} → {{ lib.latest_version }}</li>{% endfor %}</ul>
{% endif %}

<div class="footer">SDK Management System · Auto-generated · Do not reply</div>
</body>
</html>
"""

# ── Teams Adaptive Card payload ───────────────────────────────────────────────

_TEAMS_CARD = """
{
  "type": "message",
  "attachments": [{
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": {
      "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
      "type": "AdaptiveCard",
      "version": "1.4",
      "body": [
        {
          "type": "TextBlock",
          "text": "📦 Library Upgrade Report — {{ generated_at }}",
          "weight": "Bolder",
          "size": "Medium",
          "color": "Accent"
        },
        {% if critical_items %}
        {
          "type": "TextBlock",
          "text": "⚠️ CRITICAL: {{ critical_items | length }} libraries require immediate action",
          "color": "Attention",
          "weight": "Bolder",
          "wrap": true
        },
        {% endif %}
        {
          "type": "FactSet",
          "facts": [
            {"title": "Total libraries", "value": "{{ libraries | length }}"},
            {"title": "Mandatory upgrades", "value": "{{ mandatory_items | length }}"},
            {"title": "Deprecated", "value": "{{ deprecated_items | length }}"},
            {"title": "Recommended", "value": "{{ recommended_items | length }}"},
            {"title": "Up-to-date", "value": "{{ sufficient_items | length }}"}
          ]
        }
        {% if mandatory_items or deprecated_items %},
        {
          "type": "TextBlock",
          "text": "**Action Required:**",
          "weight": "Bolder",
          "wrap": true
        },
        {
          "type": "TextBlock",
          "text": "{{ action_lines }}",
          "wrap": true,
          "color": "Attention"
        }
        {% endif %}
      ]
    }
  }]
}
"""


# ── Public render functions ───────────────────────────────────────────────────

def render_email_html(context: dict) -> str:
    return _env.from_string(_EMAIL_HTML).render(**context)


def render_teams_card(context: dict) -> dict:
    import json
    rendered = _env.from_string(_TEAMS_CARD).render(**context)
    return json.loads(rendered)
