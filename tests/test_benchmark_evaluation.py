"""Test running the 60-job labeled semiconductor benchmark and asserting quality metrics."""

from tests.benchmark.evaluate_benchmark import run_benchmark_evaluation


def test_60_job_benchmark_quality_metrics():
    """Run benchmark evaluation and assert precision, zero fake applies, and high top-K accuracy."""
    metrics = run_benchmark_evaluation()

    assert metrics["total_jobs_evaluated"] == 60
    assert metrics["expected_apply_count"] == 25
    assert metrics["true_positives_apply"] == 25
    assert metrics["recall_apply"] == 1.0

    # Strong precision for target fresher DV roles (>= 80%)
    assert metrics["precision_apply"] >= 0.80
    assert metrics["false_positive_rate"] <= 0.15

    # 100% precision in Top-5 and Top-10 recommendations
    assert metrics["precision_at_5"] == 1.0
    assert metrics["precision_at_10"] == 1.0

    # Ensure no senior roles (8+ yrs), ITAR, or non-hardware jobs breached the false positive list
    fp_ids = [item["id"] for item in metrics["false_positive_items"]]
    for rejected_id in ["BM-29", "BM-30", "BM-31", "BM-32", "BM-33", "BM-34", "BM-35", "BM-36", "BM-37", "BM-38", "BM-39", "BM-40", "BM-41", "BM-42", "BM-43", "BM-44", "BM-45", "BM-46", "BM-47", "BM-48", "BM-49", "BM-50"]:
        assert rejected_id not in fp_ids
