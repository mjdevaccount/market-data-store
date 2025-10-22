# REPO_TOKEN Permission Issue - Fix Guide

**Date:** October 22, 2025
**Issue:** Auto-release workflow failing to notify infra repository

---

## Error

```
Error: Repository not found, OR token has insufficient permissions.
```

**Workflow:** `.github/workflows/auto_release_on_merge.yml`
**Step:** "Notify Infra Repository"
**Target:** `mjdevaccount/market-data-infra`

---

## Root Cause

The `REPO_TOKEN` secret doesn't have sufficient permissions to:
1. Access the `market-data-infra` repository
2. Send repository dispatch events to it

---

## Required Token Permissions

The `REPO_TOKEN` needs to be a **Personal Access Token (PAT)** or **Fine-grained token** with these permissions:

### Option A: Classic Token (Recommended for simplicity)

**Required Scopes:**
- ✅ `repo` (Full control of private repositories)
  - Includes: `repo:status`, `repo_deployment`, `public_repo`, `repo:invite`
- ✅ `workflow` (Update GitHub Action workflows)

### Option B: Fine-grained Token (More secure, granular)

**Repository access:**
- Must have access to:
  - ✅ `mjdevaccount/market-data-store` (this repo)
  - ✅ `mjdevaccount/market-data-infra` (target repo)

**Repository permissions:**
- ✅ `Contents`: Read and write
- ✅ `Pull requests`: Read and write
- ✅ `Workflows`: Read and write
- ✅ `Metadata`: Read (automatically included)

---

## How to Fix

### Step 1: Verify the Infra Repository Exists

First, confirm the target repository exists and you have access:

```bash
# Check if you can access it
gh repo view mjdevaccount/market-data-infra
```

If this fails, the repository might:
- Not exist yet (needs to be created)
- Have a different name
- Be in a different organization

### Step 2: Create a New Token (if needed)

#### For Classic Token:

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Set token name: `market-data-store-automation`
4. Set expiration: `90 days` (or as per your security policy)
5. Select scopes:
   - ✅ `repo` (all sub-scopes)
   - ✅ `workflow`
6. Click "Generate token"
7. **Copy the token immediately** (you won't see it again)

#### For Fine-grained Token:

1. Go to: https://github.com/settings/personal-access-tokens/new
2. Set token name: `market-data-store-automation`
3. Set expiration: `90 days` (or as per your security policy)
4. Under "Repository access", select:
   - "Only select repositories"
   - Add: `market-data-store`
   - Add: `market-data-infra`
5. Under "Repository permissions":
   - Contents: **Read and write**
   - Pull requests: **Read and write**
   - Workflows: **Read and write**
6. Click "Generate token"
7. **Copy the token immediately**

### Step 3: Update the Repository Secret

```bash
# Update the REPO_TOKEN secret with the new token
gh secret set REPO_TOKEN --repo mjdevaccount/market-data-store

# When prompted, paste your new token
```

Or via GitHub UI:
1. Go to: https://github.com/mjdevaccount/market-data-store/settings/secrets/actions
2. Click on `REPO_TOKEN`
3. Click "Update secret"
4. Paste the new token
5. Click "Update secret"

### Step 4: Test the Workflow

Trigger the workflow manually to test:

```bash
# Re-run the failed workflow
gh run rerun <run-id>

# Or trigger a new release by making a small change
```

---

## Alternative: Make This Step Optional

If you don't need to notify the infra repository, you can make this step optional by adding `continue-on-error: true`:

```yaml
- name: Notify Infra Repository
  if: success()
  continue-on-error: true  # Add this line
  uses: peter-evans/repository-dispatch@v3
  with:
    token: ${{ secrets.REPO_TOKEN }}
    repository: mjdevaccount/market-data-infra
    event-type: downstream_release
    client-payload: >
      {"origin": "market-data-store", "version": "${{ steps.bump.outputs.new_version }}"}
```

---

## Verification Checklist

After updating the token, verify:

- [ ] Token has `repo` scope (classic) or appropriate permissions (fine-grained)
- [ ] Token has access to both `market-data-store` and `market-data-infra`
- [ ] `REPO_TOKEN` secret is updated in repository settings
- [ ] The `market-data-infra` repository exists
- [ ] The token hasn't expired
- [ ] Workflow runs successfully

---

## Common Issues

### Issue: "Repository not found"
- The `market-data-infra` repository might not exist
- Check if it's named differently
- Verify you have access to it

### Issue: "Insufficient permissions"
- Token needs `repo` scope for private repos
- Token needs `workflow` scope for Actions
- Token must have access to both repositories

### Issue: "Token expired"
- PATs expire - check expiration date
- Regenerate and update the secret

---

## Current Token Status

To check the current token's permissions:

```bash
# This will show what scopes the token has
gh auth status
```

---

## Next Steps

1. ✅ Create/update token with correct permissions
2. ✅ Update `REPO_TOKEN` secret in repository settings
3. ✅ Verify `market-data-infra` repository exists
4. ✅ Re-run the workflow to test

**Note:** The release itself (v0.6.8) was successful! Only the infra notification failed.
The package was published to PyPI and GitHub releases correctly. 🎉
