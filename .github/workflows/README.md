# Workflows

## Structure

```
.github/workflows/
  on_core_release.yml          # Receives dispatch → updates deps → creates PR
  auto_release_on_merge.yml    # Merged PR → bump version → publish to PyPI
  release.yml                  # Manual tag → publish to PyPI
  ci.yml                       # Tests on push/PR
scripts/
  bump_version.sh              # Reusable version bump logic
```

## Automated Dependency Updates & Releases

### `on_core_release.yml`
- **Trigger:** `repository_dispatch` event from `market-data-core` (or manual)
- **Action:** Updates `market-data-core` dependency → creates PR → auto-merges after CI

### `auto_release_on_merge.yml`
- **Trigger:** PR with "bump market-data-core" merged to `base`
- **Action:** Bumps version → tags → publishes to PyPI → creates GitHub Release

### `release.yml`
- **Trigger:** Manual tag push (`git tag vX.Y.Z && git push --tags`)
- **Action:** Builds and publishes to PyPI

### `ci.yml`
- **Trigger:** Push or PR
- **Action:** Runs tests

## Setup Required

1. **Branch protection for `base`:** Require "test" status check
2. **Enable auto-merge:** Settings → General → Allow auto-merge
3. **Secrets:**
   - `PYPI_TOKEN` - PyPI API token (rename from `PYPI_API_TOKEN`)
   - `GITHUB_TOKEN` - Auto-provided

## Core Dispatch Setup

Add to `market-data-core/.github/workflows/release.yml`:

```yaml
- name: Notify downstream repos
  uses: peter-evans/repository-dispatch@v2
  with:
    token: ${{ secrets.DISPATCH_TOKEN }}
    repository: mjdevaccount/market-data-store
    event-type: core_release
    client-payload: |
      {
        "version": "${{ steps.version.outputs.version }}",
        "origin": "market-data-core"
      }
```

Core needs `DISPATCH_TOKEN` secret (Personal Access Token with `repo` scope).
