"""
Timeline legend layout (2026-10-21, user request: "puedes centrarlo o
organizarlo mejor?").

The legend was a flat strip of 9 items in one flex row: at ~1600px it
wrapped after the seventh item, leaving a two-item second row left-aligned
under a nearly full first row — unbalanced and reading as an accident.

Fix: the items are grouped into three units that wrap as a whole
(Pool | Estados | Señales) and the container centers its rows. Grouping
uses a gap hierarchy (container column-gap wider than the inner group gap)
instead of dividers, because a border/pipe divider would dangle at the
start of a wrapped row.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _block(css, selector):
    """Declarations of the first `selector { ... }` rule."""
    m = re.search(re.escape(selector) + r"\s*\{", css)
    assert m, "missing rule: %s" % selector
    depth, end = 1, m.end()
    while end < len(css) and depth:
        if css[end] == "{":
            depth += 1
        elif css[end] == "}":
            depth -= 1
        end += 1
    return css[m.end():end - 1]


def test_legend_items_live_in_three_groups():
    """Template: Pool | Estados | Señales, no item left outside a group."""
    html = _read("web/dashboard_template.html")
    section = html.split('id="timeline-legend"', 1)[1].split("</section>", 1)[0]
    assert section.count('class="timeline-legend__group"') == 3
    # Everything before the first group must be the title only.
    before_first = section.split('class="timeline-legend__group"', 1)[0]
    assert "timeline-legend__item" not in before_first
    # Every state/signal item sits inside a group (8 items: pool + 5 states
    # + derivado + conflicto).
    assert section.count("timeline-legend__item") == 8


def test_legend_is_centered_with_group_gap_hierarchy():
    """CSS: centered rows; between-group gap wider than inner-group gap."""
    css = _read("web/theme.css")
    container = _block(css, ".timeline-legend")
    assert "justify-content: center" in container, "legend rows must be centered"

    def _px(text, which):
        values = [int(v) for v in re.findall(r"(\d+)px", text)]
        assert values, "expected px gaps in: %r" % text
        return values[-1] if which == "last" else values[0]

    # `gap: <row> <col>` — the column gap separates the groups.
    between_groups = _px(container.split("gap:")[1].split(";")[0], "last")
    inner = _px(_block(css, ".timeline-legend__group").split("gap:")[1].split(";")[0], "first")
    assert between_groups > inner, (
        "container column gap (%dpx) must exceed the inner group gap (%dpx)"
        % (between_groups, inner)
    )
