"""HTML report formatter."""

import html as html_lib

from formatters.base import BaseFormatter
from resources.base import Result

_STATUS_COLORS = {
    "ok": "#28a745",
    "warning": "#ffc107",
    "error": "#dc3545",
    "unavailable": "#6c757d",
}


def _e(text: str) -> str:
    """HTML-escape a string."""
    return html_lib.escape(str(text))


class HtmlFormatter(BaseFormatter):
    """HTML report, delivered as email body."""

    delivery = "body"
    extension = ""

    def render(
        self,
        results: list[Result],
        hostname: str,
        timestamp: str,
        version: str,
    ) -> str:
        """Render all results as an HTML string with inline styles."""
        all_alerts = [a for r in results for a in r.alerts]
        overall_status = "ok"
        for r in results:
            if r.status == "error":
                overall_status = "error"
                break
            if r.status == "warning":
                overall_status = "warning"

        header_color = _STATUS_COLORS.get(overall_status, "#343a40")

        sections = []
        for result in results:
            sections.append(self._render_section(result))

        alerts_html = self._render_alerts_summary(all_alerts)
        sections_html = "\n".join(sections)

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Server Report: {_e(hostname)}</title></head>
<body style="font-family: monospace; background: #f8f9fa; padding: 20px; margin: 0;">
  <div style="max-width: 800px; margin: 0 auto;">
    <div style="background: {header_color}; color: #fff; padding: 16px 20px; border-radius: 4px 4px 0 0;">
      <h1 style="margin: 0; font-size: 18px;">SERVER REPORT: {_e(hostname)}</h1>
      <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.85;">
        {_e(timestamp)} &nbsp;&bull;&nbsp; v{_e(version)}
      </p>
    </div>
    {alerts_html}
    {sections_html}
    <p style="font-size: 11px; color: #6c757d; margin-top: 12px;">
      Generated automatically by server-report v{_e(version)}
    </p>
  </div>
</body>
</html>"""

    def _render_alerts_summary(self, alerts: list[str]) -> str:
        if not alerts:
            return (
                '<div style="background:#d4edda;color:#155724;padding:12px 16px;'
                'border-left:4px solid #28a745;margin-top:0;">'
                "All systems nominal.</div>"
            )
        items = "".join(f"<li>{_e(a)}</li>" for a in alerts)
        return (
            '<div style="background:#fff3cd;color:#856404;padding:12px 16px;'
            'border-left:4px solid #ffc107;margin-top:0;">'
            f"<strong>Alerts</strong><ul style='margin:6px 0 0;padding-left:20px'>{items}</ul></div>"
        )

    def _render_section(self, result: Result) -> str:
        color = _STATUS_COLORS.get(result.status, "#6c757d")
        badge = (
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:3px;font-size:11px;">{_e(result.status.upper())}</span>'
        )
        body = self._render_body(result)
        return f"""
    <div style="background:#fff;border:1px solid #dee2e6;border-radius:4px;
                margin-top:12px;overflow:hidden;">
      <div style="background:#f1f3f5;padding:8px 16px;border-bottom:1px solid #dee2e6;
                  display:flex;justify-content:space-between;align-items:center;">
        <strong style="font-size:14px;">{_e(result.name)}</strong>
        {badge}
      </div>
      <div style="padding:12px 16px;font-size:13px;line-height:1.6;">
        {body}
      </div>
    </div>"""

    def _render_body(self, result: Result) -> str:
        if result.error:
            return f'<p style="color:#dc3545;margin:0;">ERROR: {_e(result.error)}</p>'

        parts = []
        m = result.metrics

        if result.name == "CPU":
            parts.append(
                f"<p style='margin:0'><b>Cores:</b> {_e(m.get('cores', 'n/a'))}<br>"
                f"<b>Load avg:</b> {m.get('load_1m',0):.2f} / "
                f"{m.get('load_5m',0):.2f} / {m.get('load_15m',0):.2f} "
                "(1m / 5m / 15m)</p>"
            )
            top = m.get("top_cpu", [])
            if top:
                rows = "".join(
                    f"<tr><td>{_e(p['user'])}</td><td>{_e(p['cpu'])}%</td>"
                    f"<td style='max-width:320px;overflow:hidden;text-overflow:ellipsis'>"
                    f"{_e(p['cmd'][:60])}</td></tr>"
                    for p in top
                )
                parts.append(
                    '<p style="margin:8px 0 2px"><b>Top by CPU:</b></p>'
                    '<table style="width:100%;border-collapse:collapse;font-size:12px">'
                    "<tr style='background:#f8f9fa'><th align='left'>User</th>"
                    "<th align='left'>CPU%</th><th align='left'>Command</th></tr>"
                    f"{rows}</table>"
                )

        elif result.name == "Memory":
            ram = m.get("ram", {})
            swap = m.get("swap", {})
            parts.append(
                f"<p style='margin:0'>"
                f"<b>RAM:</b> {_e(ram.get('used_mb',0))} MB / "
                f"{_e(ram.get('total_mb',0))} MB ({ram.get('pct',0):.1f}%)<br>"
                f"<b>Swap:</b> {_e(swap.get('used_mb',0))} MB / "
                f"{_e(swap.get('total_mb',0))} MB</p>"
            )

        elif result.name == "Disk":
            rows = "".join(
                f"<tr><td>{_e(p['mount'])}</td><td>{_e(p['used'])}</td>"
                f"<td>{_e(p['size'])}</td><td>{_e(p['avail'])}</td>"
                f"<td><b>{_e(p['pct'])}</b></td></tr>"
                for p in m.get("partitions", [])
            )
            parts.append(
                '<table style="width:100%;border-collapse:collapse;font-size:12px">'
                "<tr style='background:#f8f9fa'><th align='left'>Mount</th>"
                "<th align='left'>Used</th><th align='left'>Size</th>"
                "<th align='left'>Avail</th><th align='left'>Usage</th></tr>"
                f"{rows}</table>"
            )

        elif result.name == "Network":
            tcp = "<br>".join(_e(l) for l in m.get("tcp_summary", []))
            logins = m.get("recent_logins", [])
            login_html = "<br>".join(_e(l) for l in logins)
            parts.append(f"<p style='margin:0'>{tcp}</p>")
            if logins:
                parts.append(
                    f"<p style='margin:8px 0 0'><b>Recent logins:</b><br>{login_html}</p>"
                )

        elif result.name == "Services":
            failed = m.get("failed_services", [])
            parts.append(
                f"<p style='margin:0'><b>Failed:</b> {_e(m.get('failed_count', 0))}</p>"
            )
            if failed:
                items = "".join(f"<li>{_e(s)}</li>" for s in failed)
                parts.append(f"<ul style='margin:4px 0;padding-left:20px'>{items}</ul>")

        else:
            flat = {k: v for k, v in m.items() if isinstance(v, (str, int, float, bool))}
            if flat:
                rows = "".join(
                    f"<tr><td><b>{_e(k)}</b></td><td>{_e(v)}</td></tr>"
                    for k, v in flat.items()
                )
                parts.append(
                    f"<table style='border-collapse:collapse;font-size:12px'>{rows}</table>"
                )

        if result.alerts:
            alert_items = "".join(f"<li>{_e(a)}</li>" for a in result.alerts)
            parts.append(
                '<ul style="margin:8px 0 0;padding-left:20px;color:#856404">'
                f"{alert_items}</ul>"
            )

        return "\n".join(parts) if parts else "<p style='margin:0;color:#6c757d'>No data.</p>"
