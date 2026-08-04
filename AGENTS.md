# QuietCue — AGENTS.md

## Purpose

QuietCue is a multi-device accessibility system for deaf and hard-of-hearing users. It detects important environmental sounds and speech-related events, applies user-specific context and priority rules, and delivers clear haptic alerts through an Arduino Uno Q-based wearable.

This file defines the project architecture, development rules, implementation priorities, and tool usage expectations for all developers and coding agents working in this repository.

---

## Product Goal

Build a reliable, low-latency system that can:

1. Capture environmental audio near the user.
2. Detect important events such as alarms, doorbells, horns, a name being called, or a baby crying.
3. Apply the active user profile and context rules.
4. Send a compact alert command to the wearable.
5. Produce a distinguishable haptic pattern.
6. Show the detected event, confidence, latency, and device status in the companion app.

The core demo must work locally on the Snapdragon X Elite Copilot+ PC and Arduino Uno Q without depending on a cloud LLM.

---

## Non-Negotiable Architecture

```text
Environment
    |
    v
Microphone connected to Uno Q
    |
    v
Uno Q Linux side
- audio capture
- buffering / preprocessing
- network transport
    |
    | Wi-Fi during the hackathon
    v
Snapdragon X Elite PC
- sound classification
- speech transcription when needed
- profile and context logic
- alert prioritization
- dashboard / app backend
    |
    | compact event command
    v
Uno Q Linux side
    |
    | Arduino RPC
    v
STM32 microcontroller
- deterministic motor timing
- button input
- LED / hardware status
    |
    v
Haptic feedback
```

### Core design decisions

- Use **Wi-Fi**, not Bluetooth audio, for the first audio-streaming implementation.
- Use Bluetooth Low Energy only later for small commands, configuration, or a more wearable production design.
- Keep safety-critical detection local.
- Treat the phone as an optional companion, not a required part of the core demo.
- Do not use SSH as the runtime protocol. SSH is only for development, deployment, and debugging.
- Do not run heavy coding agents or large development tooling on the Uno Q.

---

## Device Responsibilities

### Snapdragon X Elite PC

The Snapdragon PC is the primary intelligence and orchestration layer.

Responsibilities:

- Run the main environmental sound classifier.
- Run speech-to-text only when speech is detected or needed.
- Detect a configured name or phrase from transcripts.
- Apply profile, location, time, and priority rules.
- Select the haptic category and motor pattern.
- Host the backend API and dashboard.
- Log events, confidence, latency, and device health.
- Run model conversion, profiling, and optimization workflows.

Do not move the primary model off the Snapdragon PC until the complete end-to-end system is working and benchmarked.

### Arduino Uno Q — Linux side

Responsibilities:

- Capture microphone audio.
- Normalize, buffer, and packetize audio.
- Stream audio to the Snapdragon PC.
- Receive alert commands.
- Communicate with the STM32 through Arduino RPC.
- Report connection and device health.
- Optionally run lightweight preprocessing or a small local classifier later.

The Uno Q Linux side may eventually run:

- voice activity detection;
- wake-word or name trigger prefilters;
- a small sound-event classifier;
- emergency fallback logic.

These are stretch goals, not MVP requirements.

### Arduino Uno Q — STM32 side

Responsibilities:

- Drive the haptic motor through a proper transistor or MOSFET driver.
- Execute deterministic vibration timing.
- Read the acknowledge button.
- Control status LEDs.
- Continue a critical haptic pattern even if the Linux process briefly stalls.

The STM32 should not run networking, speech transcription, or large ML models.

### Phone companion

Optional responsibilities:

- User profile editing.
- Sound library configuration.
- Haptic preview.
- Recent event history.
- Device status.
- Profile switching.

The phone must not be required for the main hackathon demo.

---

## Runtime Protocols

### Audio transport

Current engineering default:

- Mono audio.
- 16 kHz sample rate.
- 16-bit PCM.
- Audio sent in 0.5- to 1-second chunks.
- WebSocket or raw TCP over Wi-Fi.
- Sequence numbers and timestamps on every chunk.

These values are defaults, not hard requirements. Change them only after measuring accuracy, latency, and bandwidth.

Example envelope:

```json
{
  "sequence": 184,
  "captured_at_ms": 1785798400123,
  "sample_rate": 16000,
  "channels": 1,
  "encoding": "pcm_s16le"
}
```

### Alert command

The Snapdragon PC sends compact event data rather than audio back to the Uno Q.

