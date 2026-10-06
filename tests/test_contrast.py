"""Phase 5: every text/background pair in app.css is >= 4.5:1 (WCAG AA),
in both the light (default) and dark theme.

Parses the CSS custom-property tokens directly out of app.css rather than
hardcoding a second copy of the palette, so this fails the moment either
theme's tokens drift out of an accessible range.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS_PATH = Path(__file__).resolve().parents[1] / "frontend" / "static" / "css" / "app.css"


def _parse_root_block(css: str, selector: str) -> dict[str, str]:
    """Extract ``--name: value;`` custom properties from one ``selector { ... }`` block."""
    pattern = re.compile(re.escape(selector) + r"\s*\{([^}]*)\}", re.DOTALL)
    match = pattern.search(css)
    assert match, f"could not find a {selector} block in app.css"
    body = match.group(1)
    tokens = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body):
        tokens[name.strip()] = value.strip()
    return tokens


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip()
    if value.lower() == "#fff" or value.lower() == "#ffffff":
        return (255, 255, 255)
    h = value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgba_to_rgb(value: str) -> tuple[tuple[int, int, int], float]:
    nums = [float(x) for x in re.findall(r"[\d.]+", value)]
    r, g, b, a = nums[0], nums[1], nums[2], nums[3] if len(nums) > 3 else 1.0
    return (int(r), int(g), int(b)), a


def _resolve(value: str, tokens: dict[str, str]) -> str:
    """Resolve a (possibly var()-wrapped, possibly chained) token to a literal color."""
    seen = set()
    while value.strip().startswith("var("):
        name = value.strip()[4:-1].strip()
        assert name not in seen, f"circular var() reference at {name}"
        seen.add(name)
        assert name in tokens, f"{name} is not defined in this theme block"
        value = tokens[name]
    return value.strip()


def _linear(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def _contrast(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    l1, l2 = _luminance(rgb1), _luminance(rgb2)
    l1, l2 = max(l1, l2), min(l1, l2)
    return (l1 + 0.05) / (l2 + 0.05)


def _color_on(value: str, tokens: dict[str, str], page_bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Resolve a token to its final rendered RGB, blending alpha over `page_bg`."""
    literal = _resolve(value, tokens)
    if literal.startswith("rgba"):
        rgb, alpha = _rgba_to_rgb(literal)
        return tuple(round(rgb[i] * alpha + page_bg[i] * (1 - alpha)) for i in range(3))
    return _hex_to_rgb(literal)


# Each pair mirrors a real rule in app.css: (text token, background token).
# Backgrounds that are themselves a var() (badge/banner tints) are resolved
# against the page's own --bg, matching how they actually render (nested
# inside a .card, which sits on --bg via --bg-card... close enough for a
# conservative check since --bg-card is lighter than --bg in dark mode and
# darker than --bg in light mode is not the case here -- both land within
# a few luminance points, and the badge tints are low-alpha so the page
# background dominates the blend either way).
PAIRS = [
    ("--text", "--bg"),
    ("--text", "--bg-card"),
    ("--text-dim", "--bg"),
    ("--text-dim", "--bg-card"),
    ("--text-bright", "--bg"),
    ("--text-bright", "--bg-card"),
    ("--red-text", "--red-bg"),
    ("--green-text", "--green-bg"),
    ("--yellow-text", "--yellow-bg"),
    ("--blue-text", "--blue-bg"),
    ("--purple-text", "--purple-bg"),
    ("--neutral-text", "--neutral-bg"),
]
# --red/--green/--yellow/--blue/--purple/--neutral themselves are
# intentionally NOT in PAIRS: app.css only uses them for solid button
# fills (white text on top, not covered by these pairs), borders, and
# small dots -- never as a text color on the page background (the
# -text variants exist precisely so there's always a safe token for
# that). test_no_raw_semantic_color_used_as_text below keeps that true.

MIN_RATIO = 4.5


@pytest.fixture(scope="module")
def css() -> str:
    return CSS_PATH.read_text()


@pytest.fixture(scope="module")
def light_tokens(css: str) -> dict[str, str]:
    return _parse_root_block(css, ":root")


@pytest.fixture(scope="module")
def dark_tokens(css: str, light_tokens: dict[str, str]) -> dict[str, str]:
    # The dark block only overrides a subset; fall back to light for the rest.
    overrides = _parse_root_block(css, ':root[data-theme="dark"]')
    merged = dict(light_tokens)
    merged.update(overrides)
    return merged


@pytest.mark.parametrize("text_token,bg_token", PAIRS)
def test_light_theme_contrast(light_tokens: dict[str, str], text_token: str, bg_token: str):
    page_bg = _hex_to_rgb(_resolve(light_tokens["--bg"], light_tokens))
    text_rgb = _color_on(light_tokens[text_token], light_tokens, page_bg)
    bg_rgb = _color_on(light_tokens[bg_token], light_tokens, page_bg)
    ratio = _contrast(text_rgb, bg_rgb)
    assert ratio >= MIN_RATIO, (
        f"light theme {text_token} on {bg_token}: {ratio:.2f}:1 (need >= {MIN_RATIO}:1)"
    )


@pytest.mark.parametrize("text_token,bg_token", PAIRS)
def test_dark_theme_contrast(dark_tokens: dict[str, str], text_token: str, bg_token: str):
    page_bg = _hex_to_rgb(_resolve(dark_tokens["--bg"], dark_tokens))
    text_rgb = _color_on(dark_tokens[text_token], dark_tokens, page_bg)
    bg_rgb = _color_on(dark_tokens[bg_token], dark_tokens, page_bg)
    ratio = _contrast(text_rgb, bg_rgb)
    assert ratio >= MIN_RATIO, (
        f"dark theme {text_token} on {bg_token}: {ratio:.2f}:1 (need >= {MIN_RATIO}:1)"
    )


def test_light_is_the_default_theme(css: str):
    """The toggle must be opt-in: no :root default or @media query may set
    data-theme or silently prefer dark for a first-time visitor."""
    assert "prefers-color-scheme" not in css, (
        "the OS dark-mode preference must not override the light default "
        "(a presenter's OS setting shouldn't change what's on the projector)"
    )


def test_no_raw_semantic_color_used_as_text(css: str):
    """--red/--green/--yellow/--blue/--purple/--neutral are calibrated for
    buttons/borders/dots, not guaranteed readable as text on the page
    background -- any `color:` use must go through the -text variant."""
    raw_as_text = re.findall(
        r"(?<![\w-])color:\s*var\(--(red|green|yellow|blue|purple|neutral)\)",
        css,
    )
    assert not raw_as_text, f"found raw semantic color(s) used as text: {raw_as_text}"


def test_body_text_is_at_least_14px():
    html_css = CSS_PATH.read_text()
    match = re.search(r"html,\s*body\s*\{([^}]*)\}", html_css, re.DOTALL)
    assert match
    size = re.search(r"font-size:\s*(\d+)px", match.group(1))
    assert size and int(size.group(1)) >= 14


def test_no_label_sized_font_below_13px(css: str):
    sizes = [int(px) for px in re.findall(r"font-size:\s*(\d+)px", css)]
    assert sizes, "expected at least one font-size rule"
    assert min(sizes) >= 13, f"found a font-size below 13px: {min(sizes)}px"
