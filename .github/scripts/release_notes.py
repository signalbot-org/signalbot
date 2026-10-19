"""Group GitHub's generated release notes by the conventional commit prefix of PRs.

Reads the generated notes from stdin and writes the grouped notes to stdout, e.g.:
gh api repos/{owner}/{repo}/releases/generate-notes -f tag_name=v1.2.3 --jq .body \
    | python .github/scripts/release_notes.py
"""

import re
import sys

# A generated entry, e.g. "* feat: add poll command by @user in https://github.com/.../pull/1"
ENTRY = re.compile(r"^\* (?P<title>.+) (?P<rest>by @\S+ in https://\S+)$")
PREFIX = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?!?:\s*(?P<title>.+)$")

# (heading, subheading), in the order they are written
SECTIONS = {
    "feat": ("New features", None),
    "fix": ("Bug fixes", None),
    "docs": ("Documentation", None),
    "deps": ("Dependencies", "Main"),
    "deps-dev": ("Dependencies", "Dev"),
}
OTHER = ("Other changes", None)


def section(title: str) -> tuple[tuple[str, str | None], str]:
    """Return the section of a PR and its title without the prefix."""
    match = PREFIX.match(title)
    if match is None:
        return OTHER, title[0].upper() + title[1:]
    # Dependency PRs keep their prefix, as in the previous releases
    if match["scope"] in {"deps", "deps-dev"}:
        return SECTIONS[match["scope"]], title
    stripped = match["title"]
    return SECTIONS.get(match["type"], OTHER), stripped[0].upper() + stripped[1:]


def group(notes: str) -> str:
    """Rewrite the "What's Changed" list of the generated notes into sections."""
    grouped: dict[tuple[str, str | None], list[str]] = {
        key: [] for key in [*SECTIONS.values(), OTHER]
    }
    rest: list[str] = []
    for line in notes.splitlines():
        entry = ENTRY.match(line)
        if entry is None:
            rest.append(line)
            continue
        key, title = section(entry["title"])
        grouped[key].append(f"* {title} {entry['rest']}")

    lines = ["## What's Changed"] if any(grouped.values()) else []
    written_headings: set[str] = set()
    for (heading, subheading), entries in grouped.items():
        if not entries:
            continue
        if heading not in written_headings:
            lines += ["", f"### {heading}"]
            written_headings.add(heading)
        if subheading is not None:
            lines += ["", f"#### {subheading}"]
        lines += entries

    # Keeps the "New Contributors" and "Full Changelog" sections as they are
    rest = [line for line in rest if line.strip() != "## What's Changed"]
    body = "\n".join(rest).strip()
    if body:
        lines += ["", body]
    return "\n".join(lines).strip() + "\n"


if __name__ == "__main__":
    sys.stdout.write(group(sys.stdin.read()))
