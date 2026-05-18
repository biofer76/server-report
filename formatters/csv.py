"""CSV report formatter — fixed-column anomaly log as attachment."""

import csv
import io

from formatters.base import BaseFormatter
from resources.base import Result


class CsvFormatter(BaseFormatter):
    """Fixed-column anomaly log, delivered as .csv attachment.

    Columns: timestamp, server, version, resource, status, alerts
    The alerts column contains all alert strings joined by '|'.
    Never accesses Result.metrics.
    """

    delivery = "attachment"
    extension = ".csv"

    def render(
        self,
        results: list[Result],
        hostname: str,
        timestamp: str,
        version: str,
    ) -> str:
        """Render results as a CSV string with fixed columns."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["timestamp", "server", "version", "resource", "status", "alerts"])
        for r in results:
            writer.writerow([
                timestamp,
                hostname,
                version,
                r.name,
                r.status,
                "|".join(r.alerts),
            ])
        return buf.getvalue()
