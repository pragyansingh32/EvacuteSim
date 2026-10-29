"""The known-answer battery is a permanent regression gate: every case must
classify correctly, or the engine has drifted from documented behavior."""

from __future__ import annotations

from app.services.validation_service import run_battery


def test_battery_all_cases_classified_correctly():
    report = run_battery()
    misses = [c for c in report["cases"] if not c["passed"]]
    assert not misses, (
        "Known-answer battery regressed: "
        + "; ".join(f"{c['name']} -> {c['actual']}" for c in misses)
    )
    assert report["accuracy_pct"] == 100.0
    assert report["ran_cases"] >= 14


def test_battery_covers_all_categories():
    report = run_battery()
    categories = {c["category"] for c in report["cases"]}
    assert {"pass", "fail", "accuracy"} <= categories
    # Both directions must exist: designs that pass and designs that fail.
    assert any(c["category"] == "pass" and c["passed"] for c in report["cases"])
    assert any(c["category"] == "fail" for c in report["cases"])


def test_battery_fail_cases_actually_fail_in_engine():
    """The 'fail' category cases must produce non-evacuated outcomes."""
    report = run_battery()
    fail_cases = [c for c in report["cases"] if c["category"] == "fail" and c["passed"]]
    assert len(fail_cases) >= 4
    for case in fail_cases:
        evidence = case["evidence"]
        outcome = evidence.get("engine_status")
        # Honest failure modes: refused, incomplete, or unreachable detected.
        assert (
            outcome == "incomplete"
            or evidence.get("unreachable", 0) > 0
            or case["name"] == "Every exit blocked"
        ), case["name"]
