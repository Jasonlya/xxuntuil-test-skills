[简体中文](./README.md) | [English](./README.en.md)

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/hero-dark.svg">
    <img src="./assets/hero.svg" alt="C2D Case Writing — a testing skill for writing image-validation test cases for design-to-code" width="820">
  </picture>
</p>

<h1 align="center">xxuntuil-test-skills</h1>

<p align="center"><strong>Test engineering methods, output standards and mechanical gates — packaged for AI agents.</strong></p>

<p align="center">A collection of testing skills for AI agents.<br>One directory per skill; copy it into your host's skills folder and it works. No host code changes.</p>

<p align="center">
  <a href="https://github.com/Jasonlya/xxuntuil-test-skills/actions/workflows/check.yml"><img src="https://github.com/Jasonlya/xxuntuil-test-skills/actions/workflows/check.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="./skills/"><img src="https://img.shields.io/badge/skills-1-blue" alt="Skills"></a>
  <a href="./CHANGELOG.md"><img src="https://img.shields.io/badge/version-v0.1.0-blueviolet" alt="Version"></a>
  <img src="https://img.shields.io/badge/deps-0-brightgreen" alt="Zero dependencies">
  <img src="https://img.shields.io/badge/python-3.8%2B-3776AB" alt="Python 3.8+">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT"></a>
</p>

---

Currently one skill. It turns "how to write image-validation test cases" from a verbal expectation into an executable format: **every case carries a real, reachable image URL, plus a statement of why that image triggers the rule under test.** Backed by 47 scenario rules, 13 verified image fixtures, and two gates whose exit code is the verdict.

