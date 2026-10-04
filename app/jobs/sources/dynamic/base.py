"""Dynamic career portal base classes, configuration, and rate-limiting abstractions."""

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import SourceHealthStatus
from app.jobs.sources.adapters import FETCH_TIMEOUT_SECONDS, JobSourceAdapter
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload

logger = logging.getLogger(__name__)


class BlockedSourceError(RuntimeError):
    """Raised when a remote career portal responds with HTTP 403/429 or an automated bot block."""


class DynamicPortalConfig(BaseModel):
    """Configuration for polite, bounded dynamic career portal synchronization."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether this dynamic source is enabled.")
    page_timeout_sec: float = Field(
        default=15.0,
        ge=1.0,
        le=30.0,
        description="Timeout in seconds for dynamic page navigation/rendering (max 30s).",
    )
    request_timeout_sec: float = Field(
        default=30.0,
        ge=1.0,
        le=float(FETCH_TIMEOUT_SECONDS),
        description=f"HTTP request timeout in seconds (must be <= {FETCH_TIMEOUT_SECONDS}s).",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retry attempts on transient network failures.",
    )
    backoff_factor: float = Field(
        default=1.5,
        ge=1.0,
        le=5.0,
        description="Exponential backoff multiplier for retries.",
    )
    request_delay_sec: float = Field(
        default=0.5,
        ge=0.0,
        le=10.0,
        description="Polite request pacing delay between successive requests.",
    )
    max_jobs_per_source: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum jobs to fetch per portal source per cycle.",
    )
    user_agent: str = Field(
        default="JobAI-CareerBuddy/1.0 (+https://github.com/mrchandu1462-ux/job-ai-career-buddy)",
        description="Identifiable, polite user agent header.",
    )


class DynamicPortalAdapter(JobSourceAdapter, ABC):
    """
    Abstract base adapter for dynamic, JavaScript-heavy career portals (e.g. Workday, Greenhouse).

    Invariants
    ----------
    - Enforces finite network timeout (<= 30 seconds).
    - Implements polite rate limiting and bounded retries.
    - Zero timestamp fabrication: unverified/relative dates are set to None.
    - Isolated error handling: blocked/failing sources never crash the scanner cycle.
    - Strictly forbids evasive bypasses or CAPTCHA solving.
    """

    def __init__(
        self,
        name: str,
        config: DynamicPortalConfig | None = None,
    ) -> None:
        self._name = name
        self.config = config or DynamicPortalConfig()
        self.timeout_seconds: int = min(int(self.config.request_timeout_sec), FETCH_TIMEOUT_SECONDS)
        self._last_request_time: float = 0.0
        self._health_status: SourceHealthStatus = SourceHealthStatus.HEALTHY
        self._last_error: str | None = None

    @property
    def adapter_name(self) -> str:
        return self._name

    @property
    def source_category(self) -> str:
        return "dynamic_career_portal"

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True

    def health_status(self) -> SourceHealthStatus:
        return self._health_status

    def _apply_polite_delay(self) -> None:
        """Enforce request pacing delay to prevent aggressive crawling."""
        if self.config.request_delay_sec > 0 and self._last_request_time > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.config.request_delay_sec:
                time.sleep(self.config.request_delay_sec - elapsed)
        self._last_request_time = time.time()

    def execute_with_retry(
        self,
        operation: Callable[[], Any],
        context: str = "request",
    ) -> Any:
        """
        Execute an operation with polite rate limiting and bounded exponential backoff.

        Raises
        ------
        BlockedSourceError
            If HTTP 403/429 or bot detection occurs (no bypass attempted).
        RuntimeError
            If retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            self._apply_polite_delay()
            try:
                return operation()
            except BlockedSourceError as b_err:
                self._health_status = SourceHealthStatus.DEGRADED
                self._last_error = f"Blocked: {b_err}"
                logger.warning(
                    "Dynamic source '%s' encountered access block on %s: %s",
                    self.adapter_name,
                    context,
                    b_err,
                )
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.config.max_retries:
                    delay = self.config.request_delay_sec * (self.config.backoff_factor ** attempt)
                    logger.debug(
                        "Retry %d/%d for '%s' after %.2fs: %s",
                        attempt + 1,
                        self.config.max_retries,
                        self.adapter_name,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    self._health_status = SourceHealthStatus.DEGRADED
                    self._last_error = str(exc)
                    logger.warning(
                        "Source '%s' exhausted %d retries for %s: %s",
                        self.adapter_name,
                        self.config.max_retries,
                        context,
                        exc,
                    )

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Operation failed for source {self.adapter_name}")

    @abstractmethod
    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Fetch and normalize listings matching query criteria."""
