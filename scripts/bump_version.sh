#!/usr/bin/env bash
set -e

FILE="pyproject.toml"
if [[ ! -f "$FILE" ]]; then
  echo "❌ pyproject.toml not found!"
  exit 1
fi

OLD_VERSION=$(grep '^version = ' "$FILE" | cut -d'"' -f2)
IFS='.' read -r MAJOR MINOR PATCH <<<"$OLD_VERSION"
NEW_VERSION="${MAJOR}.${MINOR}.$((PATCH + 1))"

sed -i "s/version = .*/version = \"${NEW_VERSION}\"/" "$FILE"

echo "🔢 Bumped version: ${OLD_VERSION} → ${NEW_VERSION}"
echo "$NEW_VERSION"