[Quick start](#quick-start) · [Skills](#skills) · [How it works](#how-it-works) · [What a case looks like](#what-a-case-looks-like) · [The two gates](#the-two-gates) · [Scenario matrix](#scenario-matrix-6-groups-47-rules) · [Compatibility](#compatibility-and-boundaries) · [Measured results](#measured-results)

## Quick start

### 1. Install

```bash
git clone git@github.com:Jasonlya/xxuntuil-test-skills.git
cd xxuntuil-test-skills
./install.sh                 # all skills → ~/.workbuddy/skills/
```

`install.sh` only copies files; it never touches host configuration. When overwriting an installed skill, the old directory is **renamed to `.bak.<timestamp>` rather than deleted**.

<details>
<summary><strong>Install one skill / install per project / upgrade</strong></summary>

```bash
./install.sh --list                            # list available skills
./install.sh c2d-case-writing                  # install one
./install.sh -d ~/proj/.workbuddy/skills       # project-scoped, shared through git
./install.sh --force c2d-case-writing          # overwrite an installed copy
```

`WORKBUDDY_SKILLS_DIR` replaces `-d`. **Upgrade**: `git pull`, then rerun the original command. **Uninstall**: delete the skill directory from your host; the repository always keeps the full set.

| Scope | Directory | Applies to |
|---|---|---|
| Personal | `~/.workbuddy/skills/` | Every project |
| Project | `<repo>/.workbuddy/skills/` | That repo only; travels with git |

</details>

### 2. Confirm the skill is actually loaded

Open a new session and ask: "write C2D image validation test cases". Success means you can see it read `SKILL.md` and `references/`.

**A directory on disk does not mean the skill triggers.** Triggering depends on the frontmatter `description`; loading depends on the directory name matching `name`. Both are silent-failure points that `scripts/check_repo.py` catches.

### 3. First run: template → edit → gates

```bash
SKILL=~/.workbuddy/skills/c2d-case-writing

cp $SKILL/assets/case-template.md 测试用例_C2D图片_markmap.md
# edit for your design file, then run both gates
python3 $SKILL/scripts/case_lint_c2d.py 测试用例_C2D图片_markmap.md
python3 $SKILL/scripts/check_image_links.py 测试用例_C2D图片_markmap.md \
  --out 图片素材核验_$(date +%Y%m%d).md
```

Ship only when both exit with 0. You can also skip the shell entirely and let the agent work from your design file — the skill walks the six stages itself.

## Skills

| Skill | What it does | Outputs | Version |
|---|---|---|---|
| [c2d-case-writing](./skills/c2d-case-writing/SKILL.md) | Writes image-validation test cases for design-to-code (C2D): a real image URL per case, a stated reason the image triggers the rule, plus scenario triage, clarification, delivery checks and two gates | Case markmap, machine-readable schema, link verification report | `v0.1.0` |

Planned: requirement modelling, test strategy, case review, API testing, flaky-test triage. (Nothing lands here until it is written and actually measured.)

### Why it exists

Image bugs rarely live in business logic. They live at the **edges of the asset and rendering pipeline**: fill modes, cropping, masks, alpha channels, scale factors, format fallback, load failure. Two problems recur:

1. **Prose cannot produce an executable case.** "Test cropping with a long image" tells the executor nothing about length, aspect ratio or format. Two people reach incomparable conclusions, and regression cannot reproduce it.
2. **The wrong image means you tested nothing.** Test FILL cropping with a 1:1 image in a 1:1 container and no cropping happens at all. The case "passes" while verifying nothing.

So every case pins down two things: **one specific image (a direct URL)**, and **why that image triggers the scenario**. Rules live in `references/image-rule-matrix.md`, URLs in `references/image-fixture-registry.md`, and pass/fail is decided by scripts.

## How it works

<p align="center">
  <img src="./assets/workflow.svg" alt="Six-stage workflow: intake, scenario triage, clarification, per-scenario writing, delivery checks, finalisation — with two gates at the bottom" width="760">
</p>

Four deliberate choices:

- **Artifacts on disk are the state.** Each stage writes a file, not a chat log. Interrupt and resume by handing the artifact directory back.
- **Stop and ask; never guess.** An unreadable fill mode, an undocumented size limit, an unknown signed-URL lifetime — these are clarification items, not case content. In unattended runs they become open items instead of invented answers.
- **Exclusions need reasons.** Every rule is included or excluded during triage; an unexplained exclusion counts as a gap.
- **What can be machine-checked gets scripted.** Red lines in prose get skipped by weaker models and cannot be independently reviewed. Hence gates.

## What a case looks like

````markdown
### TC-01-01 [P1] Cover image in FILL mode: a 3:1 image cropped into a 1.875:1 container
- Rule: IMG-FILL-03 | Trigger: imageFill mode = FILL and image aspect ratio ≠ container aspect ratio
- Preconditions: design file {link} page {page} / node {nodeId} (container 375×200); env {URL} account {account}
- Image under test: https://picsum.photos/id/1015/1200/400
  - Traits: jpeg | 1200×400 | 3:1 | 103KB | opaque
  - Why it triggers: 3:1 into 1.875:1 must crop top and bottom; the crop amount is measurable (~20px) and its position observable
- Steps:
  1. Open {design link}, confirm node {nodeId} uses FILL
  2. Run C2D generation, collect the HTML output
  3. Open the output at 1440×900, select the image element in DevTools
- Expected:
  - Output is an `<img>` whose `src` is the URL above, with `object-fit: cover`
  - Rendered at 375×200 (±1px), roughly 20px cropped top and bottom (±2px), no letterboxing, no stretching
  - Loads within 3s; a blank frame after that is a failure
````

Five sections (rule / preconditions / image under test / steps / expected) plus one mandatory field: **why the image triggers the rule**. Those two — image traits and the trigger rationale — are what separate this skill from ordinary cases; without them the gate blocks the case.

Expected results must be decidable. "Displays correctly", "looks right" and "no problem" are banned. State pixel dimensions, crop margins with tolerance, `object-fit` values, Content-Type, size ceilings, diff-pixel ratios, or load deadlines.

## The two gates

<p align="center">
  <img src="./assets/guard-demo.svg" alt="Real terminal output: template passes with zero errors; a deliberately broken sample is blocked with 11 errors and 4 warnings, exit code 1; link verification passes three and expects one failure" width="820">
</p>

| Gate | What it checks | Exit code |
|---|---|---|
| [`case_lint_c2d.py`](./skills/c2d-case-writing/scripts/case_lint_c2d.py) | 12 error classes (missing sections, no direct URL, placeholders, local paths, inline `data:`, missing trigger rationale, undecidable expectations, TC numbering mismatched to its module…) + 6 warning classes | 1 = errors present, blocks finalisation |
| [`check_image_links.py`](./skills/c2d-case-writing/scripts/check_image_links.py) | One GET per case: status code, `Content-Type` is `image/*`, size; follows redirects | 1 = unexpected failure |

**Broken links vs expected failures**: load-fallback scenarios *need* a 404, so the case declares `expect_status: 404` and a matching response is reported as `EXPECTED`. Omit the declaration and it is treated as a broken link.

Both scripts use only the standard library (`re`, `pathlib`, `urllib`), call no model, and are CI-friendly.

## Scenario matrix (6 groups, 47 rules)

Full table with the required image traits per rule: [`references/image-rule-matrix.md`](./skills/c2d-case-writing/references/image-rule-matrix.md).

| Group | Prefix | Rules | Covers | Image must be |
|---|---|:--:|---|---|
| A Design-side fill | `IMG-FILL` | 10 | FILL / FIT / STRETCH / TILE, nine-patch, blend modes | Aspect ratio **clearly different** from the container |
| B Crop, mask, geometry | `IMG-CROP` | 8 | Radii, circles, masks, rotation, flipping, custom crop | Directionally **legible** content or quadrant colour blocks |
| C Export and format | `IMG-EXP` | 10 | png/jpg/webp/svg, scale factors, extreme sizes, large payloads | Target format plus boundary dimensions |
| D Rendered code | `IMG-CODE` | 11 | `src`, `object-fit`, `alt`, `loading`, `srcset`, path encoding | Distinguishable original vs fallback |
| E Load failure | `IMG-FALL` | 5 | 404, non-image response, slow load, CORS, hotlink protection | Explicit `expect_status` |
| F Visual consistency | `IMG-VIS` | 3 | Diff-pixel ratio, colour tolerance, downscale sharpness | Fine texture, not flat colour |

The most common trap: **testing FILL with an image whose ratio matches the container can never produce a crop.** Every rule states its required image traits precisely to prevent this.

## Image fixture registry (13 verified URLs)

All are direct image URLs, no login, no hotlink protection. Full list: [`references/image-fixture-registry.md`](./skills/c2d-case-writing/references/image-fixture-registry.md).

| Slot | URL | Format | Size | Use |
|---|---|---|---|---|
| `FIX-1X1` | `https://picsum.photos/1/1` | jpeg | 1×1 | Minimum-size boundary |
| `FIX-3X1` | `https://picsum.photos/id/1015/1200/400` | jpeg | 1200×400 | FILL crop (3:1 into 1.875:1) |
| `FIX-ULTRAWIDE` | `https://picsum.photos/id/1015/3000/10` | jpeg | 3000×10 | Extreme ratio (300:1) |
| `FIX-HUGE` | `https://picsum.photos/id/1025/4096/4096` | jpeg | 4096² | Oversized images, compression policy |
| `FIX-WEBP` | `https://picsum.photos/seed/c2d/100/100.webp` | webp | 100×100 | Format fallback |
| `FIX-SVG` | `https://placehold.co/200x200.svg` | svg | 200×200 | Vector export |
| `FIX-BROKEN-404` | `https://picsum.photos/id/99999/300/300` | — | — | Load fallback (`expect_status: 404`) |

Two traps recorded in the registry: **picsum 302-redirects to `fastly.picsum.photos/...?hmac=...`**, and the signature changes — so cases carry the original `picsum.photos` URL and the verifier must follow redirects. And **never paste a signed URL into a case**: it expires within days and takes the whole case set with it.

## Compatibility and boundaries

Distributed as Markdown instructions, relative-path references and on-demand standard-library scripts. No SDK, and no network dependency beyond the image hosts themselves.

| Host | Directory | Verified scope |
|---|---|---|
| WorkBuddy | `~/.workbuddy/skills/` or project `.workbuddy/skills/` | Primary target; tested locally |
| Claude Code | `~/.claude/skills/` or project `.claude/skills/` | Layout compatible; output quality not measured there |
| Other `SKILL.md` hosts | Per their rules | Adaptable layout; triggering and output need separate verification |

**Language**: documentation and skill instructions are in Chinese. **Scope**: black-box image validation for the C2D pipeline only — not unit tests of generated code, load testing, or security scanning. **Not covered**: native Windows (use WSL); no non-macOS platform has been tested.

## Repository layout

```text
skills/                    One directory per skill
  c2d-case-writing/
    SKILL.md               Single entry: red lines, five sections, six stages, common mistakes
    references/            Loaded on demand: scenario matrix, fixture registry, format rules
    assets/                Copy-ready case template with gold-standard samples
    scripts/               Two gates, zero third-party dependencies
scripts/check_repo.py      Repo checks: naming / metadata / broken refs / local paths / script syntax
.github/workflows/check.yml  Runs the checks on push and PR
install.sh                 Installer (single / all / project-scoped / backup-on-overwrite)
assets/                    README artwork (light and dark hero, workflow, gate output)
```

## Adding a skill

The collection only grows if the rules hold. `scripts/check_repo.py` treats items 1 and 2 as errors:

1. **Directory name == frontmatter `name`**, lowercase with hyphens, ≤40 chars. A mismatch silently fails to load.
2. **`description` states three things**: what it does, when to use it, and the literal trigger phrases. It is the only part permanently in context.
3. **Keep `SKILL.md` a skeleton.** Details go to `references/`, templates to `assets/`, runnable logic to `scripts/`. Aim for ≤500 lines.
4. **Machine-check what can be machine-checked**, and say what the gate cannot judge.
5. **Never invent facts.** Unknown field names or threshold sources become `TODO: confirm {what} with {whom}` — not "usually" or "probably".

Before committing:

```bash
python3 scripts/check_repo.py
```

## Measured results

All figures below come from real local runs (macOS · Python 3.13 · 2026-11-26), not estimates:

| Scenario | Result |
|---|---|
| `case_lint_c2d.py` on the template (4 modules / 5 cases) | 0 errors, 0 warnings → passes, exit 0 |
| Same script on a deliberately broken 2-case sample | **11 errors, 4 warnings → blocked**, exit 1 |
| `check_image_links.py` on the template (4 links) | 3 OK / 1 expected failure / 0 failures, exit 0 |
| Removing `expect_status` from the 404 case | The same case is immediately flagged as a broken link, exit 1 |
| All 13 fixtures, one `curl` each | 200 with matching `Content-Type` |
| `check_repo.py` negative test (name mismatch, broken ref, local path, script syntax error) | All four reported, exit 1 |

**What is not here**: no with-skill vs without-skill quality comparison has been run, so this README claims no percentage improvements. That will be added only when a controlled experiment exists.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Reproducible issues and concrete requests go to [Issues](https://github.com/Jasonlya/xxuntuil-test-skills/issues).

## License

[MIT](./LICENSE)
