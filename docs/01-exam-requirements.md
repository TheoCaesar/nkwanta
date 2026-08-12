# Exam Requirements — What Is Actually Being Marked

*Last updated: 12 August 2026*
*Source: CSCD602 Advanced Software Engineering, Individual Project-Based Examination,
University of Ghana. Examiner: Prof. Solomon Mensah.*

---

## 1. The task in one paragraph

Within 48 hours, identify a software problem of your choice and build a **working,
deployed** application using a proper software engineering lifecycle. The submission must
demonstrate requirements engineering, effort estimation, analysis, design, implementation,
testing, deployment, documentation, maintenance and future evolution. The paper singles out
two areas for **particular attention**: software effort estimation, and the identification,
prioritisation and management of technical debt.

The paper states explicitly that a large commercial system is not expected.

---

## 2. The mark scheme — read this before deciding anything

Reordered by weight. The paper lists them in lifecycle order.

| Component | Marks | Share |
|---|---:|---:|
| Implementation & Functionality | 10 | 21% |
| Requirements Engineering & SRS | 7 | 15% |
| **Technical Debt Identification & Management** | 6 | 12.5% |
| System Analysis & Design | 6 | 12.5% |
| Software Effort Estimation | 5 | 10% |
| Testing & Quality Assurance | 5 | 10% |
| Deployment & Accessibility | 3 | 6% |
| Documentation & User Manual | 3 | 6% |
| Maintenance & Future Evolution | 3 | 6% |
| **Sum of listed components** | **48** | |
| **Stated total on the paper** | **50** | |

> ### ⚠ Discrepancy in the paper
>
> The nine components listed in Part E sum to **48**, but the paper states the total as
> **50**. The marks above are transcribed exactly as printed — the arithmetic error is in
> the source document, not this transcription.
>
> Two marks are therefore unaccounted for. This is almost certainly a typographical slip
> rather than a hidden component. It changes nothing about strategy — the *relative*
> weighting is what matters, and that is unambiguous. Shares above are calculated against
> the 48 listed.
>
> Worth a polite email to the examiner if the opportunity arises. Not worth worrying about.

### What this table is telling you

**Building the app is worth 10 marks. Everything around it is worth 40.**

This single fact should drive every decision on this project. A modest application with
excellent requirements, a defensible estimate, a genuine debt register and real tests will
comfortably beat an ambitious application with thin paperwork. Most candidates will get
this backwards and spend 40 of their 48 hours coding.

Two further observations:

- **Technical debt at 6 marks outweighs design at 6 and beats testing at 5.** It is
  unusual for it to be weighted this heavily. It must be recorded continuously during the
  build, not reconstructed on the final evening.
- **Effort estimation at 5 marks must visibly influence scope.** The paper explicitly asks
  how the estimation shaped the project. An estimate that did not change anything is an
  estimate that was performed for show.

---

## 3. The closing principle, quoted

The paper ends with this, and it is effectively the marking philosophy:

> "You are not being assessed simply on whether you can produce a working application in
> 48 hours. You are being assessed on whether you can demonstrate disciplined Advanced
> Software Engineering practice under a realistic time constraint."

---

## 4. What must be produced

### Before writing any code

The paper is explicit: **do not begin implementation immediately.** First define the
problem, identify stakeholders, gather and analyse requirements, separate functional from
non-functional, prioritise, estimate effort, and set the 48-hour scope.

### Effort estimation

Choose one technique and justify it — Function Point Analysis, Use Case Points, COCOMO or
COCOMO II, story points, or expert estimation. State the estimated effort, person-hours,
duration, assumptions, constraints, and **how the estimate influenced scope**.

### Design

Produce the diagrams that best communicate the system. Not every diagram is required. Any
of: architecture, use case, class, sequence, activity, ER, component, wireframes, data flow.

### Implementation

Must be a functional application — not a proposal, not a mock-up, not a static site.
Where applicable include front-end, back-end, database, authentication, authorisation, API
integration, input validation, error handling, security controls and a responsive interface.

### Technical debt

