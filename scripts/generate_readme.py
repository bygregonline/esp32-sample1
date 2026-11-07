#!/usr/bin/env python3
"""Render the root README from structure.md and README.template.md."""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "structure.md"
TEMPLATE = ROOT / "README.template.md"
OUTPUT = ROOT / "README.md"
TOKEN = re.compile(r"\{\{([^{}]+)\}\}")


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def read_structure() -> tuple[dict, dict[str, str]]:
    source = SOURCE.read_text(encoding="utf-8")
    match = re.match(r"\A\+\+\+\n(.*?)\n\+\+\+\n", source, re.DOTALL)
    if match is None:
        raise ValueError("structure.md must start with +++ TOML front matter")
    metadata = tomllib.loads(match.group(1))
    body = source[match.end() :]

    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    in_fence = False
    for line in body.splitlines(keepends=True):
        if line.startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            if current_name is not None:
                sections[current_name] = "".join(current_lines).strip()
            current_name = line[3:].strip()
            if current_name in sections:
                raise ValueError(f"Duplicate section in structure.md: {current_name}")
            current_lines = [line]
        elif current_name is None:
            if line.strip():
                raise ValueError("Content before the first ## section in structure.md")
        else:
            current_lines.append(line)
    if current_name is not None:
        sections[current_name] = "".join(current_lines).strip()
    if not sections:
        raise ValueError("structure.md contains no ## sections")
    return metadata, sections


def render_badges(metadata: dict) -> str:
    badges = metadata.get("badges", [])
    if not badges:
        raise ValueError("structure.md must define at least one [[badges]] entry")
    return " ".join(f"[![{badge['alt']}]({badge['image']})]({badge['link']})" for badge in badges)


def project_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = {Path(part.decode("utf-8")) for part in result.stdout.split(b"\0") if part}
    return sorted(path for path in paths if path != Path("README.md") and (ROOT / path).is_file())


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    for unit in ("KiB", "MiB", "GiB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TiB"


def repository_snapshot(metadata: dict) -> str:
    # Excluding the generated README avoids the self-referential commit hash
    # and file-size cycle that a README-only commit would otherwise create.
    commit = git("log", "-1", "--format=%H|%cI", "--", ".", ":(exclude)README.md")
    commit_hash, committed_at = commit.split("|", 1)
    files = project_files()
    total_bytes = sum((ROOT / path).stat().st_size for path in files)
    slug = metadata["repository"]
    return "\n".join(
        (
            "## Repository snapshot",
            "",
            f"- **Last source commit:** [`{commit_hash[:7]}`]"
            f"(https://github.com/{slug}/commit/{commit_hash})",
            f"- **Commit date:** {committed_at}",
            f"- **Repository size:** {human_size(total_bytes)} across {len(files)} project files "
            "(generated `README.md` excluded)",
            "",
            "_Snapshot captured when this README was generated._",
        )
    )


def render() -> str:
    metadata, sections = read_structure()
    template = TEMPLATE.read_text(encoding="utf-8")
    used_sections: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        if token == "title":
            return metadata["title"]
        if token == "badges":
            return render_badges(metadata)
        if token == "repository_snapshot":
            return repository_snapshot(metadata)
        if token.startswith("section:"):
            name = token.removeprefix("section:")
            if name not in sections:
                raise ValueError(f"Template requests missing section: {name}")
            used_sections.add(name)
            return sections[name]
        raise ValueError(f"Unknown README template token: {token}")

    rendered = TOKEN.sub(replace, template).rstrip() + "\n"
    unused = sorted(set(sections) - used_sections)
    if unused:
        raise ValueError(f"Add these structure.md sections to the template: {', '.join(unused)}")
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if README.md is stale")
    args = parser.parse_args()
    try:
        expected = render()
    except (KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"README generation failed: {exc}", file=sys.stderr)
        return 2

    actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if args.check:
        if actual == expected:
            print("README.md is up to date")
            return 0
        diff = difflib.unified_diff(
            actual.splitlines(),
            expected.splitlines(),
            fromfile="README.md",
            tofile="generated README.md",
        )
        print("\n".join(list(diff)[:100]), file=sys.stderr)
        print("Run python3 scripts/generate_readme.py", file=sys.stderr)
        return 1

    if actual != expected:
        OUTPUT.write_text(expected, encoding="utf-8")
        print("Generated README.md from structure.md")
    else:
        print("README.md is already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
