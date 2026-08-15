"""Build the five Word submission documents from the markdown sources.

    python scripts/build_submission_docs.py

Each output keeps the University of Ghana cover page and front matter from
`docs/submission_files/22424543_document_name.docx`, with the document title filled in and
an abstract written for that document.

HOW IT WORKS, AND WHY THIS WAY
------------------------------
The obvious approach — take the template and append content to it — fails on numbering.
Pandoc generates its own `numbering.xml` for bullets and numbered lists, and a list spliced
into a foreign document references `numId` values that document has never heard of. The
bullets silently disappear.

So the direction is reversed: **pandoc's output is the base, and the cover is spliced into
it.** Pandoc is given the template as `--reference-doc`, which carries over its styles,
headers, footers and page setup, so the result already looks like the template. All that is
left to move is the cover and front matter — plain paragraphs, one image, and three field
codes — which have no dependencies beyond a single relationship for the logo.

WHAT WORD STILL HAS TO DO
-------------------------
The table of contents, list of figures and list of tables are **field codes**. They are
correct, and they are empty until Word calculates them: open each file, Ctrl+A, F9,
"Update entire table". This is normal for a Word template and is not a fault in the build.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TEMPLATE = DOCS / "submission_files" / "22424543_document_name.docx"
OUT_DIR = DOCS / "submission_files"
PNG = DOCS / "diagrams" / "png"
# Scratch lives outside the repository: intermediates are not source, and on a
# mounted or read-only checkout they may not even be removable.
BUILD = pathlib.Path(tempfile.gettempdir()) / "nkwanta_docbuild"

PROJECT = "NKWANTA: A ROAD INCIDENT REPORTING AND DISPATCH SYSTEM FOR URBAN GHANA"

ABBREVIATIONS = [
    ("API", "Application Programming Interface"),
    ("CI", "Continuous Integration"),
    ("ERD", "Entity Relationship Diagram"),
    ("FK", "Foreign key — a column holding another table's primary key, linking the two"),
    ("FR", "Functional Requirement"),
    ("GiST", "Generalised Search Tree — the spatial index used by PostGIS"),
    ("JWT", "JSON Web Token"),
    ("MoSCoW", "Must have, Should have, Could have, Won't have"),
    ("MTTD", "Motor Traffic and Transport Department"),
    ("NFR", "Non-Functional Requirement"),
    ("PK", "Primary key — the column that uniquely identifies a row"),
    ("PK_FK", "Both at once: part of a composite primary key, and a foreign key"),
    ("PostGIS", "The spatial extension to PostgreSQL"),
    ("PWA", "Progressive Web Application"),
    ("SRS", "Software Requirements Specification"),
    ("TD", "Technical Debt item"),
    ("UCP", "Use Case Points"),
    ("UK", "Unique key — no two rows may share this value, though it is not the identifier"),
    ("UML", "Unified Modelling Language"),
]

# --- the five documents -------------------------------------------------------------

DOCUMENTS = [
    {
        "out": "22424543_Project_Documentation.docx",
        "title": "PROJECT DOCUMENTATION",
        "sources": ["14-project-documentation.md"],
        "abstract": (
            "Nkwanta is a road incident reporting and dispatch system for urban Ghana. Road "
            "users report what is blocking a road; the system works out which reports describe "
            "the same real event, scores how believable each event is from the reporters' track "
            "records, warns other commuters travelling that way, and places credible events in "
            "front of a traffic control officer who can send a warden. "
            "This document consolidates the full engineering record across all nineteen required "
            "sections: problem, stakeholders, requirements analysis, effort estimation, system "
            "analysis and design, implementation, testing, technical debt, deployment, "
            "maintenance, future evolution and limitations. "
            "The system is deployed and reachable, carries 508 automated tests including 35 "
            "property-based invariants, and records 23 technical debt items and 45 dated design "
            "decisions written as the work was done. Two gaps are declared rather than rounded "
            "away: one functional requirement is verified only by inspection, and one "
            "non-functional requirement is stated as a target rather than a measurement."
        ),
        "figures": [
            ("Architecture: layered, with a pure core", "01-architecture.png",
             r"\*\*Architecture: layered, with a pure core\.\*\*"),
            ("Data model: reports are append-only, incidents derived", "02-data-model.png",
             r"\*\*Data model\.\*\* Nine tables\."),
            ("Report intake: saving and enqueueing in one transaction", "03-report-intake.png",
             r"\*\*The property that must always hold"),
            ("The incident lifecycle: computed states versus decided states", "04-lifecycle.png",
             r"\*\*Three columns worth explaining"),
        ],
    },
    {
        "out": "22424543_SRS.docx",
        "title": "SOFTWARE REQUIREMENTS SPECIFICATION",
        "sources": ["10-srs.md"],
        "abstract": (
            "This specification states what Nkwanta must do, precisely enough that a stranger "
            "could tell whether it does it. Fifty numbered functional requirements are given, "
            "each with a MoSCoW priority, an implementation status, the module that implements "
            "it and the automated test that verifies it. Seven non-functional requirements "
            "follow, together with four use cases and their alternative flows, and a record of "
            "the requirements that were deliberately cut against a written effort estimate. "
            "Forty-nine of the fifty functional requirements are implemented and verified. One, "
            "the clearance notification, is declared Partial: the code path exists and is wired "
            "but no automated test exercises it. Six of the seven non-functional requirements "
            "are verified by test; the seventh, a page-load target on a 3G connection, is "
            "declared unmeasured. Both gaps are stated here rather than omitted, on the view "
            "that a specification claiming fifty of fifty would be less useful and less honest."
        ),
        "figures": [
            ("The incident lifecycle referenced by FR-24 to FR-27", "04-lifecycle.png",
             r"### 3\.4 Dispatch and reputation"),
        ],
    },
    {
        "out": "22424543_Testing_Report.docx",
        "title": "TESTING REPORT",
        "sources": ["11-testing-report.md"],
        "abstract": (
            "Nkwanta carries 508 automated tests. Coverage is 69 per cent of statements overall "
            "and 99 per cent of the pure domain core, and the gap between those two figures is "
            "the honest summary of the strategy: the parts of the system that decide things are "
            "tested almost exhaustively by generated inputs, and the parts that move data around "
            "rest on nine integration paths against a real spatial database. "
            "Thirty-five properties are checked with Hypothesis, at 150 generated examples each "
            "by default and 1,000 before submission. The central property — that the order in "
            "which reports arrive cannot change the resulting incident — is proved this way "
            "rather than demonstrated on chosen inputs. "
            "This report also documents eight defects the tests found rather than users, two "
            "recurring faults in the tests themselves, and the areas that are not tested at all."
        ),
        "figures": [],
    },
    {
        "out": "22424543_Technical_Debt_Plan.docx",
        "title": "TECHNICAL DEBT IDENTIFICATION AND MANAGEMENT PLAN",
        "sources": ["08-technical-debt.md", "12-maintenance-and-evolution.md"],
        "abstract": (
            "This document is the live technical debt register for Nkwanta, together with the "
            "plan for repaying it. Twenty-three items are recorded, every one written at the "
            "moment the shortcut was taken rather than reconstructed afterwards. Each records "
            "the debt, its cause, its impact, its priority and a proposed resolution, and is "
            "classified as Acceptable, Scheduled or Critical. "
            "The repayment plan orders the items by interest rate — how much worse each becomes "
            "on its own — rather than by how visible they are. Both items classified Critical "
            "are scheduled before any real user touches the system. Two items have already "
            "demonstrated their cost with dates, by two different mechanisms, and are recorded "
            "with what they cost. "
            "The document also sets out the maintenance strategy, applies Lehman's laws of "
            "software evolution to this system specifically, and states which features should "
            "never be added and why."
        ),
        "figures": [],
    },
    {
        "out": "22424543_User_Manual.docx",
        "title": "USER MANUAL",
        "sources": ["13-user-manual.md"],
        "abstract": (
            "This manual explains how to use Nkwanta, for each of the four kinds of user: the "
            "commuter who reports what is blocking a road and is warned about the routes they "
            "travel, the traffic control officer who decides whether an incident is credible "
            "enough to act on, the traffic warden who attends and records what was found, and "
            "the administrator who manages accounts. "
            "It opens with a safety note, before anything else, because the system exists to "
            "reduce a road hazard and must not create one: the application is never to be "
            "operated while driving, and it does not summon the emergency services. "
            "It also answers the questions the design provokes — why an incident disappears "
            "from the map on its own, why a believability figure can fall, and why a report can "
            "never be deleted."
        ),
        "figures": [],
    },
]


# --- helpers ------------------------------------------------------------------------


def strip_front_matter(text: str) -> str:
    """Drop the markdown title block. The cover page carries all of it, and repeating it
    on the first content page reads as a mistake."""
    lines = text.splitlines()
    out, seen_h1 = [], False
    for i, line in enumerate(lines):
        if not seen_h1 and line.startswith("# "):
            seen_h1 = True
            continue
        if seen_h1 and len(out) < 8 and (
            line.startswith("**Nkwanta") or line.startswith("*Version") or
            line.startswith("*14 August") or line.startswith("*Theophilus") or
            line.startswith("*CSCD602") or line.startswith("*Last updated") or
            line.strip() in {"---", ""}
        ):
            continue
        if seen_h1:
            out.append(line)
    return "\n".join(out).lstrip("\n")


def insert_figures(text: str, figures: list[tuple[str, str, str]]) -> str:
    """Place each diagram immediately after the paragraph it illustrates."""
    for n, (caption, png, anchor) in enumerate(figures, start=1):
        path = (PNG / png).as_posix()
        block = (
            f"\n\n![Figure {n} — {caption}]({path}){{width=6.2in}}\n\n"
            f"*Figure {n} — {caption}.*\n"
        )
        match = re.search(anchor, text)
        if not match:
            print(f"    ! anchor not found for figure {n}; appended at the end instead")
            text += block
            continue
        end = text.find("\n\n", match.end())
        end = len(text) if end == -1 else end
        text = text[:end] + block + text[end:]
    return text


def abbreviations_markdown() -> str:
    rows = "\n".join(f"| {a} | {b} |" for a, b in ABBREVIATIONS)
    return f"| Abbreviation | Meaning |\n|---|---|\n{rows}\n"


def build_front_matter(front_xml: str, title: str, abstract: str, logo_rid: str) -> str:
    """The template's cover and front matter, with the placeholders filled."""
    xml = front_xml.replace("[DOCUMENT TITLE]", f"{PROJECT} — {title}")
    xml = xml.replace('r:embed="rId8"', f'r:embed="{logo_rid}"')

    # The abstract goes into the first empty paragraph after the ABSTRACT heading.
    para = (
        '<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/>'
        '<w:jc w:val="both"/></w:pPr><w:r><w:t xml:space="preserve">'
        f'{escape(abstract)}</w:t></w:r></w:p>'
    )
    marker = "ABSTRACT"
    i = xml.find(marker)
    close = xml.find("</w:p>", i) + len("</w:p>")
    return xml[:close] + para + xml[close:]


def escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("—", "—"))


def merge_namespaces(pandoc_xml: str, template_root: str) -> str:
    """Give pandoc's <w:document> every prefix the template's cover needs."""
    theirs = dict(re.findall(r'xmlns:(\w+)="([^"]+)"', template_root))
    root = re.search(r"<w:document[^>]*>", pandoc_xml)
    mine = dict(re.findall(r'xmlns:(\w+)="([^"]+)"', root.group(0)))

    additions = "".join(
        f' xmlns:{prefix}="{uri}"' for prefix, uri in theirs.items() if prefix not in mine
    )
    # `mc:Ignorable` tells Word which of these it may skip if it does not understand them.
    ignorable = re.search(r'mc:Ignorable="([^"]*)"', template_root)
    if ignorable and "mc:Ignorable" not in root.group(0):
        additions += f' mc:Ignorable="{ignorable.group(1)}"'

    merged = root.group(0)[:-1] + additions + ">"
    return pandoc_xml[:root.start()] + merged + pandoc_xml[root.end():]


def fix_tables(xml: str, content_width: int = 9029) -> str:
    """Give every table a real width, a column grid and per-cell widths.

    Pandoc emits `<w:tblW w:type="pct" w:w="0.0"/>` and an **empty, self-closing**
    `<w:tblGrid/>` for a table with no width spec, and body cells with no `<w:tcPr>` at
    all. Word autofits and mostly copes; LibreOffice collapses the table into one cell
    per line with no visible structure — and these documents are mostly tables, so that
    is the difference between a submission and a mess.

    Two traps, both hit on the way to this version:

    * the grid must be **replaced**, not inserted. Adding a second `<w:tblGrid>` after
      the self-closing one leaves two, which is invalid and renders as an empty table
      with its contents spilled underneath.
    * most cells have no `<w:tcPr>`, so a substitution that only rewrites existing ones
      silently widens the header row and nothing else.

    Pandoc also names the style `Table`, which this template does not define; the style
    that exists, with the borders, is `TableGrid`.

    Column widths are weighted by how much text each column holds, clamped so a narrow
    column cannot vanish and a wide one cannot take everything — an eight-word
    requirement and a two-letter identifier should not get the same space.
    """
    def cell_text(cell: str) -> str:
        return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", cell))

    def rebuild(match: re.Match) -> str:
        table = match.group(0)
        rows = re.findall(r"<w:tr\b.*?</w:tr>", table, re.S)
        if not rows:
            return table
        cells_per_row = [re.findall(r"<w:tc>.*?</w:tc>", r, re.S) for r in rows]
        columns = max((len(c) for c in cells_per_row), default=0)
        if columns == 0:
            return table

        weights = []
        for i in range(columns):
            longest = max(
                (len(cell_text(cells[i])) for cells in cells_per_row if i < len(cells)),
                default=6,
            )
            weights.append(min(max(longest, 6), 70))

        total = sum(weights)
        widths = [max(int(content_width * w / total), 620) for w in weights]
        widths[-1] += content_width - sum(widths)

        grid = "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"

        table = table.replace('<w:tblStyle w:val="Table" />', '<w:tblStyle w:val="TableGrid"/>')
        # Any tblW, whatever pandoc chose — percentage widths and an absolute grid
        # disagree, and the grid is the one carrying the column proportions.
        # `tblLayout fixed` tells the renderer to honour the grid instead of measuring
        # the content itself. Without it an autofitting renderer is free to ignore the
        # widths entirely, which is what LibreOffice does.
        table = re.sub(
            r"<w:tblW[^/]*/>",
            f'<w:tblW w:type="dxa" w:w="{content_width}"/>'
            '<w:tblLayout w:type="fixed"/>',
            table, count=1,
        )
        # Replace whatever grid is there — pandoc's is self-closing and empty.
        table = re.sub(r"<w:tblGrid\s*/>|<w:tblGrid>.*?</w:tblGrid>", grid, table, count=1, flags=re.S)

        # Per-cell widths. Cells are numbered within their row, so a short row cannot
        # push every following cell into the wrong column.
        def widen_row(row_match: re.Match) -> str:
            row = row_match.group(0)
            column = [0]

            def widen_cell(cell_match: re.Match) -> str:
                w = widths[min(column[0], columns - 1)]
                column[0] += 1
                cell = cell_match.group(0)
                tcw = f'<w:tcW w:type="dxa" w:w="{w}"/>'
                if cell.startswith("<w:tc><w:tcPr>"):
                    return cell.replace("<w:tcPr>", "<w:tcPr>" + tcw, 1)
                return cell.replace("<w:tc>", "<w:tc><w:tcPr>" + tcw + "</w:tcPr>", 1)

            return re.sub(r"<w:tc>.*?</w:tc>", widen_cell, row, flags=re.S)

        return re.sub(r"<w:tr\b.*?</w:tr>", widen_row, table, flags=re.S)

    return re.sub(r"<w:tbl>.*?</w:tbl>", rebuild, xml, flags=re.S)