Document debt arising from time pressure, design shortcuts, simplified architecture,
incomplete refactoring, temporary solutions, limited testing, duplication, dependency
choices, security compromises and incomplete documentation.

Each item recorded as: **Debt → Cause → Impact → Priority → Proposed Resolution**

And classified as one of:

- acceptable temporarily
- scheduled for future resolution
- critical, requiring immediate attention

### Testing

Evidence of functional, unit, integration, system and user acceptance testing. Where
appropriate also security, usability and performance. Each documented with test case,
expected result, actual result, pass/fail, defects found and corrective action.

### Deployment

Must be live and reachable online. Vercel, Netlify, Render, GitHub Pages or another
suitable host. Must supply live URL, admin URL, test credentials, admin credentials and the
source repository. The deployment must **remain accessible** for grading.

### Documentation

One consolidated document covering all nineteen required sections: title, problem
statement, aim and objectives, stakeholders, requirements analysis, SRS, effort estimation,
system analysis, system design, implementation, testing, technical debt, deployment, user
manual, maintenance strategy, future evolution, limitations, conclusion, references.

---

## 5. Submission package

One ZIP through Sakai LMS:

```
StudentID_ProjectName/
├── Project_Documentation.pdf
├── SRS.pdf
├── Testing_Report.pdf
├── Technical_Debt_Plan.pdf
├── User_Manual.pdf
├── Deployment_and_Source_Links.txt
└── Supporting_Files/
```

These may be combined into one comprehensive PDF provided all sections are clearly
identified.

`Deployment_and_Source_Links.txt` must contain: student name, student ID, project title,
live application URL, admin URL, test username and password, admin username and password,
and the source code repository.

---

## 6. The viva

Rule 10 of the paper: the examiner **may conduct an individual viva voce or demo** to
verify authorship, understanding and implementation. Rule 11: you may be asked to explain
requirements, effort estimation, architecture, implementation decisions, testing strategy
and technical debt.

**Practical consequence:** never include anything you cannot explain from first principles.
A clever feature you cannot account for is worse than a simple one you can. This is a
further argument for a small, deeply understood system.

Every external library, framework, API, dataset and third-party component must be
acknowledged (Rule 6).

---

## 7. Suggested phase plan from the paper

Described as a recommendation, not a mandatory timetable.

| Phase | Hours | Work |
|---|---|---|
| 1 — Planning & Requirements | 1–6 | Select project, define problem, stakeholders, requirements, SRS, prioritisation, effort estimation, scope |
| 2 — Analysis & Design | 7–12 | Architecture, UML, database, interfaces, stack, identify likely debt |
| 3 — Implementation | 13–32 | Core functionality, database, UI, backend, integrations, auth, continuous testing |
| 4 — Testing & Refinement | 33–38 | Execute tests, fix critical defects, usability, security review, document debt, refactor |
| 5 — Deployment | 39–42 | Deploy, verify production, test live, prepare credentials, verify repository |
| 6 — Documentation | 43–48 | Complete all documents, user manual, testing report, debt plan, evolution plan, package, submit |

Note that implementation gets 20 of the 48 hours, and 12 hours come **before** any code is
written. Following this plan is itself evidence of the discipline being assessed.

---

## 8. Final checklist from the paper

- [ ] Defined a realistic software problem
- [ ] Identified stakeholders and users
- [ ] Completed requirements analysis
- [ ] Developed an SRS
- [ ] Estimated software effort
- [ ] Justified the estimation technique
- [ ] Designed the system
- [ ] Implemented a functional application
- [ ] Tested the application
- [ ] Documented test results
- [ ] Identified technical debt
- [ ] Proposed technical debt resolution strategies
- [ ] Deployed the application
- [ ] Tested the live deployment
- [ ] Prepared a user manual
- [ ] Prepared a maintenance strategy
- [ ] Prepared a future evolution plan
- [ ] Provided the source code repository
- [ ] Verified all URLs and credentials
- [ ] Included name, student ID and project title
- [ ] Submitted all required files through Sakai
