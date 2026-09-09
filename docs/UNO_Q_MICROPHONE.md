# Uno Q microphone to connected inference

QuietCue captures mono PCM from the microphone connected to the UNO Q and sends
it to one reachable Samsung/PC inference hub. The board does not classify
environmental sounds. It adds only signal-health metadata (RMS, peak level, and
voice activity), receives profile-approved alert commands, and forwards their
haptic patterns through Arduino Bridge to the STM32.

```text
microphone -> UNO Q PCM stream -> Samsung/PC model -> event/profile decision
           <- detection_result <-                  -> UNO Q -> STM32 vibration
```

## One-command live demo

After the one-time Uno Q setup and App Lab firmware installation, run this on
the computer:

```bash
./scripts/run_demo.sh --live
```

This starts the real ONNX classifier, binds the hub to a reachable interface,
finds one active Uno Q through `UNO_Q_HOST`, mDNS, or Tailscale, selects a USB
ALSA capture device, and starts microphone streaming plus physical haptics over
SSH. No pairing token is required for a short demo on a trusted network. SSH may
ask for the board password. If automatic discovery is ambiguous, specify the
board once with `--uno-host arduino@HOST`; use `--input-device` only when the
automatic USB selection is wrong.

The prototype microphone was detected as:

- USB device: `31b2:0011 DCMT Technology USB Condenser Microphone`
- ALSA card: `Microphone`
- capture endpoint: `plughw:CARD=Microphone,DEV=0`
- native input: mono `S16_LE`, 44.1–192 kHz

`plughw` performs the rate conversion to 16 kHz. `arecord` writes into a pipe;
QuietCue does not persist raw audio on the board.

## Check the microphone

```bash
python3 -m uno_q.linux.transport.hub_client --list-microphones

python3 -m uno_q.linux.transport.hub_client \
  --microphone \
  --input-device 'plughw:CARD=Microphone,DEV=0' \
  --max-chunks 6 \
  --compact
```

The second command is a three-second signal check only. Speaking near the mic
should raise RMS/peak values and usually set `voice=True`; it does not infer an
event or drive the motor.

## Start a PC hub

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-onnx.txt

export QUIETCUE_PAIRING_TOKEN='<development-token>'
python -m backend.app.hub_server \
  --host 0.0.0.0 \
  --classifier onnx \
  --profile home
```

The checked-in W8A8 ONNX model is the default connected classifier. On a
Snapdragon PC, `QUIETCUE_ONNX_TARGET=auto` tries the QNN execution provider and
falls back to CPU. On other computers it uses ONNX Runtime CPU. YAMNet remains a
baseline rather than a safety-certified classifier.

Bind to `0.0.0.0` only on a trusted LAN or Tailscale network and use a pairing
token; the current raw TCP development protocol is not encrypted.

## Run the managed board client

Create `~/.quietcue_env` on the UNO Q:

```bash
QUIETCUE_PC_HUB=<computer-host>:8765
# QUIETCUE_PHONE_HUB=<protocol-compatible-phone-host>:8765
QUIETCUE_PAIRING_TOKEN=<same-development-token>
QUIETCUE_ALSA_DEVICE=plughw:CARD=Microphone,DEV=0
QUIETCUE_DEVICE_ID=uno-q-dev
```

Then deploy on the board:

```bash
./scripts/deploy_uno_q.sh --local
systemctl --user status quietcue-client.service
journalctl --user -u quietcue-client.service -f
```

The service streams microphone chunks, reconnects after network/hub/microphone
failures, dispatches returned alerts to the real App Lab Bridge, and reports
haptic delivery back to the hub. During a hub outage it does not infer events or
produce safety haptics locally.

For a foreground diagnostic:

```bash
python3 -m uno_q.linux.transport.hub_client \
  --microphone \
  --input-device 'plughw:CARD=Microphone,DEV=0' \
  --pc '<computer-host>:8765' \
  --pairing-token "$QUIETCUE_PAIRING_TOKEN" \
  --chunk-ms 1000 \
  --haptics \
  --compact
```

Automatic routing prefers a reachable computer and can fail over to a
protocol-compatible `--phone` endpoint. The Samsung companion hosts that audio
inference server with quantized YAMNet and an optional, lazy Whisper ONNX speech
worker.

## Speech behavior

Voice-activity metadata from the board and the hub's YAMNet speech-family score
gate the connected speech path. The computer uses Faster-Whisper; the Samsung
hub uses staged Whisper ONNX assets. Both buffer at most four seconds in memory,
transcribe on a worker that cannot block environmental classification, fuzzy-
match configured phrases, apply the active profile, and return any resulting
haptic command. Runtime responses and telemetry never include transcript text.