```json
{
  "event": "fire_alarm",
  "category": "emergency",
  "confidence": 0.97,
  "pattern": "urgent_repeat",
  "requires_ack": true,
  "event_id": "evt_01J..."
}
```

### Haptic categories

Keep the haptic language simple:

- **Informational:** short pulse or two short pulses.
- **Attention:** one longer pulse.
- **Emergency:** repeated urgent pulses until acknowledged or timed out.

Do not create a unique rhythm for every sound. The app provides the exact event label; the haptic pattern communicates urgency and category.

---

## App Features

### Profiles

Profiles are a core product feature, not a stretch feature.

Each profile may define:

- enabled sounds;
- disabled sounds;
- confidence thresholds;
- alert priority;
- haptic category;
- quiet hours;
- whether acknowledgement is required;
- optional location or activity context.

Recommended initial profiles:

- Home
- Work / School
- Driving / Transit
- Sleep / Night
- Emergency

### Sound library

Initial event classes should focus on a small, high-value set:

- fire or smoke alarm;
- doorbell or knock;
- car horn;
- siren;
- name called;
- baby crying;
- kitchen timer;
- phone ringing.

Do not add many classes before the first set is reliable.

### Dashboard

The demo dashboard should show:

- active profile;
- current microphone and Uno Q connection state;
- latest detected event;
- confidence;
- end-to-end latency;
- haptic pattern sent;
- acknowledgement state;
- recent event history.

---

## Model Strategy

### Separate environmental sound detection from speech processing

Do not use Whisper as the environmental sound classifier.

```text
Audio
  |-- Environmental classifier -> alarm, doorbell, horn, crying, siren
  `-- Speech path -> transcript -> configured name or phrase detection
```

The environmental classifier should remain active continuously. The speech pipeline should be gated so it only runs when speech is likely present or when the active profile needs it.

### Baseline first, optimization second

Required order:

1. Prove normal model inference on the Snapdragon PC.
2. Integrate it into the live audio pipeline.
3. Complete the haptic round trip.
4. Measure the baseline.
5. Use QUAD to convert, quantize, profile, and optimize.

Do not spend the first development day optimizing an unproven model.

---

## QUAD Usage

QUAD is a high-priority optimization and deployment tool for this project.

Use it to:

- detect the Snapdragon and Uno Q hardware;
- inspect available CPU, GPU, NPU, runtimes, and SDK status;
- convert ONNX, PyTorch, TensorFlow, or TFLite models;
- quantize the selected classifier, preferably testing INT8;
- profile latency, memory, power, and utilization;
- compare CPU, GPU, and NPU execution;
- generate runnable inference code;
- profile a model on a connected board over SSH;
- document why the final execution target was selected.

Recommended sequence:

```bash
quad-client detect
quad-client doctor
```

Then, from Claude Code or another supported MCP client:

```text
/quad-quickstart
/quad-aihub
/quad-convert
/quad-profile
/quad-orchestrate
/quad-codegen
```

Example board profiling flow after a working model exists:

```bash
quad-client profile-device \
  --convert \
  --model ./models/sound_classifier.onnx \
  --source-format onnx \
  --quantization int8 \
  --transport ssh \
  --host arduino@<uno-q-tailscale-ip>
