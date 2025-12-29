# Scripts

This directory contains utility scripts for development and testing.

## generate_release_notes.py

**Main script for generating release notes.** Used by GitHub Actions workflows and can be run locally for testing.

**Usage:**
```bash
# Output to stdout
python3 scripts/generate_release_notes.py 0.8.0

# Output to file
python3 scripts/generate_release_notes.py 0.8.0 release_notes.md
```

**What it does:**
- Extracts changelog section from CHANGELOG.md for the given version
- Falls back to git commits if changelog entry not found
- Adds installation instructions automatically
- Can output to stdout or file

**Features:**
- Standalone Python script (no external dependencies)
- Used by GitHub Actions workflow
- Can be tested independently
- Handles version extraction and git commit fallback

**Testing:**
```bash
# Test with different versions
python3 scripts/generate_release_notes.py 0.8.0
python3 scripts/generate_release_notes.py 0.7.0

# Test output to file
python3 scripts/generate_release_notes.py 0.8.0 /tmp/test_notes.md
cat /tmp/test_notes.md
```

## test_release_notes.sh

Test script for release notes generation. Wrapper script that uses `generate_release_notes.py` to test release notes locally.

**Usage:**
```bash
# Test with default version (0.8.0)
bash scripts/test_release_notes.sh

# Test with specific version
bash scripts/test_release_notes.sh 0.8.0
```

**What it does:**
- Calls `generate_release_notes.py` (same script used by GitHub Actions)
- Generates release notes with installation instructions
- Saves output to `test_release_notes_<version>.md`
- Shows preview of how it will appear in GitHub

**Output:**
- Creates `test_release_notes_<version>.md` file in the project root
- You can preview the markdown rendering in your editor
- Use this to verify formatting before creating a real release

**Note:** This script is a convenience wrapper around `generate_release_notes.py`. It ensures you're testing with the exact same logic that GitHub Actions will use.