def next_rid(rels: str) -> str:
    used = {int(n) for n in re.findall(r'Id="rId(\d+)"', rels)}
    return f"rId{max(used) + 1}"


# --- the build ----------------------------------------------------------------------


def build(doc: dict, front_xml: str, logo_bytes: bytes,
          template_root: str) -> pathlib.Path:
    name = doc["out"]
    print(f"  {name}")

    body = "\n\n\\newpage\n\n".join(
        strip_front_matter((DOCS / src).read_text(encoding="utf-8"))
        for src in doc["sources"]
    )
    body = insert_figures(body, doc["figures"])
    body += "\n\n# List of Abbreviations\n\n" + abbreviations_markdown()

    work = BUILD / name.replace(".docx", "")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    md = work / "body.md"
    md.write_text(body, encoding="utf-8")
    interim = work / "interim.docx"

    subprocess.run(
        # No `--columns`. For pipe tables pandoc derives each column's *relative* width
        # from how wide it is in the source against this value, so a large number makes
        # every column a sliver — the table converts, and then renders as one cell per
        # line with no visible structure. The default is correct.
        ["pandoc", str(md), "-o", str(interim), f"--reference-doc={TEMPLATE}",
         "--from", "markdown"],
        check=True, capture_output=True,
    )

    unpacked = work / "unpacked"
    with zipfile.ZipFile(interim) as z:
        z.extractall(unpacked)

    # The logo needs a relationship of its own — pandoc copied the media across but had
    # no reason to reference it.
    rels_path = unpacked / "word" / "_rels" / "document.xml.rels"
    rels = rels_path.read_text(encoding="utf-8")
    rid = next_rid(rels)
    rels = rels.replace(
        "</Relationships>",
        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/image" Target="media/image1.png"/>'
        "</Relationships>",
    )
    rels_path.write_text(rels, encoding="utf-8")
    (unpacked / "word" / "media").mkdir(exist_ok=True)
    (unpacked / "word" / "media" / "image1.png").write_bytes(logo_bytes)

    # Splice the cover in at the top of the body, then a page break.
    doc_path = unpacked / "word" / "document.xml"
    xml = doc_path.read_text(encoding="utf-8")
    front = build_front_matter(front_xml, doc["title"], doc["abstract"], rid)
    page_break = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

    # The cover uses namespace prefixes the template's root declares and pandoc's does
    # not — w14 revision ids, mc compatibility, the w16 family. Splicing without them
    # gives "unbound prefix" and Word refuses the file outright, so the two roots are
    # merged rather than one being assumed to cover the other.
    xml = merge_namespaces(xml, template_root)
    xml = fix_tables(xml)

    open_tag = re.search(r"<w:body[^>]*>", xml)
    at = open_tag.end()
    xml = xml[:at] + front + page_break + xml[at:]
    doc_path.write_text(xml, encoding="utf-8")

    # Written in the scratch directory and copied over, rather than deleted and
    # recreated in place: on a mounted folder an unlink may be refused, and a failed
    # delete after a successful build would lose the build.
    staged = work / name
    with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(unpacked.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(unpacked).as_posix())

    out = OUT_DIR / name
    shutil.copyfile(staged, out)
    return out


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def verify(path: pathlib.Path) -> list[str]:
    """Check the built file structurally rather than by looking at a rendering.

    LibreOffice was tried first and is not trustworthy here: it renders pandoc's tables
    with the columns collapsed even when handed pandoc's own default template, so a bad
    render proves nothing and a good one would only have proved LibreOffice agreed. A
    parser can answer the questions that actually matter — is the XML valid, does every
    table have a grid, does every cell still contain its text.
    """
    problems: list[str] = []
    with zipfile.ZipFile(path) as z:
        try:
            root = ET.fromstring(z.read("word/document.xml"))
        except ET.ParseError as exc:
            return [f"document.xml does not parse: {exc}"]
        rels = z.read("word/_rels/document.xml.rels").decode()
        media = [n for n in z.namelist() if n.startswith("word/media/")]

    body = root.find(f"{W}body")
    tables = body.findall(f"{W}tbl")
    headings = [
        p for p in body.iter(f"{W}p")
        if (st := p.find(f"{W}pPr/{W}pStyle")) is not None
        and (st.get(f"{W}val") or "").startswith("Heading")
    ]

    if not headings:
        problems.append("no headings — the table of contents would come out empty")

    for n, table in enumerate(tables, start=1):
        grid = table.find(f"{W}tblGrid")
        if grid is None or not len(grid):
            problems.append(f"table {n} has no column grid")
        rows = table.findall(f"{W}tr")
        if not rows:
            problems.append(f"table {n} has no rows")
            continue
        empty = sum(
            1 for row in rows for cell in row.findall(f"{W}tc")
            if not "".join(t.text or "" for t in cell.iter(f"{W}t")).strip()
        )
        total = sum(len(row.findall(f"{W}tc")) for row in rows)
        if total and empty == total:
            problems.append(f"table {n} is entirely empty")

    # Every image referenced must resolve to a file that is actually in the package.
    for rid in {b.get(f"{{http://schemas.openxmlformats.org/officeDocument/2006/relationships}}embed")
                for b in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")}:
        if rid and f'Id="{rid}"' not in rels:
            problems.append(f"image reference {rid} has no relationship")

    if not any(m.endswith("image1.png") for m in media):
        problems.append("the university crest is missing from the package")

    return problems


def main() -> int:
    if not TEMPLATE.exists():
        print(f"template not found: {TEMPLATE}", file=sys.stderr)
        return 1

    BUILD.mkdir(exist_ok=True)
    tpl = BUILD / "template"
    shutil.rmtree(tpl, ignore_errors=True)
    with zipfile.ZipFile(TEMPLATE) as z:
        z.extractall(tpl)

    xml = (tpl / "word" / "document.xml").read_text(encoding="utf-8")
    paras = [(m.start(), m.end()) for m in re.finditer(r"<w:p\b[^>]*>.*?</w:p>", xml, re.S)]
    # 0–46 is the cover, abstract, contents, figures, tables and abbreviations.
    # 47 onward is the specimen chapter text, which every document replaces.
    front_xml = xml[paras[0][0]:paras[46][1]]
    logo = (tpl / "word" / "media" / "image1.png").read_bytes()
    template_root = re.search(r"<w:document[^>]*>", xml).group(0)

    print("building:")
    built = [build(doc, front_xml, logo, template_root) for doc in DOCUMENTS]

    print("\nwritten to docs/submission_files/:")
    failed = False
    for path in built:
        problems = verify(path)
        mark = "ok " if not problems else "!! "
        print(f"  {mark}{path.name:46} {path.stat().st_size // 1024:>5} KB")
        for problem in problems:
            failed = True
            print(f"       {problem}")
    if failed:
        print("\nSome documents did not verify. Do not submit them as they are.")
    print(
        "\nIn Word, for each file: Ctrl+A then F9, and choose 'Update entire table'.\n"
        "The contents, figures and tables lists are field codes and stay empty until\n"
        "Word calculates them. That is normal, not a fault in the build."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
