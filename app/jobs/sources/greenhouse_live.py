"""Live Greenhouse Job Board API adapter for discovering verified real-world semiconductor listings."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.jobs.models import SourceHealthStatus
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload
from app.jobs.sources.dynamic.base import DynamicPortalAdapter, DynamicPortalConfig

logger = logging.getLogger(__name__)

# Known public Greenhouse board tokens for semiconductor and hardware teams
DEFAULT_GREENHOUSE_BOARDS: list[dict[str, str]] = [
    {"token": "sifive", "company": "SiFive"},
    {"token": "tenstorrent", "company": "Tenstorrent"},
    {"token": "groq", "company": "Groq"},
    {"token": "cerebras", "company": "Cerebras Systems"},
    {"token": "untetherai", "company": "Untether AI"},
    {"token": "rivos", "company": "Rivos"},
]


def strip_html(raw_html: str) -> str:
    """Safely convert HTML job description to clean, decoded plain text."""
    if not raw_html:
        return ""
    # Decode HTML entities
    text = html.unescape(raw_html)
    # Replace block elements with linebreaks
    text = re.sub(r"<(?:p|div|br|li|h[1-6]|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Normalize multiple whitespace / blank lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


class LiveGreenhouseAdapter(DynamicPortalAdapter):
    """
    Production-grade live adapter fetching authentic job postings from Greenhouse public boards API.
    (e.g., https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true).

    Invariants:
    - Never fabricates listings or timestamps.
    - Captures created_at and updated_at explicitly from remote JSON payloads.
    - Uses strict TLS verification (ssl.create_default_context()) and finite request timeouts.
    - Isolates board-level failures gracefully without crashing scanner execution.
    - is_fixture is strictly False for authentic live data.
    """

    is_fixture: bool = False

    def __init__(
        self,
        name: str = "live_greenhouse",
        boards: list[dict[str, str]] | None = None,
        config: DynamicPortalConfig | None = None,
        transport: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(name=name, config=config)
        self.boards = boards or list(DEFAULT_GREENHOUSE_BOARDS)
        self._transport = transport

    @property
    def source_category(self) -> str:
        return "career_pages"

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True

    def _fetch_board_payload(self, board_token: str) -> dict[str, Any] | None:
        """Fetch raw JSON payload for a given Greenhouse board token."""
        if self._transport is not None:
            return self._transport(board_token)

        url = f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(board_token)}/jobs?content=true"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "application/json",
            },
        )
        ctx = ssl.create_default_context()
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds, context=ctx) as resp:
                if resp.status != 200:
                    logger.warning("Greenhouse board %s returned HTTP %s", board_token, resp.status)
                    return None
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as ex:
            logger.warning("HTTP error fetching Greenhouse board %s: %s", board_token, ex)
            if ex.code in (403, 429):
                self._health_status = SourceHealthStatus.DEGRADED
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            logger.warning("Network timeout/error fetching Greenhouse board %s: %s", board_token, ex)
            self._health_status = SourceHealthStatus.DEGRADED
            return None
        except json.JSONDecodeError as ex:
            logger.warning("Malformed JSON response from Greenhouse board %s: %s", board_token, ex)
            return None

    def parse_job_item(self, item: dict[str, Any], default_company: str) -> RawJobPayload | None:
        """Parse an authentic Greenhouse JSON item into a standardized RawJobPayload."""
        if not isinstance(item, dict):
            return None

        title = str(item.get("title") or "").strip()
        if not title:
            return None

        job_id = str(item.get("id") or item.get("internal_job_id") or "").strip()
        req_id = str(item.get("requisition_id") or "").strip() or None

        # Extract location
        loc_name = None
        loc_obj = item.get("location")
        if isinstance(loc_obj, dict):
            loc_name = loc_obj.get("name")
        elif loc_obj:
            loc_name = str(loc_obj).strip()

        if not loc_name and item.get("offices") and isinstance(item["offices"], list) and len(item["offices"]) > 0:
            loc_name = item["offices"][0].get("name")

        location = str(loc_name).strip() if loc_name else None

        # Clean description content
        raw_content = item.get("content") or item.get("description") or ""
        plain_content = strip_html(str(raw_content))
        if not plain_content:
            plain_content = f"{default_company} is hiring for {title} in {location or 'unspecified location'}."

        source_url = item.get("absolute_url") or (
            f"https://boards.greenhouse.io/{default_company.lower().replace(' ', '')}/jobs/{job_id}"
            if job_id
            else None
        )
        app_url = item.get("apply_url") or source_url

        # Explicit timestamp handling (updated_at vs created_at)
        created_at_raw = item.get("created_at")
        updated_at_raw = item.get("updated_at")
        raw_posted = updated_at_raw or created_at_raw or item.get("published_at")

        published_at: str | None = None
        timestamp_source = "unverified"

        if raw_posted:
            posted_str = str(raw_posted).strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}", posted_str):
                try:
                    clean_ts = posted_str.replace("Z", "+00:00")
                    parsed = datetime.fromisoformat(clean_ts)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    now_utc = datetime.now(UTC)
                    # Future timestamp safety guard
                    if parsed > now_utc + timedelta(hours=1):
                        published_at = None
                        timestamp_source = "unverified"
                    else:
                        published_at = parsed.isoformat()
                        timestamp_source = "greenhouse_api"
                except (ValueError, TypeError):
                    published_at = None
                    timestamp_source = "unverified"

        now_iso = datetime.now(UTC).isoformat()
        hash_input = f"{default_company}|{title}|{location or ''}|{job_id}|{plain_content[:500]}"
        content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        return RawJobPayload(
            company=default_company,
            title=title,
            raw_payload=plain_content,
            location=location,
            country=None,  # Country will be inferred during normalization
            employment_type="Full-time",
            source=self.adapter_name,
            source_url=source_url,
            application_url=app_url,
            discovered_at=now_iso,
            content_hash=content_hash,
            metadata={
                "published_at": published_at,
                "timestamp_source": timestamp_source,
                "created_at": created_at_raw,
                "updated_at": updated_at_raw,
                "portal_type": "greenhouse_api",
                "internal_job_id": job_id,
                "requisition_id": req_id,
                "is_live_source": True,
            },
        )

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Fetch, parse, and return authentic listings from all configured boards."""
        if not self.config.enabled:
            return []

        results: list[RawJobPayload] = []
        for board_cfg in self.boards:
            token = board_cfg["token"]
            company_name = board_cfg.get("company", token.capitalize())

            data = self._fetch_board_payload(token)
            if not data or not isinstance(data, dict):
                continue

            jobs_list = data.get("jobs", [])
            if not isinstance(jobs_list, list):
                continue

            for raw_item in jobs_list:
                parsed = self.parse_job_item(raw_item, default_company=company_name)
                if parsed is None:
                    continue

                results.append(parsed)
                if len(results) >= query.limit:
                    return results

        return results
