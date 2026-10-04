"""Job ranking and segmentation utility."""

from app.db.models import NormalizedJob
from app.matching.models import JobMatchResult
from app.matching.scorer import JobScoringEngine
from app.profile.models import CandidateProfile, FactBank


class JobRanker:
    """Ranks and segments jobs based on deterministic eligibility and relevance match scores."""

    def __init__(self, profile: CandidateProfile, fact_bank: FactBank):
        self.scoring_engine = JobScoringEngine(profile, fact_bank)

    def rank_jobs(
        self,
        jobs: list[NormalizedJob],
        eligible_only: bool = False,
        min_score: float = 0.0,
    ) -> list[JobMatchResult]:
        """Score and sort jobs descending by match score."""
        results: list[JobMatchResult] = []
        for job in jobs:
            match = self.scoring_engine.score_job(job)
            if eligible_only and not match.is_eligible:
                continue
            if match.match_score < min_score:
                continue
            results.append(match)

        # Sort descending by match score
        results.sort(key=lambda r: (-r.match_score, r.company))
        return results

    def get_top_india_matches(
        self, jobs: list[NormalizedJob], limit: int = 20
    ) -> list[JobMatchResult]:
        """Return top eligible job opportunities in priority India hubs."""
        ranked = self.rank_jobs(jobs, eligible_only=True)
        india_jobs = [r for r in ranked if not r.is_overseas]
        return india_jobs[:limit]

    def get_top_overseas_matches(
        self, jobs: list[NormalizedJob], limit: int = 20
    ) -> list[JobMatchResult]:
        """Return top eligible overseas job opportunities with sponsorship tracking."""
        ranked = self.rank_jobs(jobs, eligible_only=True)
        overseas_jobs = [r for r in ranked if r.is_overseas]
        return overseas_jobs[:limit]
