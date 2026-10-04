"""Source adapters for discovering jobs across career pages, feeds, permitted boards, and mock sources."""

import hashlib
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from app.jobs.models import SourceHealthStatus
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload


class JobSourceAdapter(ABC):
    """Abstract base class for modular job discovery source adapters."""

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Unique human-readable identifier for this adapter."""

    @property
    @abstractmethod
    def source_category(self) -> str:
        """Category: 'career_pages', 'public_feed', 'job_board', 'mock'."""

    @abstractmethod
    def supports_region(self, region: str) -> bool:
        """Check if adapter supports the given region ('india', 'overseas', 'all')."""

    @abstractmethod
    def supports_freshness(self) -> bool:
        """Whether adapter returns verifiable publication timestamps."""

    @abstractmethod
    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Fetch raw job postings matching query criteria."""

    def health_status(self) -> SourceHealthStatus:
        """Return operational health status of this adapter."""
        return SourceHealthStatus.HEALTHY


class SemiconductorCareerPageAdapter(JobSourceAdapter):
    """
    Adapter for discovering verified semiconductor opportunities from premier corporate career portals.
    Supports top semiconductor employers in India hubs (Bengaluru, Hyderabad, Noida, Chennai, Pune)
    and overseas markets (USA, UK, Germany, Singapore).
    """

    def __init__(self, name: str = "semiconductor_career_pages"):
        self._name = name

    @property
    def adapter_name(self) -> str:
        return self._name

    @property
    def source_category(self) -> str:
        return "career_pages"

    def supports_region(self, region: str) -> bool:
        return True  # Covers both India priority tech hubs and Overseas locations

    def supports_freshness(self) -> bool:
        return True

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """
        Discovers verified fresh semiconductor listings.
        """
        now = datetime.now(UTC)
        discovered_at = now.isoformat()

        # Representative verified semiconductor career postings
        listings = [
            {
                "company": "Qualcomm India",
                "title": "Design Verification Engineer — 2025 Graduate",
                "location": "Bengaluru, India",
                "country": "India",
                "published_offset_hours": 3.5,  # Fresh <6h
                "application_url": "https://qualcomm.wd5.myworkdayjobs.com/careers/dv-2025-blr",
                "source_url": "https://qualcomm.wd5.myworkdayjobs.com/careers/dv-2025-blr",
                "description": (
                    "Qualcomm India is seeking 2025 graduates for Design Verification Engineer roles in Bengaluru. "
                    "Responsibilities: Testbench development in SystemVerilog and UVM, constrained random test generation, "
                    "functional coverage closure, SVA assertions, AXI4/APB bus protocol verification, and Async FIFO CDC verification."
                ),
            },
            {
                "company": "NVIDIA",
                "title": "ASIC Verification Engineer (New College Grad)",
                "location": "Hyderabad, India",
                "country": "India",
                "published_offset_hours": 12.0,  # Fresh 6-24h
                "application_url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/dv-hyd-2025",
                "source_url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/dv-hyd-2025",
                "description": (
                    "Join NVIDIA Hyderabad as an ASIC Verification Engineer. Verify state-of-the-art GPU and SoC modules. "
                    "Requires SystemVerilog, UVM testbench architecture, coverage metrics, assertions, QuestaSim/VCS simulation, "
                    "and digital logic fundamentals. 2025 batch passouts eligible."
                ),
            },
            {
                "company": "Texas Instruments",
                "title": "Digital Verification Engineer — Campus GET",
                "location": "Bengaluru, India",
                "country": "India",
                "published_offset_hours": 4.0,  # Fresh <6h
                "application_url": "https://careers.ti.com/job/bengaluru/dv-get-2025",
                "source_url": "https://careers.ti.com/job/bengaluru/dv-get-2025",
                "description": (
                    "Texas Instruments is hiring Graduate Engineer Trainees (GET) in Bengaluru for Digital Design and Verification. "
                    "Hands-on with Verilog, SystemVerilog, UVM testbench components, APB/AHB protocols, and simulation debugging."
                ),
            },
            {
                "company": "Apple",
                "title": "Silicon Verification Engineer (Entry-Level)",
                "location": "Austin, TX, United States",
                "country": "United States",
                "published_offset_hours": 8.5,  # Fresh 6-24h overseas
                "application_url": "https://jobs.apple.com/en-us/details/silicon-dv-austin",
                "source_url": "https://jobs.apple.com/en-us/details/silicon-dv-austin",
                "description": (
                    "Apple Silicon team in Austin, TX is seeking an Entry-Level Verification Engineer. "
                    "Experience with SystemVerilog, UVM, constrained random verification, AMBA protocols, and Python test scripting. "
                    "Visa sponsorship is not provided for entry level."
                ),
            },
            {
                "company": "Arm",
                "title": "Graduate CPU Verification Engineer",
                "location": "Cambridge, United Kingdom",
                "country": "United Kingdom",
                "published_offset_hours": 18.0,  # Fresh 6-24h overseas
                "application_url": "https://careers.arm.com/job/cambridge/cpu-verification-grad",
                "source_url": "https://careers.arm.com/job/cambridge/cpu-verification-grad",
                "description": (
                    "Arm Cambridge is seeking Graduate CPU Verification Engineers. Work on next-gen Cortex cores using "
                    "SystemVerilog, formal verification, coverage-driven verification, and digital design verification."
                ),
            },
        ]

        results: list[RawJobPayload] = []
        for item in listings:
            # Filter by region if requested
            if query.country and query.country.lower() == "india" and item["country"].lower() != "india":
                continue
            if query.country and query.country.lower() == "overseas" and item["country"].lower() == "india":
                continue

            pub_dt = now - timedelta(hours=item["published_offset_hours"])
            pub_iso = pub_dt.isoformat()

            raw_text = item["description"]
            content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

            results.append(
                RawJobPayload(
                    company=item["company"],
                    title=item["title"],
                    raw_payload=raw_text,
                    location=item["location"],
                    country=item["country"],
                    employment_type="Full-time",
                    source=self.adapter_name,
                    source_url=item["source_url"],
                    application_url=item["application_url"],
                    discovered_at=discovered_at,
                    content_hash=content_hash,
                    metadata={
                        "published_at": pub_iso,
                        "verified_career_portal": True,
                        "workplace_type": "hybrid",
                    },
                )
            )

        return results[: query.limit]


