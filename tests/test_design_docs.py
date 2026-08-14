"""The design document has to agree with the code it describes.

`09-system-design.md` is worth 6 marks and is the document an examiner reads *instead of*
the code. A diagram naming a module that no longer exists is worse than no diagram: it is
a confident statement that happens to be false, and it is exactly the kind of rot that
sets in when documentation is written once and the code moves on.

So the names in it are checked against the filesystem and the models. This cannot verify
that a diagram is *well drawn* — only that everything it points at is real.

Mermaid syntax is validated separately, outside pytest, because it needs a JavaScript
parser. See the note in HANDOFF for 14 August.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.models import Base

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
DESIGN = (DOCS / "09-system-design.md").read_text(encoding="utf-8")
APP = pathlib.Path(__file__).resolve().parent.parent / "app"

MERMAID = re.findall(r"```mermaid\n([\s\S]*?)```", DESIGN)


def test_the_document_exists_and_carries_diagrams() -> None:
    """The paper names UML under Analysis and Design. Prose alone does not answer it."""
    assert len(MERMAID) >= 6, "a design document with no diagrams is a design essay"


def test_it_covers_the_kinds_of_diagram_the_paper_asks_for() -> None:
    kinds = {block.strip().split("\n")[0].split()[0] for block in MERMAID}
    assert "erDiagram" in kinds, "no data model"
    assert "sequenceDiagram" in kinds, "no behaviour over time"
    assert "stateDiagram-v2" in kinds, "no lifecycle"
    assert kinds & {"graph", "flowchart"}, "no structural view"


@pytest.mark.parametrize(
    "module",
    ["clustering", "confidence", "lifecycle", "reputation", "circuit_breaker",
     "worker", "gateway", "models"],
)
def test_every_module_the_diagrams_name_exists(module: str) -> None:
    """Named in the architecture diagram, so it had better be there."""
    assert f"{module}.py" in DESIGN, f"{module} is no longer described"
    assert (APP / f"{module}.py").exists(), f"the design names a module that is gone"


@pytest.mark.parametrize(
    "service",
    ["reports", "projection", "advisory", "dispatch", "attachments", "staleness"],
)
def test_every_service_the_diagrams_name_exists(service: str) -> None:
    assert (APP / "services" / f"{service}.py").exists()
    assert service in DESIGN


def test_every_table_in_the_er_diagram_is_a_real_table() -> None:
    """And, more usefully, the reverse — a table absent from the diagram is a part of the
    system the reader has not been told about."""
    er = next(b for b in MERMAID if b.strip().startswith("erDiagram"))
    drawn = set(re.findall(r"^\s{4}(\w+) \{", er, re.M))
    actual = set(Base.metadata.tables)

    assert not drawn - actual, f"the diagram invents tables: {drawn - actual}"
    assert not actual - drawn, f"tables missing from the data model: {actual - drawn}"


def test_the_thresholds_quoted_match_the_code() -> None:
    """0.35 and 0.70 decide whether commuters are warned and whether police are involved.
    A document quoting the wrong ones misleads on the thing that matters most."""
    from app.confidence import THRESHOLD_CORROBORATED, THRESHOLD_STALE, THRESHOLD_VERIFIED

    for value in (THRESHOLD_CORROBORATED, THRESHOLD_VERIFIED, THRESHOLD_STALE):
        assert f"{value:.2f}" in DESIGN, f"threshold {value} is not stated"


def test_the_clustering_constants_quoted_match_the_code() -> None:
    from app.clustering import DEFAULT_RADIUS_METRES, DEFAULT_WINDOW_MINUTES

    assert f"{DEFAULT_RADIUS_METRES} m" in DESIGN
    assert f"{DEFAULT_WINDOW_MINUTES} min" in DESIGN


def test_every_decision_it_cites_is_in_the_log() -> None:
    """A dangling D-number is a citation to nothing."""
    log = (DOCS / "05-decision-log.md").read_text(encoding="utf-8")
    cited = set(re.findall(r"\bD-(\d{3})\b", DESIGN))
    assert cited, "the design cites no decisions at all"
    for number in sorted(cited):
        assert f"### D-{number}" in log, f"D-{number} is cited but not recorded"


def test_every_debt_item_it_cites_is_in_the_register() -> None:
    debt = (DOCS / "08-technical-debt.md").read_text(encoding="utf-8")
    cited = set(re.findall(r"\bTD-(\d{2})\b", DESIGN))
    assert cited, "a design with no stated compromises is a design nobody believes"
    for number in sorted(cited):
        assert f"TD-{number}" in debt, f"TD-{number} is cited but not registered"


def test_every_test_file_it_points_at_exists() -> None:
    """The traceability table is only worth marks if the trace lands somewhere."""
    here = pathlib.Path(__file__).resolve().parent
    named = set(re.findall(r"(test_\w+\.py)", DESIGN))
    assert len(named) >= 6, "the traceability table names almost nothing"
    for name in sorted(named):
        assert (here / name).exists(), f"the design points at {name}, which does not exist"


def test_every_requirement_it_cites_is_in_the_scope_document() -> None:
    scope = (DOCS / "02-problem-and-scope.md").read_text(encoding="utf-8")
    for nfr in sorted(set(re.findall(r"\bNFR-\d\w?\b", DESIGN))):
        assert nfr in scope, f"{nfr} is cited but not specified"
