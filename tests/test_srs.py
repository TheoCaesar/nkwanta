"""The specification has to be true.

An SRS is worth 7 marks and is read *instead of* the code. Its characteristic failure is
not being wrong about the design — it is claiming a requirement is implemented when the
module named beside it does not exist, or when the test named beside it was renamed six
commits ago. Those claims cost more than an omission, because they are confident.

So every row of the traceability tables is checked against the filesystem: the module
exists, the test file exists, the identifiers are unique and unbroken. What cannot be
checked here — whether the requirement is a *good* requirement — is the examiner's job.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SRS = (DOCS / "10-srs.md").read_text(encoding="utf-8")

# Rows of the traceability tables: | FR-nn | text | priority | status | impl | test |
ROWS = re.findall(r"^\| (FR-\d{2}) \|(.+)$", SRS, re.M)


def test_the_specification_exists_and_has_requirements() -> None:
    assert len(ROWS) >= 40, "too few requirements to be a specification of this system"


def test_requirement_numbers_are_unique_and_unbroken() -> None:
    """A gap in the numbering means a requirement was deleted rather than superseded, and
    a duplicate means two things answer to one name in the traceability table."""
    ids = [row[0] for row in ROWS]
    assert len(ids) == len(set(ids)), f"duplicated: {[i for i in ids if ids.count(i) > 1]}"

    numbers = sorted(int(i.split("-")[1]) for i in ids)
    assert numbers == list(range(1, len(numbers) + 1)), f"gap in FR numbering: {numbers}"


def test_every_requirement_has_a_priority_and_a_status() -> None:
    for rid, rest in ROWS:
        assert re.search(r"\| (Must|Should|Could|Won't) \|", rest), f"{rid} has no priority"
        assert re.search(r"\| (Implemented|Partial|Deferred|\*\*Partial\*\*) \|", rest), (
            f"{rid} has no status"
        )


def test_every_module_named_as_an_implementation_exists() -> None:
    """The claim that costs most when false."""
    named = set(re.findall(r"`((?:app/|routers/|services/|web/)[\w./]+\.(?:py|js))", SRS))
    named |= {f"app/{m}" for m in re.findall(r"`(\w+\.py)::", SRS)}
    assert len(named) >= 15, "the specification names almost no implementation"

    for path in sorted(named):
        candidates = [ROOT / path, ROOT / "app" / path, ROOT / "app" / "routers" / path]
        assert any(c.exists() for c in candidates), f"{path} is named but does not exist"


def test_every_test_file_named_as_verification_exists() -> None:
    here = pathlib.Path(__file__).resolve().parent
    named = set(re.findall(r"(test_\w+\.py)", SRS))
    assert len(named) >= 10, "the verification column names almost nothing"
    for name in sorted(named):
        assert (here / name).exists(), f"{name} is cited as verification and does not exist"


def test_the_partial_requirement_is_declared_rather_than_hidden() -> None:
    """FR-40, clearance. The code path exists and is wired; nothing tests it and no seeded
    incident demonstrates it.

    A specification claiming fifty of fifty would be a less useful document and a less
    honest one. If this ever becomes true, delete the test — but delete it deliberately.
    """
    assert "**Partial**" in SRS
    partial = [rid for rid, rest in ROWS if "Partial" in rest]
    assert partial == ["FR-40"], f"the declared partial set has changed: {partial}"

    row = next(rest for rid, rest in ROWS if rid == "FR-40")
    assert "no test calls it" in row.lower() or "*none*" in row.lower()


def test_the_unverified_non_functional_requirement_is_declared() -> None:
    """NFR-07 is a target, not a measurement. Nobody threw a 3G profile at it."""
    assert "NFR-07 is not verified" in SRS


def test_every_non_functional_requirement_carried_over_is_still_specified() -> None:
    """The SRS renumbered NFR-1 to NFR-01. Nothing may be lost in the renaming."""
    scope = (DOCS / "02-problem-and-scope.md").read_text(encoding="utf-8")
    original = {int(n) for n in re.findall(r"NFR-(\d)\b", scope)}
    carried = {int(n) for n in re.findall(r"NFR-0(\d)\b", SRS)}
    assert original <= carried, f"lost in renumbering: {sorted(original - carried)}"
    assert "NFR-04a" in SRS, "the requirement that protects the reporter was dropped"


def test_the_thresholds_it_quotes_match_the_code() -> None:
    from app.clustering import DEFAULT_RADIUS_METRES, DEFAULT_WINDOW_MINUTES
    from app.confidence import THRESHOLD_CORROBORATED, THRESHOLD_STALE, THRESHOLD_VERIFIED

    for value in (THRESHOLD_CORROBORATED, THRESHOLD_VERIFIED, THRESHOLD_STALE):
        assert f"{value:.2f}" in SRS, f"threshold {value} is misquoted or absent"
    assert f"{DEFAULT_RADIUS_METRES} m" in SRS
    assert f"{DEFAULT_WINDOW_MINUTES} minutes" in SRS


def test_the_totals_in_the_summary_match_the_tables() -> None:
    """A summary table that disagrees with the thing it summarises is the sort of error a
    reader finds and then stops trusting the rest of the document."""
    stated_total = int(re.search(r"\*\*Total\*\* \| \*\*(\d+)\*\*", SRS).group(1))
    assert stated_total == len(ROWS), f"summary says {stated_total}, tables hold {len(ROWS)}"

    implemented = sum(1 for _, rest in ROWS if "Partial" not in rest)
    stated_impl = int(re.search(r"\*\*Total\*\* \| \*\*\d+\*\* \| \*\*(\d+)\*\*", SRS).group(1))
    assert stated_impl == implemented


@pytest.mark.parametrize("doc", ["02-problem-and-scope.md", "05-decision-log.md",
                                 "06-effort-estimation.md", "08-technical-debt.md",
                                 "09-system-design.md", "04-advanced-concept.md"])
def test_every_document_it_references_exists(doc: str) -> None:
    assert doc in SRS, f"{doc} is no longer referenced"
    assert (DOCS / doc).exists(), f"{doc} is referenced and missing"


def test_every_decision_and_debt_item_it_cites_is_recorded() -> None:
    log = (DOCS / "05-decision-log.md").read_text(encoding="utf-8")
    debt = (DOCS / "08-technical-debt.md").read_text(encoding="utf-8")

    for number in sorted(set(re.findall(r"\bD-(\d{3})\b", SRS))):
        assert f"### D-{number}" in log, f"D-{number} is cited but not recorded"
    for number in sorted(set(re.findall(r"\bTD-(\d{2})\b", SRS))):
        assert f"TD-{number}" in debt, f"TD-{number} is cited but not registered"
