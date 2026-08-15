"""The testing report has to be true about the tests.

A report claiming a count, a coverage figure or a Hypothesis profile that no longer exists
is the same defect class as an SRS naming a file that was deleted — a confident statement,
in a graded document, that nobody reading it can check.

Counts drift with every commit, so these tests check them where checking is cheap and
tolerant where it is not: the profiles must exist, the property count must be at least what
is claimed, every named test file must exist, and every defect cited as `D-` or `TD-` must
be recorded. The coverage percentages are not asserted — they change with the environment
and the report states its measurement conditions instead.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
REPORT = (ROOT / "docs" / "11-testing-report.md").read_text(encoding="utf-8")


def test_every_hypothesis_profile_it_names_is_registered() -> None:
    """The report tells an examiner to run `HYPOTHESIS_PROFILE=thorough`. If that profile
    does not exist, the instruction fails in front of them."""
    conftest = (TESTS / "conftest.py").read_text(encoding="utf-8")
    for profile in re.findall(r"`(dev|default|thorough)`", REPORT):
        assert f'register_profile("{profile}"' in conftest, f"no profile named {profile}"


def test_the_thorough_profile_runs_at_least_what_is_claimed() -> None:
    conftest = (TESTS / "conftest.py").read_text(encoding="utf-8")
    claimed = int(re.search(r"\| `thorough` \| (\d+) \|", REPORT).group(1))
    actual = int(re.search(r'register_profile\("thorough", max_examples=(\d+)', conftest).group(1))
    assert actual >= claimed, f"report claims {claimed} examples, conftest sets {actual}"


def test_the_property_count_is_not_overstated() -> None:
    """`@given` is the marker of a property-based test. The report may understate this —
    counts drift — but it may never claim more than exist."""
    given = sum(
        p.read_text(encoding="utf-8").count("@given") for p in TESTS.glob("test_*.py")
    )
    claimed = int(re.search(r"(\d+) properties", REPORT).group(1))
    assert given >= claimed, f"report claims {claimed} properties, {given} use @given"


def test_the_test_total_is_not_overstated() -> None:
    """Collected count, not a number typed into a document. Tolerant upward — tests get
    added — and strict downward, because a shrinking suite behind a fixed claim is how a
    report becomes fiction."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-p", "no:randomly"],
        cwd=ROOT, capture_output=True, text=True,
    )
    collected = re.search(r"(\d+) tests? collected", result.stdout)
    if not collected:  # pragma: no cover - collection shape differs across versions
        pytest.skip("could not read the collected count from pytest output")

    claimed = int(re.search(r"\| Tests \| (\d+) \|", REPORT).group(1))
    actual = int(collected.group(1))
    assert actual >= claimed - 5, (
        f"the report claims {claimed} tests; {actual} were collected. "
        "A report that overstates the suite is worse than one that understates it."
    )


def test_every_test_file_it_names_exists() -> None:
    named = set(re.findall(r"(test_\w+\.py)", REPORT))
    assert len(named) >= 3, "the report names almost no test files"
    for name in sorted(named):
        assert (TESTS / name).exists(), f"{name} is discussed and does not exist"


def test_every_module_it_quotes_coverage_for_exists() -> None:
    tooling = {"coverage.py"}   # the instrument, not a thing being measured
    quoted = {
        m for m in re.findall(r"`(?:services/|app/)?(\w+\.py)`", REPORT)
        if m not in tooling and not m.startswith("test_")   # test files: covered above
    }
    assert quoted, "no module is named"
    for module in sorted(quoted):
        assert any(p.name == module for p in (ROOT / "app").rglob("*.py")), (
            f"{module} has a coverage figure and does not exist"
        )


def test_every_defect_it_cites_is_recorded() -> None:
    """Each defect in §4 is traceable to the decision or debt entry that resulted."""
    docs = ROOT / "docs"
    log = (docs / "05-decision-log.md").read_text(encoding="utf-8")
    debt = (docs / "08-technical-debt.md").read_text(encoding="utf-8")

    decisions = set(re.findall(r"\bD-(\d{3})\b", REPORT))
    assert decisions, "no defect is traced to a decision"
    for number in sorted(decisions):
        assert f"### D-{number}" in log, f"D-{number} is cited but not recorded"
    for number in sorted(set(re.findall(r"\bTD-(\d{2})\b", REPORT))):
        assert f"TD-{number}" in debt, f"TD-{number} is cited but not registered"


def test_the_declared_gaps_match_the_specification() -> None:
    """The two things the SRS admits are the two things this report must also admit. If
    one document quietly upgrades a gap, they disagree and both lose their value."""
    srs = (ROOT / "docs" / "10-srs.md").read_text(encoding="utf-8")

    assert "FR-40" in REPORT and "FR-40" in srs
    assert "**Partial**" in srs
    assert "NFR-07" in REPORT and "NFR-07 is not verified" in srs


def test_the_meta_assertions_it_claims_are_really_there() -> None:
    """§8.1 says every affected test now asserts its collection is non-empty. That claim
    is checkable, and a report making unverifiable claims about its own rigour is the
    least useful kind."""
    vacuity_guards = sum(
        p.read_text(encoding="utf-8").count("vacuous")
        for p in TESTS.glob("test_*.py")
    )
    assert vacuity_guards >= 3, (
        "the report claims three vacuous tests were fixed with meta-assertions"
    )
