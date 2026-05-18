"""JSON report formatter — full structured output as attachment."""

import json as json_lib
from dataclasses import asdict

from formatters.base import BaseFormatter
from resources.base import Result


class JsonFormatter(BaseFormatter):
    """Full serialisation of all Result objects, delivered as .json attachment."""

    delivery = "attachment"
    extension = ".json"

    def render(
        self,
        results: list[Result],
        hostname: str,
        timestamp: str,
        version: str,
    ) -> str:
        """Render results as a pretty-printed JSON string."""
        payload = {
            "timestamp": timestamp,
            "server": hostname,
            "version": version,
            "results": [asdict(r) for r in results],
        }
        return json_lib.dumps(payload, indent=2, ensure_ascii=False)