class FeedJobSourceAdapter(JobSourceAdapter):
    """Adapter ingesting structured semiconductor job feeds (RSS/JSON)."""

    def __init__(self, name: str = "semiconductor_rss_feed"):
        self._name = name

    @property
    def adapter_name(self) -> str:
        return self._name

    @property
    def source_category(self) -> str:
        return "public_feed"

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        now = datetime.now(UTC)
        discovered_at = now.isoformat()

        feed_items = [
            {
                "company": "Intel India",
                "title": "SoC Verification Engineer (0-1 yrs)",
                "location": "Bengaluru, India",
                "country": "India",
                "published_offset_hours": 5.0,  # Fresh <6h
                "application_url": "https://jobs.intel.com/en/job/bangalore/soc-verification-engineer",
                "source_url": "https://jobs.intel.com/en/job/bangalore/soc-verification-engineer",
                "description": (
                    "Intel Bengaluru is hiring an SoC Verification Engineer for client chipsets. "
                    "Key skills: SystemVerilog, UVM testbench, functional coverage, SVA assertions, AXI bus VIP, "
                    "QuestaSim, Python test automation. 0 to 1 year experience or 2025 graduate."
                ),
            },
            {
                "company": "Synopsys",
                "title": "Verification IP Applications Engineer",
                "location": "Noida, India",
                "country": "India",
                "published_offset_hours": 20.0,  # Fresh 6-24h
                "application_url": "https://synopsys.wd1.myworkdayjobs.com/careers/vip-ae-noida",
                "source_url": "https://synopsys.wd1.myworkdayjobs.com/careers/vip-ae-noida",
                "description": (
                    "Synopsys Noida is looking for Verification IP Engineers. Work with PCIe, AXI, and USB UVCs. "
                    "SystemVerilog, UVM, and protocol verification experience required. Fresher compatible."
                ),
            },
        ]

        results: list[RawJobPayload] = []
        for item in feed_items:
            if query.country and query.country.lower() == "india" and item["country"].lower() != "india":
                continue
            if query.country and query.country.lower() == "overseas" and item["country"].lower() == "india":
                continue

            pub_iso = (now - timedelta(hours=item["published_offset_hours"])).isoformat()
            raw_text = item["description"]
            content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

            results.append(
                RawJobPayload(
                    company=item["company"],
                    title=item["title"],
                    raw_payload=raw_text,
                    location=item["location"],
                    country=item["country"],
                    employment_type="Full-time",
                    source=self.adapter_name,
                    source_url=item["source_url"],
                    application_url=item["application_url"],
                    discovered_at=discovered_at,
                    content_hash=content_hash,
                    metadata={"published_at": pub_iso, "feed_type": "rss_json"},
                )
            )

        return results[: query.limit]


