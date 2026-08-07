#!/usr/bin/env bash
# One-command local QuietCue launcher for macOS, Linux, and WSL.
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ANDROID_DIR="$REPOSITORY_ROOT/frontend/android"

classifier="demo"
alert_profile="home"
bind_host="127.0.0.1"
audio_port="8765"
state_port="8787"
speech_model="base.en"
speech_disabled=0
showcase=false
exit_after_showcase=false
install_android=false
skip_android=false
discovery_state="$REPOSITORY_ROOT/.quietcue/discovery_state.json"
hub_pid=""
showcase_directory=""

usage() {
    printf '%s\n' \
        "Usage: ./scripts/run_demo.sh [options]" \
        "" \
        "Options:" \
        "  --showcase                 Replay a fire alarm and create a Sound Scout candidate" \
        "  --exit-after-showcase      Stop after the automated showcase completes" \
        "  --install-android          Build/install the Android app when adb is connected" \
        "  --skip-android             Do not configure or launch a connected Android device" \
        "  --classifier MODE          demo, yamnet, or onnx (default: demo)" \
        "  --profile PROFILE          home, work, driving, sleep, or emergency" \
        "  --speech-model MODEL       Local Faster-Whisper model (default: base.en)" \
        "  --no-speech                Disable local speech transcription" \
        "  --bind-host HOST           Hub/state bind address (default: 127.0.0.1)" \
        "  --port PORT                Audio TCP port (default: 8765)" \
        "  --state-port PORT          State HTTP port (default: 8787)" \
        "  --discovery-state PATH     Persistent metadata path" \
        "  -h, --help                 Show this help"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --showcase) showcase=true; shift ;;
        --exit-after-showcase) exit_after_showcase=true; shift ;;
        --install-android) install_android=true; shift ;;
        --skip-android) skip_android=true; shift ;;
        --classifier) classifier="${2:?Missing classifier}"; shift 2 ;;
        --profile) alert_profile="${2:?Missing profile}"; shift 2 ;;
        --speech-model) speech_model="${2:?Missing speech model}"; shift 2 ;;
        --no-speech) speech_disabled=1; speech_model=""; shift ;;
        --bind-host) bind_host="${2:?Missing bind host}"; shift 2 ;;
        --port) audio_port="${2:?Missing audio port}"; shift 2 ;;
        --state-port) state_port="${2:?Missing state port}"; shift 2 ;;
        --discovery-state) discovery_state="${2:?Missing discovery state path}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

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

cd "$REPOSITORY_ROOT"
command -v python3 >/dev/null 2>&1 || { printf 'Python 3 is required.\n' >&2; exit 1; }

venv_python="$REPOSITORY_ROOT/.venv/bin/python"
if [[ ! -x "$venv_python" ]]; then
    printf 'Creating .venv...\n'
    python3 -m venv "$REPOSITORY_ROOT/.venv"
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
if [[ "$speech_disabled" -eq 0 && -n "$speech_model" ]]; then
    printf 'Ensuring local speech dependencies are installed...\n'
    "$venv_python" -m pip install --quiet --upgrade pip
    "$venv_python" -m pip install --quiet -r backend/requirements-speech.txt
fi

if [[ -z "${QUIETCUE_PAIRING_TOKEN:-}" ]]; then
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
    --discovery-state "$discovery_state"
)
if [[ "$speech_disabled" -eq 0 && -n "$speech_model" ]]; then
    hub_args+=(--speech-model "$speech_model" --speech-device cpu --speech-compute-type int8)
else
    hub_args+=(--no-speech)
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

if [[ "$showcase" == true ]]; then
    [[ "$classifier" == "demo" ]] || { printf '--showcase requires --classifier demo.\n' >&2; exit 2; }
    showcase_directory="$(mktemp -d "${TMPDIR:-/tmp}/quietcue-showcase.XXXXXX")"
    fire_wav="$showcase_directory/fire-alarm.wav"
    vacuum_wav="$showcase_directory/vacuum-cleaner.wav"
    "$venv_python" scripts/generate_demo_audio.py fire_alarm "$fire_wav" --duration 1
    "$venv_python" scripts/generate_demo_audio.py vacuum_cleaner "$vacuum_wav" --duration 1

    printf 'Showcase 1/2: emitting a configured emergency fire-alarm event...\n'
    "$venv_python" -m uno_q.linux.transport.hub_client "$fire_wav" --pc "127.0.0.1:$audio_port" --compact

    printf 'Showcase 2/2: emitting three separate unmapped vacuum episodes...\n'
    for episode in 1 2 3; do
        "$venv_python" -m uno_q.linux.transport.hub_client "$vacuum_wav" --pc "127.0.0.1:$audio_port" --compact
        if [[ "$episode" -lt 3 ]]; then sleep 3.1; fi
    done
    printf 'Sound Scout is ready for review in Android. Add, teach, or ignore the Vacuum cleaner card.\n'
    if [[ "$exit_after_showcase" == true ]]; then
        exit 0
    fi
fi

printf 'Press Ctrl+C to stop QuietCue.\n'
wait "$hub_pid"
