#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${REPO_OWNER:-SAYURIqvq}"
REPO_NAME="${REPO_NAME:-AutoAIAnswer}"
REMOTE="${REMOTE:-origin}"
MAIN_BRANCH="${MAIN_BRANCH:-main}"
WINDOWS_ASSET="${WINDOWS_ASSET:-AutoAIAnswer-Windows.zip}"
MAC_ASSET="${MAC_ASSET:-AutoAIAnswer-macOS.dmg}"
WAIT_SECONDS="${WAIT_SECONDS:-2400}"
POLL_SECONDS="${POLL_SECONDS:-20}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() {
  printf '[release] %s\n' "$*" >&2
}

fail() {
  printf '[release] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

api() {
  local method="$1"
  local url="$2"
  shift 2
  curl --retry 3 --retry-all-errors --connect-timeout 20 --max-time 180 \
    -fsS \
    -X "$method" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$@" \
    "$url"
}

json_value() {
  python3 -c 'import json, sys
data = json.load(sys.stdin)
path = sys.argv[1].split(".")
for key in path:
    data = data[int(key)] if isinstance(data, list) else data[key]
print(data)'
}

asset_id_by_name() {
  local release_json="$1"
  local asset_name="$2"
  RELEASE_JSON="$release_json" python3 - "$asset_name" <<'PY'
import json
import os
import sys

target = sys.argv[1]
data = json.loads(os.environ["RELEASE_JSON"])
for asset in data.get("assets", []):
    if asset.get("name") == target:
        print(asset.get("id", ""))
        break
PY
}

asset_url_by_name() {
  local release_json="$1"
  local asset_name="$2"
  RELEASE_JSON="$release_json" python3 - "$asset_name" <<'PY'
import json
import os
import sys

target = sys.argv[1]
data = json.loads(os.environ["RELEASE_JSON"])
for asset in data.get("assets", []):
    if asset.get("name") == target and asset.get("state") == "uploaded" and asset.get("size", 0) > 0:
        print(asset.get("browser_download_url", ""))
        break
PY
}

next_patch_tag() {
  local latest
  latest="$(git tag --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)"
  [[ -n "$latest" ]] || {
    printf 'v0.1.0\n'
    return
  }

  python3 - "$latest" <<'PY'
import re
import sys

match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", sys.argv[1])
if not match:
    raise SystemExit("Invalid latest semver tag")
major, minor, patch = map(int, match.groups())
print(f"v{major}.{minor}.{patch + 1}")
PY
}

release_body() {
  local tag="$1"
  local commit="$2"
  cat <<EOF
Automated release for ${tag}.

Source commit: ${commit}

Artifacts:
- ${MAC_ASSET}: built on local macOS by scripts/release.sh
- ${WINDOWS_ASSET}: built by GitHub Actions on Windows
EOF
}

load_token() {
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    return
  fi

  if command -v git >/dev/null 2>&1; then
    GITHUB_TOKEN="$(
      printf 'protocol=https\nhost=github.com\n\n' |
        git credential fill 2>/dev/null |
        awk -F= '/^password=/{print $2; exit}'
    )"
    export GITHUB_TOKEN
  fi

  [[ -n "${GITHUB_TOKEN:-}" ]] || fail "Set GITHUB_TOKEN, or make sure git credential has a GitHub token with repo release permissions."
}

ensure_clean_tracked_tree() {
  git diff --quiet || fail "Tracked files have unstaged changes. Commit or stash them before releasing."
  git diff --cached --quiet || fail "Tracked files have staged changes. Commit or unstage them before releasing."
}

ensure_on_latest_main() {
  log "Fetching ${REMOTE}/${MAIN_BRANCH} and tags..."
  git fetch "$REMOTE" "$MAIN_BRANCH" --tags

  log "Checking out ${MAIN_BRANCH}..."
  git checkout "$MAIN_BRANCH"

  log "Pulling latest ${REMOTE}/${MAIN_BRANCH}..."
  git pull --ff-only "$REMOTE" "$MAIN_BRANCH"

  local local_head remote_head
  local_head="$(git rev-parse "$MAIN_BRANCH")"
  remote_head="$(git rev-parse "${REMOTE}/${MAIN_BRANCH}")"
  [[ "$local_head" == "$remote_head" ]] || fail "${MAIN_BRANCH} is not at ${REMOTE}/${MAIN_BRANCH}."
}

