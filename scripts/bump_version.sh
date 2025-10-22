#!/usr/bin/env bash
set -euo pipefail

FILE="pyproject.toml"

# Ensure the file exists
if [[ ! -f "$FILE" ]]; then
  echo "❌ pyproject.toml not found in $(pwd)"
  exit 1
fi

# Extract version line
OLD_VERSION=$(grep -E '^version *= *"' "$FILE" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')

if [[ -z "$OLD_VERSION" ]]; then
  echo "❌ Could not parse version from $FILE"
  exit 1
fi

IFS='.' read -r MAJOR MINOR PATCH <<<"$OLD_VERSION" || {
  echo "❌ Failed to split version: $OLD_VERSION"
  exit 1
}

# Make sure PATCH is numeric
if ! [[ "$PATCH" =~ ^[0-9]+$ ]]; then
  echo "❌ Non-numeric patch version: $PATCH"
  exit 1
fi

NEW_VERSION="${MAJOR}.${MINOR}.$((PATCH + 1))"

# BSD/macOS sed vs GNU sed compatibility
if sed --version >/dev/null 2>&1; then
  # GNU sed
  sed -i "s/^version *= *.*/version = \"${NEW_VERSION}\"/" "$FILE"
else
  # BSD/macOS sed
  sed -i '' "s/^version *= *.*/version = \"${NEW_VERSION}\"/" "$FILE"
fi

echo "🔢 Bumped version: ${OLD_VERSION} → ${NEW_VERSION}" >&2
echo "$NEW_VERSION"
