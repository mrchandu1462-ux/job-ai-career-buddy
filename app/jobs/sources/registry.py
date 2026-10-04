"""Registry managing modular job discovery sources."""

from app.jobs.sources.base import (
    JobDiscoveryQuery,
    JobSource,
    RawJobPayload,
)


class JobSourceRegistry:
    """Central registry holding and querying all configured job sources."""

    def __init__(self):
        self._sources: dict[str, JobSource] = {}

    def register_source(self, source: JobSource) -> None:
        """Register a new job source."""
        self._sources[source.source_name] = source

    def unregister_source(self, source_name: str) -> None:
        """Unregister a job source by name."""
        if source_name in self._sources:
            del self._sources[source_name]

    def get_source(self, source_name: str) -> JobSource | None:
        """Get a registered source by name."""
        return self._sources.get(source_name)

    def list_sources(self) -> list[str]:
        """List names of all registered job sources."""
        return sorted(self._sources.keys())

    def search_all(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Search across all registered job sources and aggregate discovered raw payloads."""
        aggregated: list[RawJobPayload] = []
        for source in self._sources.values():
            found = source.search(query)
            aggregated.extend(found)
        return aggregated