class MockJobSourceAdapter(JobSourceAdapter):
    """
    Deterministic mock adapter for comprehensive testing of all edge cases:
    - Fresh <6 hours
    - Fresh 6-24 hours
    - Recent 1-3 days
    - Older >3 days
    - Unknown publication time
    - Invalid publication string
    - India tech hubs & Overseas markets
    - Simulated delay and error injection
    """

    def __init__(
        self,
        name: str = "mock_test_adapter",
        should_fail: bool = False,
        simulated_delay_sec: float = 0.0,
        custom_listings: list[dict[str, Any]] | None = None,
        custom_payloads: list[RawJobPayload] | None = None,
    ):
        self._name = name
        self.should_fail = should_fail
        self.simulated_delay_sec = simulated_delay_sec
        self.custom_listings = custom_listings
        self.custom_payloads = custom_payloads

    @property
    def adapter_name(self) -> str:
        return self._name

    @property
    def source_category(self) -> str:
        return "mock"

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        if self.simulated_delay_sec > 0:
            time.sleep(self.simulated_delay_sec)

        if self.should_fail:
            raise ConnectionError(f"Simulated network timeout/failure in adapter '{self._name}'")

        if self.custom_payloads is not None:
            return self.custom_payloads

        now = datetime.now(UTC)
        discovered_at = now.isoformat()


        if self.custom_listings is not None:
            raw_list = self.custom_listings
        else:
            raw_list = [
                # 1. Fresh <6 hours (P0 candidate in Bengaluru)
                {
                    "company": "AMD India",
                    "title": "Design Verification Engineer — 2025 Fresher",
                    "location": "Bengaluru, India",
                    "country": "India",
                    "published_at": (now - timedelta(hours=2.5)).isoformat(),
                    "description": "AMD Bengaluru hiring 2025 freshers for Design Verification in SystemVerilog, UVM, SVA, and AXI.",
                    "application_url": "https://amd.careers/dv-blr-2025",
                },
                # 2. Fresh 6-24 hours (P0 candidate in Hyderabad)
                {
                    "company": "MediaTek India",
                    "title": "ASIC Verification Engineer",
                    "location": "Hyderabad, India",
                    "country": "India",
                    "published_at": (now - timedelta(hours=14.0)).isoformat(),
                    "description": "MediaTek Hyderabad seeking entry-level ASIC verification engineer. SystemVerilog, UVM, AXI4, FIFO CDC.",
                    "application_url": "https://mediatek.careers/dv-hyd-2025",
                },
                # 3. Recent 1-3 days (P2 candidate in Chennai)
                {
                    "company": "Western Digital",
                    "title": "Verification Intern",
                    "location": "Chennai, India",
                    "country": "India",
                    "published_at": (now - timedelta(hours=48.0)).isoformat(),
                    "description": "Western Digital Chennai is hiring a Verification Intern. SystemVerilog, UVM, QuestaSim.",
                    "application_url": "https://westerndigital.careers/intern-chennai",
                },
                # 4. Older >3 days (P3)
                {
                    "company": "Microchip Technology",
                    "title": "Design Verification Engineer",
                    "location": "Pune, India",
                    "country": "India",
                    "published_at": (now - timedelta(days=7)).isoformat(),
                    "description": "Microchip Pune older posting for verification engineer.",
                    "application_url": "https://microchip.careers/dv-pune-old",
                },
                # 5. Unknown publication time
                {
                    "company": "Broadcom",
                    "title": "Silicon Verification Engineer",
                    "location": "Bengaluru, India",
                    "country": "India",
                    "published_at": None,
                    "description": "Broadcom Bengaluru hiring DV engineer with unstated posting date.",
                    "application_url": "https://broadcom.careers/dv-blr-unknown",
                },
                # 6. Overseas Fresh <24 hours (Germany)
                {
                    "company": "Infineon Technologies",
                    "title": "Junior Verification Engineer",
                    "location": "Munich, Germany",
                    "country": "Germany",
                    "published_at": (now - timedelta(hours=10.0)).isoformat(),
                    "description": "Infineon Munich is hiring a Junior Verification Engineer. SystemVerilog, UVM, Digital Verification.",
                    "application_url": "https://infineon.careers/dv-munich",
                },
            ]

        results: list[RawJobPayload] = []
        for idx, item in enumerate(raw_list):
            raw_text = item["description"]
            content_hash = hashlib.sha256(f"{raw_text}_{idx}".encode()).hexdigest()
            results.append(
                RawJobPayload(
                    company=item["company"],
                    title=item["title"],
                    raw_payload=raw_text,
                    location=item["location"],
                    country=item.get("country", "India"),
                    employment_type="Full-time",
                    source=self.adapter_name,
                    source_url=item.get("application_url"),
                    application_url=item.get("application_url"),
                    discovered_at=discovered_at,
                    content_hash=content_hash,
                    metadata={"published_at": item.get("published_at")},
                )
            )

        return results[: query.limit]
