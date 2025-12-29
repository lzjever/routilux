#!/usr/bin/env python3
"""
Generate release notes from CHANGELOG.md or git commits.

This script extracts changelog entries for a given version and adds
installation instructions. It's designed to be used by GitHub Actions
workflows but can also be run locally for testing.

Usage:
    python3 scripts/generate_release_notes.py <version> [output_file]

    If output_file is not provided, output goes to stdout.

Examples:
    # Output to stdout
    python3 scripts/generate_release_notes.py 0.1.1

    # Output to file
    python3 scripts/generate_release_notes.py 0.1.1 release_notes.md
"""

import sys
import os
import subprocess
from pathlib import Path


def get_changelog_section(version, changelog_path="CHANGELOG.md"):
    """
    Extract changelog section for given version.

    Args:
        version: Version string (e.g., "0.1.1")
        changelog_path: Path to CHANGELOG.md file

    Returns:
        str: Changelog content for the version, or None if not found
    """
    if not os.path.exists(changelog_path):
        return None

    with open(changelog_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_pattern = f"## [{version}]"
    in_section = False
    extracted_lines = []

    for line in lines:
        if start_pattern in line:
            in_section = True
            continue
        if in_section:
            # Stop at next version section
            if line.strip().startswith("## ["):
                break
            extracted_lines.append(line)

    if extracted_lines:
        return ''.join(extracted_lines).strip()
    return None


def get_git_commits_since_tag(prev_tag=None):
    """
    Get git commits since previous tag.

    Args:
        prev_tag: Previous tag name, or None to get recent commits

    Returns:
        str: Formatted commit list, or None on error
    """
    try:
        if prev_tag:
            cmd = ['git', 'log', f'{prev_tag}..HEAD', '--pretty=format:- %s (%h)', '--no-merges']
        else:
            cmd = ['git', 'log', '--pretty=format:- %s (%h)', '--no-merges', '-10']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_previous_tag():
    """
    Get the previous git tag.

    Returns:
        str: Previous tag name, or None if not found
    """
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--abbrev=0', 'HEAD^'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def generate_release_notes(version, tag=None):
    """
    Generate release notes for given version.

    Args:
        version: Version string (e.g., "0.1.1")
        tag: Tag string (e.g., "v0.1.1"), defaults to "v{version}"

    Returns:
        str: Complete release notes
    """
    if tag is None:
        tag = f"v{version}"

    # Try to get from CHANGELOG.md
    changelog_content = get_changelog_section(version)

    # Fallback to git commits
    if not changelog_content:
        prev_tag = get_previous_tag()
        commits = get_git_commits_since_tag(prev_tag)

        notes_lines = ["## What's Changed", ""]
        if commits:
            notes_lines.append(commits)
        else:
            notes_lines.append("Initial release")

        changelog_content = '\n'.join(notes_lines)

    # Add installation instructions
    installation = """
## Installation

```bash
pip install routilux
```
""".strip()

    # Combine changelog and installation
    full_notes = f"{changelog_content}\n\n{installation}"
    return full_notes


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/generate_release_notes.py <version> [output_file]", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    version = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    # Generate release notes
    notes = generate_release_notes(version)

    # Output to file or stdout
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(notes)
        print(f"Release notes written to: {output_file}", file=sys.stderr)
    else:
        print(notes)


if __name__ == '__main__':
    main()

