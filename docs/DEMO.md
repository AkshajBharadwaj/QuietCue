# QuietCue 3-minute demo runbook

Audience takeaway: environmental sound -> profile decision -> haptic alert, all
local, with visible confidence and latency.

## Prerequisites (before going on stage)

- Windows hub PC with Python 3.10+ on PATH and this repository cloned.
- Optional live hardware: Uno Q with the USB condenser microphone, reachable
  over the LAN or Tailscale, with the repo deployed
  (`scripts/setup_uno_q.sh`, then `scripts/deploy_uno_q.sh`).
- Agree the shared development token and set it on both sides:
  - Hub (PowerShell): `$env:QUIETCUE_PAIRING_TOKEN = '<shared-development-token>'`
  - Uno Q: `QUIETCUE_PAIRING_TOKEN` in `~/.quietcue_env`
- Dry-run the whole script at least once. Have the no-hardware fallback
  (Step F) rehearsed too.

The managed Uno Q runtime drives the STM32 motor through App Lab Bridge and
reports the result to `/api/state`. Keep the no-hardware path ready as a stage
fallback, but do not describe a motor alert as delivered until the state feed
sets `simulated` to `false`.

## Demo script

On macOS, Linux, or WSL, the hub, optional attached Android launch, and a complete
fire-alarm plus Sound Scout replay can be started together:

```bash
./scripts/run_demo.sh --showcase
```

The script leaves the hub running for interaction until Ctrl+C. The individual
steps below remain useful for Windows, physical hardware, and stage narration.

### Step A — Start the hub (~20 s)

```powershell
.\scripts\run_demo.ps1 -Classifier demo -AlertProfile home -BindHost 0.0.0.0
```

(Use `-Classifier yamnet` if TensorFlow is preinstalled and the real
classifier was validated on this machine; `demo` is the deterministic
tone-based simulator and is the safe stage default.)

Audience sees: hub log lines showing the audio port (8765), the state API
(8787), classifier, and active profile.

### Step B — Show the dashboard / state feed (~15 s)

Open `http://127.0.0.1:8787/api/state` in a browser (or show the Android
companion app connected to the same address). Point out: active profile,
connection state, no alerts yet.

### Step C — Fire alarm = emergency alert (~45 s)

With live hardware: play a fire-alarm sound near the Uno Q microphone.

Without the board mic, replay the synthetic fixture from a second terminal:

```powershell
.venv\Scripts\python.exe -c "from backend.audio.demo_audio import write_demo_wav; from pathlib import Path; write_demo_wav(Path('fire_alarm.wav'), 'fire_alarm', duration_seconds=1.0)"
.venv\Scripts\python.exe -m uno_q.linux.transport.hub_client fire_alarm.wav --pc 127.0.0.1:8765 --pairing-token $env:QUIETCUE_PAIRING_TOKEN
```

Audience sees: `ALERT COMMAND urgent_repeat` followed by `HAPTIC delivered`
in the hub log, the wearable buzzing the urgent pattern, and the event
with confidence and latency in the state feed. Say out loud: emergency
alerts repeat until acknowledged.

### Step D — Profile suppression: doorbell in Sleep mode (~45 s)

1. Show the doorbell working in the `home` profile (same replay flow with
   `doorbell_knock`): attention alert, `long_pulse` pattern.
2. Switch the active profile to `sleep` (via the Android app profile switcher,
   or restart the hub with `-AlertProfile sleep`).
3. Replay `doorbell_knock` again: no alert — the sleep profile disables
   doorbells — then replay `fire_alarm`: the emergency still fires.

Audience takeaway: user context controls what wakes you, but safety events
always get through.

### Step E — Close on the numbers (~30 s)

Show the state feed's latency fields for the last event (inference ms,
total ms after capture). If QUAD benchmarks are in `docs/benchmarks/`,
show the INT8-vs-baseline table as the final slide.

### Optional feature beat — Smart Places (~30 s)

In the Android app, open **Places**, choose **Create hackathon demo place**, and
tap **Test arrival**. Return to **Home** and show the review card offering to
switch to Work / School. Choose **Always switch here**, then test departure to
show QuietCue return to the prior profile. This simulator does not require
location permission or physical movement; real saved places use private on-phone
Android geofences.

## Step F — Fallback if anything breaks on stage

One command, zero dependencies, no network, no hardware:

```bash
python3 scripts/run_no_hardware_demo.py --event fire_alarm --profile home
python3 scripts/run_no_hardware_demo.py --event doorbell_knock --profile sleep
```

The first prints the completed loop with pattern and latency; the second
prints that the doorbell was suppressed by the sleep profile. That pair alone
demonstrates the full detection -> profile -> alert story.

Available events: `doorbell_knock`, `car_horn`, `fire_alarm`, `siren`,
`baby_crying`, `kitchen_timer`, `phone_ringing`.
Available profiles: `home`, `work`, `driving`, `sleep`, `emergency`.
