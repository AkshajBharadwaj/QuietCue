#!/usr/bin/env bash
# One-command local QuietCue launcher for macOS, Linux, and WSL.
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ANDROID_DIR="$REPOSITORY_ROOT/frontend/android"

classifier="demo"
classifier_explicit=false
alert_profile="home"
bind_host="127.0.0.1"
bind_host_explicit=false
audio_port="8765"
state_port="8787"
speech_model=""
showcase=false
exit_after_showcase=false
install_android=false
skip_android=false
live_hardware=false
uno_host="${UNO_Q_HOST:-}"
hub_address=""
input_device="auto"
hub_pid=""
showcase_directory=""

usage() {
    printf '%s\n' \
        "Usage: ./scripts/run_demo.sh [options]" \
        "" \
        "Options:" \
        "  --live                     Start real ONNX inference plus the Uno Q mic/haptics over SSH" \
        "  --uno-host TARGET          Uno Q SSH target (default: UNO_Q_HOST, mDNS, or one active Tailscale Linux peer)" \
        "  --hub-address HOST         Address the Uno Q uses to reach this computer (normally auto-detected)" \
        "  --input-device DEVICE      Uno Q ALSA input (default: auto-detect a USB capture device)" \
        "  --showcase                 Replay a deterministic fire-alarm alert" \
        "  --exit-after-showcase      Stop after the automated showcase completes" \
        "  --install-android          Build/install the Android app when adb is connected" \
        "  --skip-android             Do not configure or launch a connected Android device" \
        "  --classifier MODE          demo, yamnet, or onnx (default: demo)" \
        "  --profile PROFILE          home, work, driving, sleep, or emergency" \
        "  --speech-model MODEL       Optional local Faster-Whisper model" \
        "  --bind-host HOST           Hub/state bind address (default: 127.0.0.1)" \
        "  --port PORT                Audio TCP port (default: 8765)" \
        "  --state-port PORT          State HTTP port (default: 8787)" \
        "  -h, --help                 Show this help"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --live|--live-hardware) live_hardware=true; shift ;;
        --uno-host) uno_host="${2:?Missing Uno Q SSH target}"; shift 2 ;;
        --hub-address) hub_address="${2:?Missing hub address}"; shift 2 ;;
        --input-device) input_device="${2:?Missing input device}"; shift 2 ;;
        --showcase) showcase=true; shift ;;
        --exit-after-showcase) exit_after_showcase=true; shift ;;
        --install-android) install_android=true; shift ;;
        --skip-android) skip_android=true; shift ;;
        --classifier) classifier="${2:?Missing classifier}"; classifier_explicit=true; shift 2 ;;
        --profile) alert_profile="${2:?Missing profile}"; shift 2 ;;
        --speech-model) speech_model="${2:?Missing speech model}"; shift 2 ;;
        --bind-host) bind_host="${2:?Missing bind host}"; bind_host_explicit=true; shift 2 ;;
        --port) audio_port="${2:?Missing audio port}"; shift 2 ;;
        --state-port) state_port="${2:?Missing state port}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ "$live_hardware" == true ]]; then
    if [[ "$classifier_explicit" == false ]]; then
        classifier="onnx"
    fi
    if [[ "$bind_host_explicit" == false ]]; then
        bind_host="0.0.0.0"
    fi
    [[ "$classifier" != "demo" ]] || {
        printf '%s\n' '--live requires a real classifier; use onnx (the default) or yamnet.' >&2
        exit 2
    }
    [[ "$showcase" == false ]] || {
        printf '%s\n' '--live and --showcase are separate modes and cannot be combined.' >&2
        exit 2
    }
fi

case "$classifier" in demo|yamnet|onnx) ;; *) printf 'Invalid classifier: %s\n' "$classifier" >&2; exit 2 ;; esac
case "$alert_profile" in home|work|driving|sleep|emergency) ;; *) printf 'Invalid profile: %s\n' "$alert_profile" >&2; exit 2 ;; esac
[[ "$audio_port" =~ ^[0-9]+$ ]] || { printf 'Invalid audio port\n' >&2; exit 2; }
[[ "$state_port" =~ ^[0-9]+$ ]] || { printf 'Invalid state port\n' >&2; exit 2; }

cleanup() {
    if [[ -n "$hub_pid" ]] && kill -0 "$hub_pid" 2>/dev/null; then
        kill "$hub_pid" 2>/dev/null || true
        wait "$hub_pid" 2>/dev/null || true
    fi
    if [[ -n "$showcase_directory" && -d "$showcase_directory" ]]; then
        rm -rf -- "$showcase_directory"
    fi
}
trap cleanup EXIT INT TERM

