#!/usr/bin/env bash
# Start the QuietCue hub on the Mac for the iPhone demo.
#
# The iPhone app plays the wearable (microphone in, vibration out) and the
# companion dashboard; this script runs the inference hub bound to every
# interface so the phone can reach it over Wi-Fi.
#
# Usage:
#   ./scripts/run_ios_demo.sh                 # YAMNet ONNX classifier, Home profile
#   ./scripts/run_ios_demo.sh --classifier demo   # synthetic-tone classifier for dry runs
#   QUIETCUE_PAIRING_TOKEN=secret ./scripts/run_ios_demo.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python3 -c "import onnxruntime, onnx, numpy" 2>/dev/null; then
  echo "Installing the hub's Python dependencies (onnxruntime, onnx, numpy)…"
  python3 -m pip install onnxruntime onnx numpy
fi

# The float YAMNet export is not checked in; fetch it so confidences are
# continuous instead of the quantized model's coarse ladder.
if [ ! -f models/source/yamnet-onnx-float/yamnet-onnx-float/yamnet.onnx ]; then
  ./scripts/fetch_models.sh || echo "Could not download the float model; falling back to the checked-in w8a8 export."
fi

# macOS ships bash 3.2, where an empty array trips `set -u`; use a plain string.
speech_flag="--no-speech"
if python3 -c "import faster_whisper" 2>/dev/null; then
  speech_flag=""
else
  echo "faster-whisper is not installed; speech and name detection stay off (pip install faster-whisper to enable)."
fi

lan_ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
if [ -z "$lan_ip" ]; then
  lan_ip="<this Mac's Wi-Fi IP; see System Settings > Wi-Fi > Details>"
fi
echo
echo "QuietCue hub for the iPhone demo"
echo "  Enter this address in the app's Mac hub card: $lan_ip"
echo "  Audio stream: port 8765   Dashboard API: port 8787"
echo "  Both devices must be on the same Wi-Fi. Allow incoming connections if macOS asks."
echo

exec python3 -m backend.app.hub_server \
  --host 0.0.0.0 \
  --state-host 0.0.0.0 \
  --classifier onnx \
  --profile home \
  ${speech_flag:+"$speech_flag"} \
  "$@"
