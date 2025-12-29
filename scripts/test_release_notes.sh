#!/bin/bash
# Test script for release notes generation
# Uses the same generate_release_notes.py script as the GitHub Actions workflow

set -e

echo "============================================================"
echo "Testing Release Notes Generation"
echo "============================================================"
echo ""

# Test version
VERSION="${1:-0.1.1}"
TAG="v${VERSION}"

echo "Testing with version: $VERSION (tag: $TAG)"
echo ""

# Create temporary file for release notes
RELEASE_NOTES_FILE=$(mktemp)
echo "Using temporary file: $RELEASE_NOTES_FILE"
echo ""

# Use the same script as GitHub Actions workflow
echo "✓ Using generate_release_notes.py script (same as workflow)"
python3 scripts/generate_release_notes.py "$VERSION" "$RELEASE_NOTES_FILE"

echo ""
echo "============================================================"
echo "Generated Release Notes:"
echo "============================================================"
echo ""
cat "$RELEASE_NOTES_FILE"
echo ""
echo "============================================================"
echo "File saved for preview:"
echo "============================================================"
echo ""

# Save to a file for easy viewing
OUTPUT_FILE="test_release_notes_${VERSION}.md"
cp "$RELEASE_NOTES_FILE" "$OUTPUT_FILE"
echo "✓ Release notes saved to: $OUTPUT_FILE"
echo ""
echo "To preview markdown rendering:"
echo "  - Open in VS Code or any markdown viewer"
echo "  - Or view on GitHub by creating a test release"
echo ""

# Cleanup
rm -f "$RELEASE_NOTES_FILE"

echo "============================================================"
echo "Test Complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Review the generated markdown file"
echo "  2. If it looks good, create a GitHub release"
echo "  3. The workflow will use the same logic"
echo "============================================================"