discover_uno_host() {
    if [[ -n "$uno_host" ]]; then
        if [[ "$uno_host" == *@* ]]; then
            printf '%s\n' "$uno_host"
        else
            printf 'arduino@%s\n' "$uno_host"
        fi
        return
    fi

    if command -v dscacheutil >/dev/null 2>&1 && \
        dscacheutil -q host -a name uno-q.local 2>/dev/null | grep -q '^ip_address:'; then
        printf '%s\n' 'arduino@uno-q.local'
        return
    fi

    if command -v tailscale >/dev/null 2>&1; then
        tailscale_candidates="$(
            tailscale status 2>/dev/null |
                awk '$4 == "linux" && $5 !~ /^offline/ { print $1 }'
        )"
        tailscale_count="$(printf '%s\n' "$tailscale_candidates" | awk 'NF { count++ } END { print count + 0 }')"
        if [[ "$tailscale_count" == "1" ]]; then
            printf 'arduino@%s\n' "$tailscale_candidates"
            return
        fi
    fi

    printf '%s\n' \
        'Could not uniquely find the Uno Q. Rerun with --uno-host arduino@HOST once.' >&2
    return 1
}

discover_hub_address() {
    if [[ -n "$hub_address" ]]; then
        printf '%s\n' "$hub_address"
        return
    fi

    uno_address="${uno_host#*@}"
    if [[ "$uno_address" == 100.* ]] && command -v tailscale >/dev/null 2>&1; then
        detected="$(tailscale ip -4 2>/dev/null | awk 'NF { print; exit }')"
        if [[ -n "$detected" ]]; then
            printf '%s\n' "$detected"
            return
        fi
    fi

    if command -v ipconfig >/dev/null 2>&1; then
        detected="$(ipconfig getifaddr en0 2>/dev/null || true)"
        if [[ -n "$detected" ]]; then
            printf '%s\n' "$detected"
            return
        fi
    fi

    if command -v hostname >/dev/null 2>&1; then
        detected="$(hostname -I 2>/dev/null | awk '{ print $1 }' || true)"
        if [[ -n "$detected" ]]; then
            printf '%s\n' "$detected"
            return
        fi
    fi

    printf '%s\n' \
        'Could not determine this computer address. Rerun with --hub-address HOST.' >&2
    return 1
}

runtime_root="$REPOSITORY_ROOT"
if [[ "$(uname -s)" == "Darwin" ]] && \
    [[ "$(stat -f '%Sf' "$REPOSITORY_ROOT/backend/requirements-onnx.txt" 2>/dev/null || true)" == *dataless* ]]; then
    runtime_root="${QUIETCUE_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/Library/Caches}/quietcue/runtime-source}"
    if [[ ! -d "$runtime_root/.git" ]]; then
        repository_url="${QUIETCUE_REPO_URL:-https://github.com/AkshajBharadwaj/quietcue}"
        printf 'Workspace runtime files are iCloud placeholders; creating local runtime cache...\n'
        git clone --depth 1 "$repository_url" "$runtime_root"
    else
        printf 'Workspace runtime files are iCloud placeholders; using local runtime cache at %s.\n' \
            "$runtime_root"
    fi
fi

cd "$runtime_root"
command -v python3 >/dev/null 2>&1 || { printf 'Python 3 is required.\n' >&2; exit 1; }

if [[ -n "${QUIETCUE_VENV_DIR:-}" ]]; then
    venv_dir="$QUIETCUE_VENV_DIR"
elif [[ "$(uname -s)" == "Darwin" ]]; then
    # Repositories under Documents may be managed by iCloud. Virtualenv files
    # there can become "dataless" and make imports/pip hang while macOS tries
    # to rehydrate thousands of tiny files. Keep the disposable runtime cache
    # outside the synced workspace.
    python_tag="$(python3 -c 'import sys; print(f"py{sys.version_info.major}{sys.version_info.minor}")')"
    venv_dir="${XDG_CACHE_HOME:-$HOME/Library/Caches}/quietcue/venv-$python_tag"
else
    venv_dir="$REPOSITORY_ROOT/.venv"
fi
venv_python="$venv_dir/bin/python"
if [[ ! -x "$venv_python" ]]; then
    printf 'Creating runtime environment at %s...\n' "$venv_dir"
    python3 -m venv "$venv_dir"
fi

requirements=""
case "$classifier" in
    yamnet) requirements="backend/requirements.txt" ;;
    onnx) requirements="backend/requirements-onnx.txt" ;;
esac
if [[ -n "$requirements" ]]; then
    printf 'Ensuring %s dependencies are installed...\n' "$classifier"
    "$venv_python" -m pip install --quiet --upgrade pip
    "$venv_python" -m pip install --quiet -r "$requirements"
fi
if [[ -n "$speech_model" ]]; then
    printf 'Ensuring local speech dependencies are installed...\n'
    "$venv_python" -m pip install --quiet --upgrade pip
    "$venv_python" -m pip install --quiet -r backend/requirements-speech.txt
fi

pairing_token="${QUIETCUE_PAIRING_TOKEN:-}"
pairing_token_generated=false
if [[ -z "$pairing_token" && "$live_hardware" == true ]]; then
    pairing_token="$("$venv_python" -c 'import secrets; print(secrets.token_urlsafe(24))')"
    pairing_token_generated=true
fi
if [[ -z "$pairing_token" && "$live_hardware" == false ]]; then
    printf 'Warning: QUIETCUE_PAIRING_TOKEN is unset; use only on a trusted development network.\n' >&2
