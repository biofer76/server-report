"""Abstract base class for all report formatters."""

from abc import ABC, abstractmethod

from resources.base import Result


class BaseFormatter(ABC):
    """Contract every formatter must implement."""

    delivery: str = "body"    # "body" | "attachment"
    extension: str = ""       # file extension when delivery == "attachment"

    @abstractmethod
    def render(
        self,
        results: list[Result],
        hostname: str,
        timestamp: str,
        version: str,
    ) -> str:
        """
        Receive the full list of Result objects and return the formatted output.

        Called once per unique format needed across all recipients.
        """
        ...
