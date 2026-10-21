"""
Responsive mobile rules (audit 2026-10-21): the topbar must never force a
page-level horizontal scroll, and the 769-1100px range cannot be left
without a breakpoint while the topbar keeps fixed-width footprints.

H1: .pool-group__counts has a fixed 46ch footprint (~300px) and the
    .topbar-meta row had no wrap — on a ~360px phone the meta row (~590px)
    overflowed the page.
H2: the only breakpoint was 768px; tablets/intermediate windows rendered
    the desktop single-row topbar with its fixed 52px height.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _media_body(css, max_width):
    """Body of the first @media (max-width: Npx) block."""
    m = re.search(r"@media\s*\(max-width:\s*%dpx\)\s*\{" % max_width, css)
    assert m, "missing @media (max-width: %dpx) block" % max_width
    depth, end = 1, m.end()
    while end < len(css) and depth:
        if css[end] == "{":
            depth += 1
        elif css[end] == "}":
            depth -= 1
        end += 1
    return css[m.end():end - 1]


def _decls(body, selector):
    """Declarations of the first `selector { ... }` rule inside a body."""
    m = re.search(re.escape(selector) + r"\s*\{", body)
    if not m:
        return []
    depth, end = 1, m.end()
    while end < len(body) and depth:
        if body[end] == "{":
            depth += 1
        elif body[end] == "}":
            depth -= 1
        end += 1
    return [d.strip() for d in body[m.end():end - 1].split(";") if d.strip()]


def test_tablet_breakpoint_relieves_the_topbar():
    """H2: a 1100px breakpoint wraps the topbar and lets its height grow."""
    css = _read("web/theme.css")
    body = _media_body(css, 1100)

    topbar = _decls(body, ".topbar")
    assert "flex-wrap: wrap" in topbar
    assert "height: auto" in topbar
    assert any(d.startswith("min-height") and "header-height" in d for d in topbar)

    meta = _decls(body, ".topbar-meta")
    assert "flex-wrap: wrap" in meta


def test_phone_topbar_never_forces_page_scroll():
    """H1: under 768px the counts footprint must not widen the page; the
    stacked topbar must NOT inherit wrap (wrap on a column flex makes
    horizontal columns)."""
    css = _read("web/theme.css")
    body = _media_body(css, 768)

    topbar = _decls(body, ".topbar")
    assert "flex-direction: column" in topbar
    assert "flex-wrap: nowrap" in topbar

    assert "flex-wrap: wrap" in _decls(body, ".topbar-meta")
    counts = _decls(body, ".pool-group__counts")
    assert "min-width: 0" in counts
    assert "white-space: normal" in counts
