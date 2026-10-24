"""Regenerate the README banners from docs/assets/logo.svg.

Writes docs/assets/banner-light.svg and docs/assets/banner-dark.svg. Rerun it after
changing the logo. Needs Inkscape and the Lato font installed; the text is converted to
paths so the banners render the same everywhere without the font.

    uv run scripts/generate_banners.py
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets"

# theme name -> (wordmark color, tagline color)
THEMES = {
    "light": ("#0F172A", "#475569"),
    "dark": ("#F8FAFC", "#94A3B8"),
}

TEMPLATE = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 256" width="960" height="256">
  <defs>
    <linearGradient id="word" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4F8CFF"/>
      <stop offset="1" stop-color="#6D3BE8"/>
    </linearGradient>
  </defs>
  <g transform="translate(0 49) scale(0.8)">{logo}</g>
  <text x="230" y="160" font-family="Lato" font-weight="900" font-size="118"
        letter-spacing="-2">
    <tspan fill="{fg}">signal</tspan><tspan fill="url(#word)">bot</tspan>
  </text>
  <text x="236" y="214" font-family="Lato" font-weight="500" font-size="34"
        fill="{muted}">
    Build Signal bots in Python
  </text>
</svg>
"""


def logo_contents() -> str:
    svg = (ASSETS / "logo.svg").read_text()
    match = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.DOTALL)
    if match is None:
        msg = "Could not find the <svg> element in logo.svg"
        raise ValueError(msg)
    return re.sub(r"\s*<title.*?</title>", "", match.group(1))


def main() -> None:
    inkscape = shutil.which("inkscape")
    if inkscape is None:
        msg = "Inkscape is required to generate the banners"
        raise RuntimeError(msg)

    logo = logo_contents()
    with tempfile.TemporaryDirectory() as tmp:
        for name, (fg, muted) in THEMES.items():
            source = Path(tmp) / f"banner-{name}.svg"
            source.write_text(TEMPLATE.format(logo=logo, fg=fg, muted=muted))
            subprocess.run(  # noqa: S603
                [
                    inkscape,
                    str(source),
                    "--export-text-to-path",
                    "--export-area-drawing",
                    "--export-margin=4",
                    "--export-plain-svg",
                    "-o",
                    str(ASSETS / f"banner-{name}.svg"),
                ],
                check=True,
                capture_output=True,
            )


if __name__ == "__main__":
    main()