fi
if [[ "$bind_host" == "0.0.0.0" ]]; then
    printf 'Warning: the hub is exposed to the local network.\n' >&2
fi

if [[ "$skip_android" == false ]] && command -v adb >/dev/null 2>&1 && adb get-state >/dev/null 2>&1; then
    if [[ "$install_android" == true ]]; then
        printf 'Building and installing the Android companion...\n'
        (cd "$ANDROID_DIR" && ./gradlew installDebug)
    fi
    adb reverse "tcp:$state_port" "tcp:$state_port" >/dev/null
    if adb shell pm path com.quietcue.app >/dev/null 2>&1; then
        adb shell monkey -p com.quietcue.app -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
        printf 'Android companion connected through adb reverse on port %s.\n' "$state_port"
    else
        printf 'Android device found, but QuietCue is not installed; rerun with --install-android.\n'
    fi
fi

hub_args=(
    -m backend.app.hub_server
    --host "$bind_host"
    --port "$audio_port"
    --state-host "$bind_host"
    --state-port "$state_port"
    --classifier "$classifier"
    --profile "$alert_profile"
    --pairing-token "$pairing_token"
)
if [[ -n "$speech_model" ]]; then
    hub_args+=(--speech-model "$speech_model" --speech-device cpu --speech-compute-type int8)
fi

printf 'Starting QuietCue: classifier=%s profile=%s audio=%s:%s state=%s:%s\n' \
    "$classifier" "$alert_profile" "$bind_host" "$audio_port" "$bind_host" "$state_port"
"$venv_python" "${hub_args[@]}" &
hub_pid="$!"

ready=false
for _ in {1..100}; do
    if ! kill -0 "$hub_pid" 2>/dev/null; then
        wait "$hub_pid"
        exit 1
    fi
    if "$venv_python" -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$state_port/health', timeout=.2).read()" \
        >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 0.05
done
[[ "$ready" == true ]] || { printf 'Hub did not become ready.\n' >&2; exit 1; }

printf 'QuietCue is ready. State: http://127.0.0.1:%s/api/state\n' "$state_port"

if [[ "$live_hardware" == true ]]; then
    uno_host="$(discover_uno_host)"
    hub_address="$(discover_hub_address)"
    printf 'Starting live Uno Q demo: board=%s hub=%s:%s microphone=%s\n' \
        "$uno_host" "$hub_address" "$audio_port" "$input_device"
    if [[ "$pairing_token_generated" == true ]]; then
        printf 'Temporary pairing protection configured automatically.\n'
    fi
    printf 'SSH may ask for the Uno Q password. Press Ctrl+C once to stop the entire demo.\n'

    ssh "$uno_host" bash -s -- \
        "$hub_address:$audio_port" "$input_device" "$pairing_token" <<'QUIETCUE_REMOTE'
set -euo pipefail

hub_endpoint="$1"
input_device="$2"
pairing_token="${3:-}"
project_dir="${QUIETCUE_PROJECT_DIR:-$HOME/projects/QuietCue}"

cd "$project_dir"

if [[ "$input_device" == "auto" ]]; then
    capture_hardware="$(arecord -l 2>/dev/null || true)"
    card_name="$(
        printf '%s\n' "$capture_hardware" |
            awk '/^card [0-9]+:/ {
                     card=$2
                     sub(/:$/, "", card)
                     if (first == "") first=card
                     if (tolower($0) ~ /usb/) { found=card; print card; exit }
                 }
                 END { if (found == "" && first != "") print first }'
    )"
    if [[ -z "$card_name" ]]; then
        printf '%s\n' 'No ALSA capture microphone was found on the Uno Q.' >&2
        exit 1
    fi
    input_device="plughw:CARD=$card_name,DEV=0"
fi

printf 'Uno Q microphone: %s\n' "$input_device"
systemctl --user stop quietcue-client.service 2>/dev/null || true

exec env \
    QUIETCUE_ENV_FILE=/dev/null \
    QUIETCUE_PC_HUB="$hub_endpoint" \
    QUIETCUE_PAIRING_TOKEN="$pairing_token" \
    QUIETCUE_ALSA_DEVICE="$input_device" \
    ./scripts/run_uno_q_client.sh
QUIETCUE_REMOTE
    exit $?
fi

if [[ "$showcase" == true ]]; then
    [[ "$classifier" == "demo" ]] || { printf '--showcase requires --classifier demo.\n' >&2; exit 2; }
    showcase_directory="$(mktemp -d "${TMPDIR:-/tmp}/quietcue-showcase.XXXXXX")"
    fire_wav="$showcase_directory/fire-alarm.wav"
    "$venv_python" scripts/generate_demo_audio.py fire_alarm "$fire_wav" --duration 1

    printf 'Showcase: emitting a configured emergency fire-alarm event...\n'
    "$venv_python" -m uno_q.linux.transport.hub_client "$fire_wav" --pc "127.0.0.1:$audio_port" --compact
    if [[ "$exit_after_showcase" == true ]]; then
        exit 0
    fi
fi

printf 'Press Ctrl+C to stop QuietCue.\n'
wait "$hub_pid"
