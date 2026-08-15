# Diagrams — where each one goes

Four diagrams, hand-authored as standalone SVG so they survive conversion to PDF. Every
markdown document keeps its Mermaid code fences as well, because those render on GitHub for
anyone browsing the repository.

**Why only four.** Nine diagrams exist in `09-system-design.md` as Mermaid. Mermaid needs a
JavaScript renderer, which most markdown-to-PDF converters do not have, so a diagram left as
a code fence arrives in the PDF as raw text. Hand-authoring all nine was not worth the
effort against the marks at stake, so the four that carry the Analysis and Design section
were done and the other five were left. That is a scoping decision of the same kind as the
rest of this project, and it is recorded here rather than left for a reader to notice.

---

## Placement

| # | File | Insert into | Exactly where | Replaces |
|---|---|---|---|---|
| 1 | `01-architecture.svg` | `09-system-design.md` §2 *Architectural style* | Immediately after "**Layered, with a pure core.** Four layers, and one rule about which may call which." | The `graph TD` Mermaid block |
| 2 | `02-data-model.svg` | `09-system-design.md` §3 *The data model* | After the paragraph ending "…the history is the reports, not the map." | The `erDiagram` Mermaid block |
| 3 | `03-report-intake.svg` | `09-system-design.md` §4 *The critical path: a report arrives* | After "Read the two boxes marked **one transaction** — everything else follows from them." | The first `sequenceDiagram` block |
| 4 | `04-lifecycle.svg` | `09-system-design.md` §6 *The incident lifecycle* | After the paragraph ending "…does not quietly revert because confidence dipped." | The `stateDiagram-v2` block |

**Also use, in `14-project-documentation.md`:**

| # | Section | Where |
|---|---|---|
| 1 | §9 *System design* | After "**Architecture: layered, with a pure core.**" |
| 2 | §9 *System design* | After "**Data model.** Nine tables." |
| 3 | §8 *System analysis* | After the advanced-concept paragraph — it is the clearest statement of the concept |
| 4 | §9 *System design* | Optional. Include only if the section looks thin without it |

**Suggested captions**, if your converter numbers figures:

1. *Figure 1 — Layered architecture. The domain layer touches no database, clock or network.*
2. *Figure 2 — Data model. Reports are append-only; incidents are derived and rebuildable.*
3. *Figure 3 — Report intake. Saving and enqueueing occur in one transaction.*
4. *Figure 4 — Incident lifecycle. Computed states versus decided states.*

---

## Building the PDFs

Everything is markdown. Nothing here needs a build step you do not already have.

### The five submission files

| Output | Source |
|---|---|
| `SRS.pdf` | `docs/10-srs.md` |
| `Testing_Report.pdf` | `docs/11-testing-report.md` |
| `Technical_Debt_Plan.pdf` | `docs/08-technical-debt.md` + `docs/12-maintenance-and-evolution.md` §4 |
| `User_Manual.pdf` | `docs/13-user-manual.md` |
| `Project_Documentation.pdf` | `docs/14-project-documentation.md` |

`Deployment_and_Source_Links.txt` stays as text — the paper asks for it that way.

### Two ways that both work

**Pandoc**, if you have it:

```bash
pandoc docs/10-srs.md -o SRS.pdf --pdf-engine=weasyprint \
       -V mainfont="Segoe UI" --toc
```

Replace each Mermaid fence with `![](docs/diagrams/01-architecture.svg)` first — pandoc
embeds SVG through weasyprint without complaint.

**A browser**, which needs nothing installed and is the safer option under time pressure:
open the markdown in any previewer that renders it (VS Code's built-in preview, or
Typora), then Print → Save as PDF. SVGs referenced with `![](…)` render; Mermaid fences
will not, which is what the four files above are for.

### Cover pages

The paper wants the full project title on every cover. Each document already opens with
title, full project name, your name, student ID and course — so a converter that starts a
new page at the first `#` heading gives you a cover for free.

### Before you zip

```
22424543_Nkwanta/
├── Project_Documentation.pdf
├── SRS.pdf
├── Testing_Report.pdf
├── Technical_Debt_Plan.pdf
├── User_Manual.pdf
├── Deployment_and_Source_Links.txt
└── Supporting_Files/
    ├── ui-designs.html          (docs/design/)
    ├── 05-decision-log.md       (45 dated decisions)
    ├── 03-glossary.md
    ├── 04-advanced-concept.md
    ├── 06-effort-estimation.md
    ├── 09-system-design.md      (the Mermaid source, for the diagrams not exported)
    ├── 12-maintenance-and-evolution.md
    ├── diagrams/*.svg
    └── explainers/01–09
```

Open every PDF once before zipping. A file that failed to convert looks identical to one
that succeeded until somebody opens it.
