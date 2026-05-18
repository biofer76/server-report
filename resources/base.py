"""Base interfaces for all resource collectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Result:
    """Output of a single collector run."""

    name: str
    status: str                                        # "ok" | "warning" | "error" | "unavailable"
    metrics: dict                                      # free-form, structure defined by each collector
    alerts: list[str] = field(default_factory=list)   # empty if no issues
    error: str | None = None                           # set if collect() raised an exception


class BaseCollector(ABC):
    """Abstract base class every resource collector must implement."""

    def __init__(self, config: dict) -> None:
        """
        Receive the merged config dict for this resource.

        Keys come from configs/base/<resource>.yaml overridden by
        configs/<server_id>/<resource>.yaml. Secrets must be read from
        environment variables, not from config.
        """
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the resource (e.g. 'CPU', 'Restic Snapshots')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if this collector can run on the current host.

        Called before collect(). If False, the collector is silently skipped.
        """
        ...

    @abstractmethod
    def collect(self) -> Result:
        """
        Collect metrics and return a Result object.

        Must never raise exceptions: catch internally and return a Result
        with status='error' and the error message set.
        """
        ...
