from __future__ import annotations

from pathlib import Path

from harness_kernel.phase5_models import (
    AcceptanceCriteria,
    CapabilityFingerprint,
    Phase5Task,
    VisualBrief,
)

PACKAGE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
HOST_DIGEST = "sha256:" + "3" * 64


def make_fingerprint(
    tmp_path: Path, *, package_digest: str = PACKAGE_DIGEST
) -> CapabilityFingerprint:
    package = tmp_path / "design-director"
    package.mkdir(exist_ok=True)
    return CapabilityFingerprint(
        capability_id="design-director",
        version="0.1.0",
        scope="PROJECT",
        canonical_path=str(package),
        package_fingerprint=package_digest,
        manifest_fingerprint=MANIFEST_DIGEST,
        provenance="LOCAL",
        trust="PROJECT_TRUSTED",
        compatibility="COMPATIBLE",
        package_status="INSPECTED",
        load_eligibility="ELIGIBLE_DECLARATIVE_METADATA_ONLY",
        files=("SKILL.md", "agents/openai.yaml"),
        scripts=(),
        dependencies=(),
    )


def make_task(tmp_path: Path) -> Phase5Task:
    workspace = tmp_path / "workspace"
    artifact_root = workspace / "artifacts"
    workspace.mkdir()
    artifact_root.mkdir()
    brief = VisualBrief(
        outcome="A premium emergency landing hero for a fictional veterinary center",
        audience="Pet owners making a high-stakes urgent-care decision",
        job="Orient quickly and call the emergency team",
        thesis="Quiet clinical confidence with a warm, nocturnal observatory signal",
        medium="HTML/CSS/SVG response-derived artifact",
        primary_action="Call the emergency team",
        exact_copy={
            "eyebrow": "24/7 emergency veterinary care",
            "heading": "When every minute matters, stay close to care.",
            "support": (
                "Northline Veterinary Emergency Center pairs calm triage "
                "with advanced overnight care."
            ),
            "cta": "Call the emergency team",
        },
        must_include=("semantic landmarks", "original code-native visual mark", "mobile reflow"),
        must_avoid=("generic SaaS template", "invented testimonials", "remote assets"),
        responsive_intent=(
            "Two-column desktop hero becomes an intentional stacked mobile composition"
        ),
        accessibility_intent="WCAG 2.2 AA-oriented semantics, focus and contrast",
        asset_role="A geometric orbital clinical mark, not a placeholder photo",
    )
    criteria = AcceptanceCriteria(
        required_sections=("header", "main", "footer"),
        required_copy=("Northline", "Call the emergency team"),
        render_viewports=((1440, 900), (390, 844)),
        dimensions=(
            "ART_DIRECTION",
            "VISUAL_HIERARCHY",
            "TYPOGRAPHY",
            "COMPOSITION",
            "SPACING",
            "COLOR_SYSTEM",
            "PRODUCT_SPECIFICITY",
            "RESPONSIVENESS",
            "ACCESSIBILITY",
            "POLISH",
            "GENERIC_AI_SLOP_AVOIDANCE",
        ),
        forbidden_signals=("lorem ipsum", "placeholder", "http://", "https://"),
    )
    return Phase5Task(
        task_id="TASK-P5-DESIGN-001",
        run_id="RUN-P5-DESIGN-001",
        title="Northline emergency veterinary hero",
        request="Create the bounded Northline Veterinary Emergency Center landing hero.",
        workspace=str(workspace),
        artifact_root=str(artifact_root),
        brief=brief,
        criteria=criteria,
        created_at=1_756_500_000,
    )


def valid_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Northline Veterinary Emergency Center</title>
<style>
:root {
  --ink: #f7f1e7;
  --muted: #c8c5bd;
  --canvas: #101b1b;
  --accent: #e5a46b;
  --line: #365653;
  --space: clamp(1rem, 2vw, 2rem);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: Georgia, serif;
}
main {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 80vh;
  gap: var(--space);
  padding: 3rem;
}
header, footer { padding: 1.25rem 3rem; }
a { color: inherit; }
button, a { min-height: 44px; }
.hero-mark { width: 100%; height: auto; }
@media (max-width: 700px) {
  main { grid-template-columns: 1fr; padding: 2rem 1.25rem; }
  header, footer { padding: 1rem 1.25rem; }
}
</style></head>
<body>
<header><a href="#main">Northline Veterinary Emergency Center</a></header>
<main id="main">
  <section aria-labelledby="hero-title">
    <p>24/7 emergency veterinary care</p>
    <h1 id="hero-title">When every minute matters, stay close to care.</h1>
    <p>Northline Veterinary Emergency Center pairs calm triage with advanced overnight care.</p>
    <a href="tel:+15550142">Call the emergency team</a>
  </section>
  <section aria-label="Northline clinical mark">
    <svg class="hero-mark" viewBox="0 0 480 420" role="img" aria-labelledby="mark-title">
      <title id="mark-title">Orbital clinical mark</title>
      <circle cx="240" cy="210" r="110" fill="none" stroke="#e5a46b" stroke-width="4"/>
      <ellipse cx="240" cy="210" rx="190" ry="70" fill="none"
        stroke="#365653" stroke-width="3" transform="rotate(-24 240 210)"/>
      <circle cx="240" cy="210" r="24" fill="#e5a46b"/>
    </svg>
  </section>
</main>
<footer><p>Calm, continuous care for the night shift.</p></footer>
</body>
</html>"""