```

### QUAD output expectations

Store the following under `docs/benchmarks/`:

- converted model details;
- quantization choice;
- target hardware;
- latency report;
- memory report;
- power or efficiency report when available;
- CPU/GPU/NPU comparison;
- final deployment recommendation;
- generated runner notes.

Do not claim NPU acceleration until it is verified by a real profile or runtime report.

---

## Qualcomm AI Hub and GenieX

Use Qualcomm AI Hub to find compatible audio, speech, or embedding models and to accelerate model conversion and deployment.

Use GenieX only when it adds direct value, such as:

- evaluating a small speech or language model locally;
- running a local model behind a stable service interface;
- comparing GGUF-capable local models for optional profile or context features.

GenieX is not required for the first end-to-end QuietCue demo.

---

## Cirrascale / Cloud AI

Cirrascale is optional and must not be placed in the safety-critical alert path.

Appropriate uses:

- convert natural-language user preferences into a profile;
- summarize alert history;
- explain why an alert was triggered;
- suggest profile changes;
- perform non-urgent contextual reasoning;
- prototype a larger model before replacing it with a local alternative.

Inappropriate uses:

- fire-alarm detection;
- horn or siren detection;
- primary haptic triggering;
- anything that must continue working without internet;
- continuous raw-audio upload.

Assume cloud credits and token usage are **limited unless the account dashboard or event organizers explicitly state otherwise**. Never design the core experience around unlimited tokens.

Keep cloud AI behind a service interface so it can be disabled, replaced, cached, rate-limited, or swapped without changing the rest of the application.

---

## Arduino RPC

Use Arduino RPC to separate Linux-side orchestration from STM32-side hardware control.

Suggested RPC commands:

```text
play_haptic(pattern, intensity, repeat_count)
stop_haptic()
set_status_led(state)
get_button_state()
get_firmware_version()
health_check()
```

The Linux process should send semantic commands such as `urgent_repeat`, not raw pin toggles.

The microcontroller should own exact motor timing.

---

## Hardware Rules

Required prototype hardware:

- Arduino Uno Q;
- microphone connected to the Uno Q;
- 3 V coin vibration motor or other suitable haptic actuator;
- MOSFET or transistor motor driver;
- flyback diode when required by the selected actuator circuit;
- shared ground;
- acknowledge button;
- optional status LED;
- breadboard and jumper wires for prototyping.

Never power the vibration motor directly from a GPIO pin.

Validate the microphone interface supported by the Uno Q before finalizing the module. Prefer a clean digital audio path when supported; use a USB microphone as a fallback for the earliest proof of concept.

---

## Performance and Evaluation

Technical evaluation is a major project priority. Every major pipeline stage must expose timing data.

Measure:

- audio capture window;
- packetization time;
- network transfer time;
- inference latency;
- profile and decision latency;
- command return latency;
- STM32 response time;
- motor activation delay;
- total end-to-end latency;
- dropped chunks;
- disconnect recovery;
- false-positive rate;
- false-negative rate;
- memory use;
- CPU/GPU/NPU utilization when available;
- battery or power behavior when available.

Recommended event timing record:

```json
{
  "event": "doorbell",
  "capture_ms": 500,
  "network_up_ms": 18,
  "inference_ms": 27,
  "decision_ms": 6,
  "network_down_ms": 14,
  "haptic_start_ms": 7,
  "total_after_window_ms": 72
}
```

Do not hide the capture window when presenting latency. Report both model latency and complete user-perceived latency.

---

## Reliability Requirements

The system should:

- reconnect after a temporary Uno Q or Wi-Fi disconnect;
- avoid replaying stale alert commands;
- deduplicate repeated detections;
- apply cooldowns where appropriate;
- keep emergency behavior more persistent than informational alerts;
- log failures without crashing the entire pipeline;
- expose health status for the microphone, backend, network link, RPC layer, and motor controller.

Emergency events should fail visibly. Do not silently drop them.

---

## Repository Layout

```text
QuietCue/
├── AGENTS.md
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── backend/
│   ├── app/
│   ├── audio/
│   ├── inference/
│   ├── profiles/
│   ├── communication/
│   ├── telemetry/
│   └── requirements.txt
├── uno_q/
│   ├── linux/
│   │   ├── audio_capture/
│   │   ├── transport/
│   │   └── rpc_client/
│   ├── stm32/
│   │   ├── haptics/
│   │   ├── buttons/
│   │   └── rpc_server/
│   └── README.md
├── frontend/
├── models/
│   ├── source/
│   ├── converted/
│   └── metadata/
├── tests/
├── scripts/
│   ├── setup_windows.ps1
│   ├── setup_wsl.sh
│   ├── setup_uno_q.sh
│   ├── run_demo.ps1
│   └── deploy_uno_q.sh
└── docs/
    ├── ARCHITECTURE.md
    ├── DEMO.md
    ├── TESTING.md
    ├── REFERENCES.md
    └── benchmarks/
