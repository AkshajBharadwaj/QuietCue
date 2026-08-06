#!/usr/bin/env bash
# One-time setup for the Arduino Uno Q (Linux side). Run this ON the board:
#
#   ssh arduino@<uno-q-tailscale-ip>
#   QUIETCUE_REPO_URL=<git-url> ./setup_uno_q.sh     # first time, clones the repo
#   ~/projects/QuietCue/scripts/setup_uno_q.sh       # later, re-checks the environment
#
# This script performs read-only dependency checks. Model dependencies belong on
# the connected phone/computer inference hub, not on the Uno Q.
set -euo pipefail

PROJECT_DIR="${QUIETCUE_PROJECT_DIR:-$HOME/projects/QuietCue}"

echo "== QuietCue Uno Q setup =="

# 1. Repository
if [ ! -d "$PROJECT_DIR" ]; then
    if [ -n "${QUIETCUE_REPO_URL:-}" ]; then
        mkdir -p "$(dirname "$PROJECT_DIR")"
        git clone "$QUIETCUE_REPO_URL" "$PROJECT_DIR"
    else
        echo "ERROR: $PROJECT_DIR does not exist and QUIETCUE_REPO_URL is not set." >&2
        echo "Set QUIETCUE_REPO_URL=<git-url> and re-run to clone." >&2
        exit 1
    fi
fi
echo "repo: $PROJECT_DIR"

# 2. Python (3.10+ recommended)
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on the board." >&2
    exit 1
fi
python3 --version

# 3. ALSA capture tool used by the microphone source
if ! command -v arecord >/dev/null 2>&1; then
    echo "WARNING: arecord not found. Install alsa-utils (sudo apt-get install alsa-utils)." >&2
else
    echo "arecord: $(command -v arecord)"
fi

# 4. Microphone visibility check (safe, read-only)
cd "$PROJECT_DIR"
echo
echo "-- ALSA capture hardware --"
python3 -m uno_q.linux.transport.hub_client --list-microphones || true

cat <<'EOF'

Setup complete. Next steps:
  1. Export the shared development token (same value as on the hub):
       export QUIETCUE_PAIRING_TOKEN='<shared-development-token>'
  2. Run a 3-second microphone signal health check (no classification):
       python3 -m uno_q.linux.transport.hub_client --microphone \
         --input-device 'plughw:CARD=Microphone,DEV=0' --max-chunks 6 --compact
  3. Stream to the hub with scripts/deploy_uno_q.sh --local (see that script).
EOF
