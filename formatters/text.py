"""Plain text report formatter."""

from formatters.base import BaseFormatter
from resources.base import Result


class TextFormatter(BaseFormatter):
    """Human-readable plain text report, delivered as email body."""

    delivery = "body"
    extension = ""

    def render(
        self,
        results: list[Result],
        hostname: str,
        timestamp: str,
        version: str,
    ) -> str:
        """Render all results as a plain text report string."""
        sep = "-" * 60
        sep2 = "=" * 60

        lines = [
            sep2,
            f"  SERVER REPORT: {hostname}",
            f"  Date:          {timestamp}",
            f"  Version:       {version}",
            sep2,
            "",
        ]

        # Alerts summary
        all_alerts = [a for r in results for a in r.alerts]
        lines.append("ALERTS")
        if all_alerts:
            for alert in all_alerts:
                lines.append(f"  [!] {alert}")
        else:
            lines.append("  All systems nominal.")
        lines.append("")
        lines.append(sep)

        for result in results:
            lines.append("")
            status_tag = f"[{result.status.upper()}]"
            lines.append(f"{result.name}  {status_tag}")

            if result.error:
                lines.append(f"  ERROR: {result.error}")
            else:
                self._render_metrics(lines, result)

            if result.alerts:
                for alert in result.alerts:
                    lines.append(f"  >> {alert}")

            lines.append(sep)

        lines.append("")
        lines.append(f"Report generated automatically by server-report v{version}")
        lines.append(sep2)

        return "\n".join(lines)

    def _render_metrics(self, lines: list[str], result: Result) -> None:
        """Append metric lines for a single result."""
        m = result.metrics

        if result.name == "CPU":
            lines.append(f"  Cores:     {m.get('cores', 'n/a')}")
            lines.append(
                f"  Load avg:  {m.get('load_1m', 0):.2f}  "
                f"{m.get('load_5m', 0):.2f}  {m.get('load_15m', 0):.2f}  "
                f"(1m / 5m / 15m)"
            )
            top = m.get("top_cpu", [])
            if top:
                lines.append("  Top by CPU:")
                for p in top:
                    lines.append(
                        f"    {p['user']:<12} {p['cpu']:>5}%  {p['cmd'][:50]}"
                    )

        elif result.name == "Memory":
            ram = m.get("ram", {})
            swap = m.get("swap", {})
            lines.append(
                f"  RAM:   {ram.get('used_mb', 0)} MB / {ram.get('total_mb', 0)} MB"
                f"  ({ram.get('pct', 0):.1f}%)"
            )
            lines.append(
                f"  Swap:  {swap.get('used_mb', 0)} MB / {swap.get('total_mb', 0)} MB"
            )

        elif result.name == "Disk":
            for p in m.get("partitions", []):
                lines.append(
                    f"  {p['mount']:<25} {p['used']:>6} / {p['size']:>6}"
                    f"  (free: {p['avail']:>6}  usage: {p['pct']})"
                )

        elif result.name == "Network":
            for line in m.get("tcp_summary", []):
                lines.append(f"  {line}")
            logins = m.get("recent_logins", [])
            if logins:
                lines.append("  Recent logins:")
                for login in logins:
                    lines.append(f"    {login}")

        elif result.name == "Services":
            failed = m.get("failed_services", [])
            lines.append(f"  Failed: {m.get('failed_count', 0)}")
            for svc in failed:
                lines.append(f"    - {svc}")
            watched = m.get("watched", {})
            if watched:
                lines.append("  Watched:")
                for svc, state in watched.items():
                    lines.append(f"    {svc}: {state}")

        else:
            # Generic fallback: key = value for flat values
            for key, val in m.items():
                if isinstance(val, (str, int, float, bool)):
                    lines.append(f"  {key}: {val}")
