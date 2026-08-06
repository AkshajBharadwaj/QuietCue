# Hub pipeline validation — 2026-08-05

Validation run on the development PC only. No Uno Q board and no live microphone
were used; every number below comes from the dependency-free simulator path
unless stated otherwise. Nothing in this report is estimated or extrapolated.

## Environment

- Windows 11 Pro 10.0.26100, native ARM64 (Snapdragon X Elite class machine)
- Python 3.12.10 (native ARM64 build)
- Repo state: working tree at commit `ddf23ba` (no local modifications made)
- Classifier under test: `--classifier demo` (deterministic simulator).
  The real YAMNet classifier could **not** be run — see "YAMNet path" below.

## 1. Automated test suite

`python -m unittest discover -s tests -v`

- **19 tests, 19 passed, 0 failed, 0 errors** in 0.580 s.
- Coverage spans: ALSA source contract, custom-sound enrollment, no-hardware
  pipeline (profile disable, quiet hours, tone→event mapping, full hub
  integration), speech context/pipeline, stream protocol, WAV replay source.

## 2. No-hardware demo loop (simulator classifier)

`python scripts/run_no_hardware_demo.py --event <e> --profile <p>` — each run
starts a real hub server, replays a generated 1 s WAV through the real TCP
transport, and reads the result from the Android state API.

| Event | Profile | Outcome | Pattern | Category | total_after_capture_ms | inference_ms (chunk 0) |
|---|---|---|---|---|---|---|
| fire_alarm | home | alert issued | urgent_repeat | emergency, requires_ack | 33 | 14.51 |
| doorbell_knock | home | alert issued | long_pulse | attention | 56 | 18.70 |
| doorbell_knock | sleep | **suppressed** (`disabled_by_profile`) | — | — | — | 9.34 |
| car_horn | home | **suppressed** (`disabled_by_profile`) | — | — | — | 5.73 |
| car_horn | driving | alert issued (profile upgrade) | urgent_repeat | emergency, requires_ack | 22 | 6.73 |
| fire_alarm | sleep | alert issued (emergency not suppressed) | urgent_repeat | emergency, requires_ack | 36 | 10.24 |

Validated behaviors:

- **Profile switching changes behavior**: the same event (doorbell_knock,
  car_horn) alerts under one profile and is suppressed under another, with the
  suppression reason exposed (`disabled_by_profile`).
- **Emergency precedence**: fire_alarm still alerts under the sleep profile.
- **Profile overrides**: driving upgrades car_horn from attention/long_pulse to
  emergency/urgent_repeat with `requires_ack: true`.
- **Cooldown dedup**: in every alerting run, the second audio chunk produced the
  same event but was suppressed with reason `cooldown` — one buzz per incident.
- **Alert JSON contract**: emitted alerts carry `event`, `category`,
  `confidence`, `pattern`, `requires_ack`, `strength`, `event_id`,
  `profile_id/name`, `captured_at_ms`, `issued_at_ms`, `total_after_capture_ms`,
  matching the AGENTS.md alert-command shape (plus telemetry fields).

Caveats: the demo classifier returns fixed 0.98-confidence predictions for a
synthetic tone; these runs validate transport, mapping, profile logic, and
telemetry — **not** real acoustic detection. All traffic was loopback
(127.0.0.1), so `total_after_capture_ms` (22–56 ms) excludes real Wi-Fi hops.

## 3. YAMNet path — could not run on this machine

`backend/requirements.txt` pins `tensorflow==2.21.0` + `tensorflow-hub`.
In a clean native ARM64 Python 3.12 venv:

```
ERROR: Could not find a version that satisfies the requirement tensorflow==2.21.0 (from versions: none)
```

An unpinned `pip install tensorflow` also finds **no distribution at all**:
there is no TensorFlow wheel for native Windows ARM64 CPython 3.12. Per the
install instructions' own note, NPU/x-elite wheels live in a separate ARM64
venv workflow; the stock TF-Hub YAMNet path as written requires WSL or an
x86-64 Python. Consequence:

- Real environmental classification has **never been executed on this machine**
  in this validation. Predictions, real-audio accuracy, and YAMNet inference
  latency are all unmeasured.
- Options (owned by the QUAD lane): run YAMNet under WSL/x64 Python for a
  baseline, or move to the ONNX/ORT-QNN route where ARM64 wheels exist.

## 4. Event-mapper readiness (code review, not measurement)

`backend/inference/event_mapper.py` maps YAMNet/AudioSet labels by substring,
floor confidence 0.10, then profiles apply per-event thresholds
(0.35–0.65 depending on profile):

| QuietCue event | Matched label terms |
|---|---|
| fire_alarm | fire alarm, smoke detector, smoke alarm |
| doorbell_knock | doorbell, ding-dong, knock |
| car_horn | vehicle horn, car horn, honking, air horn, truck horn |
| siren | siren, emergency vehicle |
| baby_crying | baby cry, infant cry, crying, sobbing |
| kitchen_timer | timer, alarm clock |
| phone_ringing | telephone bell ringing, ringtone |

Best-positioned 3 MVP classes for live validation: **fire_alarm, siren,
car_horn** — each maps to distinctive, well-represented AudioSet classes and is
emergency/attention-critical. doorbell_knock is riskier ("knock" is a weak,
easily confused class). Note: "alarm clock" → kitchen_timer may collide with
smoke-alarm-adjacent labels; verify with real audio before the demo.

## 5. Disconnect / reconnect

- No automated test exercises disconnect/recovery; grep for
  reconnect/retry/backoff finds no client retry logic in the transport, only
  replay-suppression notes in the new `uno_q/linux/rpc_client/` module (being
  built in a parallel work lane, not validated here).
- What *is* validated nearby: per-event cooldown suppression (section 2) and
  `event_id` uniqueness per alert, which is the hook for stale-replay
  suppression.
- Recovery from a mid-stream Wi-Fi drop (MVP requirement 8) remains untested.

## 6. What must be validated on the real Snapdragon-with-mic setup

1. Real YAMNet (or ONNX) inference: install path, predictions on real fire
   alarm / siren / car horn recordings, inference latency per 1 s chunk.
2. Live Uno Q microphone → Wi-Fi → hub: end-to-end latency with real network
   hops, dropped-chunk rate.
3. Disconnect/reconnect: kill Wi-Fi mid-stream, confirm resume without stale
   alert replay.
4. Speech path: gated Faster-Whisper name/phrase detection was disabled in all
   runs here (`Speech model=disabled`); needs a live run.
5. Threshold tuning against real audio (current thresholds are untested against
   any real recording).

## Prioritized validation gaps

1. **No real-model classification has ever been validated in this environment**
   (TensorFlow uninstallable on native win-arm64) — blocking MVP "detects at
   least three meaningful event classes" until run under WSL/x64 or ONNX.
2. **No end-to-end run with real audio or a real network** — all timings are
   loopback + simulator; treat 22–56 ms as a lower bound only.
3. **Disconnect/reconnect recovery is untested** and has no test coverage.
