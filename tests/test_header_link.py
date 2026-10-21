"""
Header title link (2026-10-21, user request): clicking "Pases AgileOps" in
the topbar must open the SharePoint folder with the AgileOps release
schedules (HorariosDeAtencion).

The <h1> is static markup in the template — renderer.py only rewrites the
<title> tag from config, so wrapping the heading text in an <a> is safe.
The link opens in a new tab so the dashboard is never replaced, and the
anchor inherits the heading's look by default (underline only on hover).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Verbatim URL provided by the user (SharePoint percent-encodes -, . and _ too).
SHAREPOINT_URL = (
    "https://credicorponline.sharepoint.com/sites/GestionDeCambios-CIO/"
    "Documentos%20compartidos/Forms/AllItems.aspx"
    "?id=%2Fsites%2FGestionDeCambios%2DCIO%2FDocumentos%20compartidos"
    "%2FCapacity%2DAgile%2F6%2E%20AgileOps%2DRelease%5FHorariosDeAtencion"
    "%5FINTERNO&viewid=4664a045%2D5641%2D4e1e%2D8164%2Dff7be9934e6d"
    "&newTargetListUrl=%2Fsites%2FGestionDeCambios%2DCIO%2FDocumentos"
    "%20compartidos&viewpath=%2Fsites%2FGestionDeCambios%2DCIO%2FDocumentos"
    "%20compartidos%2FForms%2FAllItems%2Easpx"
)


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


def test_header_title_links_to_the_sharepoint_folder():
    """The <h1> text is wrapped in an anchor with the exact URL, in a new tab."""
    html = _read("web/dashboard_template.html")
    m = re.search(r"<h1>(.*?)</h1>", html, re.S)
    assert m, "missing <h1> in the template"
    inner = m.group(1)
    assert 'href="%s"' % SHAREPOINT_URL in inner, "h1 must link to the SharePoint folder"
    assert 'target="_blank"' in inner, "the dashboard must stay open (new tab)"
    assert "noopener" in inner, "rel must prevent the opened page from controlling this one"
    assert "Pases AgileOps" in inner, "the visible title text must not change"


def test_header_link_keeps_the_heading_look():
    """Anchor inherits the heading colors; underline appears only on hover."""
    css = _read("web/theme.css")
    base = _block(css, ".topbar h1 a")
    assert "color: inherit" in base, "the link must not pick up the browser's link color"
    assert "text-decoration: none" in base, "the default must look exactly like the plain title"
    hover = _block(css, ".topbar h1 a:hover")
    assert "underline" in hover, "hover must signal that the title is clickable"