```

---

## Development Workflow

GitHub is the source of truth.

Developers should work locally, not by editing directly on the Uno Q.

```bash
git checkout main
git pull
git checkout -b <feature-name>
```

After changes:

```bash
git add .
git commit -m "Describe the change"
git push -u origin <feature-name>
```

Open a pull request, review it, and merge into `main`.

### Device deployment

The Uno Q keeps a deployed clone of the repository.

```bash
ssh arduino@<uno-q-tailscale-ip>
cd ~/projects/QuietCue
git pull
./scripts/deploy_uno_q.sh
```

Do not treat the Uno Q clone as the canonical copy.

### Tailscale

Use Tailscale for:

- SSH access;
- remote deployment;
- logs and debugging;
- board profiling over SSH;
- private connectivity during development.

Do not commit Tailscale auth keys.

---

## Security and Privacy

Never commit:

- Wi-Fi credentials;
- API keys;
- cloud tokens;
- QUAD MCP tokens;
- Tailscale auth keys;
- passwords;
- private SSH keys;
- raw user audio;
- confidential event materials or venue credentials.

Use:

- environment variables;
- `.env.example` with placeholder names only;
- local secret files ignored by Git;
- short-lived tokens when available.

The default product behavior should avoid storing raw audio. Store event metadata and short diagnostic clips only when explicitly enabled for testing.

---

## Submission and Documentation Requirements

The public repository must include:

- application description;
- all team members' names and emails;
- setup instructions from scratch;
- dependency installation instructions;
- run and usage instructions;
- an open-source license;
- code that works using the documented instructions.

Strongly recommended:

- automated or manual tests;
- testing instructions;
- benchmark results;
- references;
- architecture documentation;
- well-commented code;
- a one-command or one-script demo launch.

Internal target: repository and demo should be complete before **12:00 PM PT on August 7, 2026**.

---

## Implementation Order

### Milestone 0 — Infrastructure

- GitHub repository is usable by all developers.
- Snapdragon PC and Uno Q are reachable through Tailscale.
- SSH and deployment work.
- Secrets are excluded from Git.

### Milestone 1 — Hardware proof of life

- Uno Q can trigger an LED.
- Uno Q can trigger a vibration motor safely.
- Button input is visible.
- Linux-to-STM32 RPC works.

### Milestone 2 — Audio proof of life

- Microphone audio is captured on the Uno Q.
- Audio quality is verified.
- Chunks reach the Snapdragon PC.
- Dropped packets and latency are logged.

### Milestone 3 — End-to-end event loop

- A basic classifier detects at least one event.
- The Snapdragon sends an alert command.
- The Uno Q produces the correct haptic category.
- The dashboard records the event and latency.

### Milestone 4 — Profiles

- At least two profiles exist.
- Enabled events and thresholds differ by profile.
- Profile switching changes alert behavior.

### Milestone 5 — QUAD optimization

- Baseline model is profiled.
- INT8 conversion is tested.
- CPU/GPU/NPU targets are compared.
- Final target choice is documented.

### Milestone 6 — Speech and name detection

- Speech is gated separately from environmental classification.
- A configured name can trigger an attention alert.
- Speech processing does not block emergency sound detection.

### Milestone 7 — Optional cloud intelligence

- Cirrascale or another cloud model may generate profile settings or summaries.
- Cloud failure does not break core detection or haptics.

### Milestone 8 — Demo hardening

- One-command startup.
- Reconnect behavior tested.
- Demo script written.
- README verified on a clean setup.
- Benchmarks and architecture documented.

---

## Definition of Done for the Hackathon MVP

The MVP is complete when:

1. The Uno Q microphone captures environmental audio.
2. Audio reaches the Snapdragon PC over Wi-Fi.
3. The Snapdragon detects at least three meaningful event classes.
4. The active profile changes alert behavior.
5. The Uno Q receives the alert through the runtime protocol.
6. Arduino RPC triggers the correct haptic pattern on the STM32 side.
7. The dashboard shows event, confidence, profile, device status, and latency.
8. The system recovers from a brief disconnect.
9. At least one model is profiled or optimized with QUAD.
10. A new developer can install and run the project from the README.

---

## Avoid These Traps

- Do not make the phone the only output device.
- Do not use the Arduino only as a decorative vibration endpoint.
- Do not upload continuous raw audio to a cloud model.
- Do not put Cirrascale in the emergency alert path.
- Do not assume hackathon cloud tokens are unlimited.
- Do not run Claude Code on the Uno Q for normal development.
- Do not optimize with QUAD before a baseline works.
- Do not mix speech transcription and sound classification into one undifferentiated pipeline.
- Do not create too many haptic patterns.
- Do not claim NPU use without evidence.
- Do not leave setup and deployment instructions until the final day.

---

## Current Priority

The next engineering target is:

```text
Uno Q microphone
    -> Wi-Fi audio stream
    -> Snapdragon baseline classifier
    -> profile decision
    -> alert command
    -> Arduino RPC
    -> vibration motor
```

Everything else should be judged by whether it helps complete, measure, or improve that loop.