create_or_get_release() {
  local tag="$1"
  local commit="$2"
  local url="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/tags/${tag}"
  local release_json

  if release_json="$(api GET "$url" 2>/dev/null)"; then
    printf '%s' "$release_json"
    return
  fi

  log "Creating GitHub Release ${tag}..."
  python3 - "$tag" "$(release_body "$tag" "$commit")" <<'PY' |
import json
import sys

print(json.dumps({
    "tag_name": sys.argv[1],
    "name": sys.argv[1],
    "body": sys.argv[2],
}))
PY
    api POST "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases" \
      -H "Content-Type: application/json" \
      --data-binary @-
}

upload_asset_clobber() {
  local release_json="$1"
  local file_path="$2"
  local asset_name="$3"
  [[ -f "$file_path" ]] || fail "Asset not found: $file_path"

  local existing_id
  existing_id="$(asset_id_by_name "$release_json" "$asset_name")"
  if [[ -n "$existing_id" ]]; then
    log "Deleting existing release asset ${asset_name}..."
    api DELETE "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/assets/${existing_id}" >/dev/null
  fi

  local upload_url
  upload_url="$(printf '%s' "$release_json" | json_value upload_url | cut -d'{' -f1)"
  log "Uploading ${asset_name}..."
  api POST "${upload_url}?name=${asset_name}" \
    -H "Content-Type: application/octet-stream" \
    --data-binary @"$file_path" >/dev/null
}

wait_for_asset() {
  local tag="$1"
  local asset_name="$2"
  local deadline=$((SECONDS + WAIT_SECONDS))
  local release_json asset_url

  log "Waiting for ${asset_name} on GitHub Release ${tag}..."
  while (( SECONDS < deadline )); do
    release_json="$(api GET "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/tags/${tag}")"
    asset_url="$(asset_url_by_name "$release_json" "$asset_name")"
    if [[ -n "$asset_url" ]]; then
      printf '%s\n' "$asset_url"
      return
    fi
    sleep "$POLL_SECONDS"
  done

  fail "Timed out waiting for ${asset_name}. Check GitHub Actions for the Windows build."
}

main() {
  require_cmd git
  require_cmd curl
  require_cmd python3

  [[ "$(uname -s)" == "Darwin" ]] || fail "Run this script on macOS. The macOS DMG is built locally; Windows is built by GitHub Actions."
  command -v hdiutil >/dev/null 2>&1 || fail "hdiutil is required for macOS DMG creation."

  local tag="${1:-}"
  ensure_clean_tracked_tree
  ensure_on_latest_main
  ensure_clean_tracked_tree

  if [[ -z "$tag" ]]; then
    tag="$(next_patch_tag)"
  fi
  [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "Tag must look like v0.2.7."

  if git rev-parse "$tag" >/dev/null 2>&1; then
    fail "Tag already exists locally: ${tag}"
  fi
  if git ls-remote --exit-code --tags "$REMOTE" "refs/tags/${tag}" >/dev/null 2>&1; then
    fail "Tag already exists on ${REMOTE}: ${tag}"
  fi

  load_token

  log "Running tests..."
  if [[ ! -d .venv ]]; then
    "${PYTHON_BIN:-python3}" -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install -r requirements.txt
  python -m pytest tests -q

  log "Building macOS DMG..."
  bash packaging/macos/package.sh
  hdiutil verify "dist/${MAC_ASSET}"

  local commit
  commit="$(git rev-parse HEAD)"

  log "Tagging ${commit} as ${tag}..."
  git tag "$tag"
  git push "$REMOTE" "$tag"

  local release_json
  release_json="$(create_or_get_release "$tag" "$commit")"
  upload_asset_clobber "$release_json" "dist/${MAC_ASSET}" "$MAC_ASSET"

  local final_release_json mac_url win_url
  final_release_json="$(api GET "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/tags/${tag}")"
  mac_url="$(asset_url_by_name "$final_release_json" "$MAC_ASSET")"
  win_url="$(wait_for_asset "$tag" "$WINDOWS_ASSET")"

  log "Release complete: https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/tag/${tag}"
  log "macOS: ${mac_url}"
  log "Windows: ${win_url}"
}

main "$@"
