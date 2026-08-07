# Speech, name detection, and custom sounds — implementation plan

Status: implemented in source on August 6, 2026. Python and JVM verification is
complete, including a real local Faster-Whisper PC smoke test that produced a
profile-approved `name_called` alert without exposing a transcript on the wire.
Physical phone ONNX latency/accuracy and live Uno Q microphone/haptic validation
still require their external devices and staged model assets. See
`docs/WHISPER_ONNX.md` for the verified export contract and setup.

## 1. Why the current build cannot detect a name

Three independent blockers, all verified in the source:

1. **The speech path is off by default.** `backend/app/hub_server.py:381` defaults
   `--speech-model` to `""`. With an empty model name, `_pipeline_factory` never
   constructs a transcriber, so `HubInferencePipeline` receives `transcriber=None`
   (`backend/inference/pipeline.py:76`) and `BufferedSpeechRecognizer` is never created.
2. **YAMNet cannot ever produce `name_called`.** `_EVENT_TERMS` in
   `backend/inference/event_mapper.py:27` has no `name_called` entry, and AudioSet
   has no such class. The event is reachable *only* through the speech path
   (`pipeline.py:138`). YAMNet alone is structurally incapable of it — this is not a
   tuning problem.
3. **The phone hub has no speech code at all.** `PhoneInferenceEngine.kt` maps YAMNet
   labels and nothing else. If the Samsung phone is the hub, names are impossible.

A fourth problem appears as soon as the above are fixed:

4. **Phrase matching is exact.** `find_phrase_match` (`backend/inference/speech.py:141`)
   builds `(?:^|\s)<escaped phrase>(?:$|\s)` against the normalized transcript. Whisper
   tiny.en transcribing "Rohan" as "Roan", "Ro han", or "Rowan" fails silently. Names are
   the worst possible case for exact matching.

## 2. Decision: where speech-to-text runs

**Recommendation: Whisper ONNX on the phone, through the `onnxruntime-android` that is
already a dependency.** The PC path stays working as the verification reference.

### Option comparison

| | **A. whisper.cpp (C++/JNI)** | **B. Whisper ONNX (Kotlin)** | **C. `SpeechRecognizer` + `EXTRA_AUDIO_SOURCE`** |
|---|---|---|---|
| Decode loop | Already written, battle-tested | Must be hand-written | N/A — OS handles it |
| Build system | Adds NDK + CMake `externalNativeBuild` | None — ORT already wired | None |
| NDK present? | **No** — SDK has no `ndk/` or `cmake/`, needs download | n/a | n/a |
| Model asset | ggml tiny.en q5_1 ≈ 31 MB | ONNX encoder+decoder ≈ 40–75 MB | none |
| Reuses existing code | Little | `PhoneYamnetClassifier.materializeModel()`, `YamnetFeatureExtractor` | none |
| NPU / QUAD story | CPU only — weakens Milestone 5 | QNN EP path exists; AI Hub publishes the export | none |
| `initial_prompt` for names | Supported out of the box | Needs a BPE encoder (deferred, see §6) | no control |
| Reliability risk | Build friction | Decode-loop correctness | Device-dependent, may silently not work on Samsung |

### Why B

- **No new build system.** The SDK at `~/Library/Android/sdk` has no NDK and no CMake.
  Adding `externalNativeBuild` under a deadline is exactly the kind of thing that eats
  hours with nothing to show. ORT is already loading a model successfully today.
- **The asset and session pattern is already proven.**
  `PhoneYamnetClassifier.materializeModel()` / `copyAssetIfChanged()`
  (`PhoneYamnetClassifier.kt:71-90`) copies an ONNX + external-data pair out of assets
  with a size check. Whisper reuses it verbatim.
- **The mel frontend is ~80% written.** Whisper uses n_fft 400, hop 160 at 16 kHz —
  *identical* to YAMNet's `WINDOW_SAMPLES = 400` / `HOP_SAMPLES = 160`
  (`YamnetFeatureExtractor.kt:132-133`). The Hann window, the radix-2 FFT, and the
  triangular mel filterbank builder all carry over. What changes is 80 bands instead of
  64, the Slaney mel scale instead of `1127·ln1p(f/700)`, 0–8000 Hz instead of
  125–7500 Hz, and log10 + Whisper's clamp/normalize instead of `ln(x + 0.001)`.
- **It satisfies `AGENTS.md`.** The doc mandates Qualcomm AI Hub for speech-model
  sourcing and a CPU/GPU/NPU comparison for Milestone 5. AI Hub publishes Whisper-Tiny-En
  / Base-En ONNX exports, so this closes Milestone 6 and feeds Milestone 5 with one asset.
- **The single downside is the exact thing a Python reference kills.** See §7.

**whisper.cpp stays the documented escape hatch.** If the decode loop resists, switching
is a contained change behind the `PhoneTranscriber` interface in §4.

**Option C is worth a 30-minute spike, not a plan.** If Samsung honors
`EXTRA_AUDIO_SOURCE` it is 10× less code, but it is API 31+, thinly documented,
device-dependent, and offers no partial credit when it fails. Spike it; do not build on it.

### Prerequisite to verify before committing

The exact AI Hub Whisper export shape — encoder/decoder split, input/output names, and
whether the KV cache is exposed as explicit graph I/O or held internally. This determines
the decode loop's structure. **This is the first task, and it can invalidate the estimates
below.**

## 3. Trigger model: global vs per-profile

The two-level structure already half-exists and just needs a switch and a resolver.

**What exists today**

- Global: `MemoryBank` (identity + people + contexts), `MemoryModels.kt:28`, encrypted at
  rest via `EncryptedMemoryVault`, synced with whatever profile is active
  (`ProfileSyncJsonCodec.encode(catalog, memoryBank)`).
- Per-profile: `AlertProfile.phraseTriggers` (`ProfileModels.kt:190`), already editable in
  the UI as a comma-separated field (`ProfileEditorScreen.kt:297`).
- The backend already unions them: `hub_server.py:181` merges
  `profile.phrase_triggers + speech_context.identity_triggers() + wire phrase_triggers`.

**What is missing:** an on/off control at either level, and per-profile override semantics.

### New global settings — "My context" tab

```kotlin
data class SpeechSettings(
    val enabled: Boolean = true,           // master switch
    val model: SpeechModel = TINY_EN,      // TINY_EN | BASE_EN
    val sensitivity: Float = 0.6f,         // fuzzy-match floor, §6
    val listenForIdentity: Boolean = true, // the user's own name
    val listenForPeople: Boolean = false,  // other people in the bank
    val globalPhrases: List<String> = emptyList(),
)
```

Persisted in the existing encrypted vault next to `MemoryBank`. `listenForPeople` defaults
**off** — `docs/IDENTITY_AND_MEMORY.md` states other people's names are transcription
hotwords only and must not trigger the user's alert. Turning it on is a deliberate act.

### New per-profile override

```kotlin
enum class SpeechMode { INHERIT, ALWAYS_ON, OFF }
// AlertProfile gains: val speechMode: SpeechMode = SpeechMode.INHERIT
```

Sleep → `OFF` (don't wake for your name). Work → `ALWAYS_ON` + `"front desk"`. Home →
`INHERIT`.

### Resolution at runtime

```
transcribe? = profile.speechMode == ALWAYS_ON
           || (profile.speechMode == INHERIT && global.enabled)

phrases    = global.globalPhrases
           + identity.triggerPhrases()        if global.listenForIdentity
           + people names/aliases             if global.listenForPeople
           + profile.phraseTriggers
```

When `transcribe?` is false the transcriber is never invoked — no model load, no CPU, no
battery. This is the point of the switch, not just a UI nicety.

**Third layer, already working:** `name_called` is a built-in `SoundType`
(`ProfileModels.kt:27`), so its threshold, haptic pattern, strength, ack requirement, and
cooldown are *already* per-profile through the normal sound-rule editor. `speechMode`
governs whether we transcribe; the `name_called` rule governs what the alert feels like.
No new UI needed for that layer.

### Wire format

Extend the `speech_context` object in `ProfileSyncJsonCodec.encode` with a `settings`
child, and add `speech_mode` to the profile document. Decode in
`backend/profiles/wire_codec.py::_decode_speech_context` with the same bounded-validation
style as the rest of that file. Both are additive — old clients keep working since every
field has a default.

## 4. Android integration

New package `com.quietcue.app.phone.speech`:

```
PhoneTranscriber.kt        interface { fun transcribe(pcm: ByteArray): String? }
WhisperOnnxTranscriber.kt  ORT encoder+decoder sessions, greedy decode, KV cache
WhisperFeatureExtractor.kt 80-band Slaney log-mel (subclass/sibling of YamnetFeatureExtractor)
WhisperVocabulary.kt       token id -> string, from a JSON asset
SpeechGate.kt              VAD + buffering, port of BufferedSpeechRecognizer
PhraseMatcher.kt           fuzzy/phonetic matching, port of §6
```

The `PhoneTranscriber` interface is the seam that makes whisper.cpp a drop-in swap later.

**Wiring into the existing service**

- `PhoneInferenceService.onCreate` (`PhoneInferenceService.kt:42`) already loads the
  classifier on a single-thread executor and holds `@Volatile var classifier`. Add a
  matching `@Volatile var transcriber`, loaded lazily on first use so a disabled speech
  path costs nothing at startup.
- `PhoneInferenceEngine.process` already computes `speechConfidence`
  (`PhoneInferenceEngine.kt:69`) from YAMNet's speech-family labels. **That is a free VAD
  signal that is currently thrown away** — feed it straight into `SpeechGate` alongside a
  cheap RMS check with an adaptive noise floor.
- Transcription must run on its **own** single-thread executor, mirroring
  `BufferedSpeechRecognizer`'s design (`speech.py:193`), so a slow decode never blocks
  environmental detection. Emergency sounds must not queue behind a name.
- On match, emit a `PhoneMappedEvent(event = "name_called", category = "attention",
  pattern = "long_pulse")` into the existing `PhoneProfileDecisionEngine.decide` list. It
  then flows through thresholds, quiet hours, and cooldowns unchanged.
- `PhoneInferenceServer.handleClient` calls `inference.reset()` per client
  (`PhoneInferenceServer.kt:58`); add `speechGate.reset()` beside it so a reconnect drops
  stale buffered audio.

**UI**

- *My context* tab → new "Speech and names" card above the identity card:
  master switch, model picker, sensitivity slider, two audience toggles, global phrase
  editor. New `MemoryEditorFlow.SPEECH` entry in `QuietCueApp.kt:43`.
- *Profile editor* → a three-way `OptionChips` control for `speechMode` next to the
  existing trigger-phrases field, reusing the `EditorSection` / `OptionChips` helpers
  already in `ProfileEditorScreen.kt:364,545`.
- *Dashboard* → surface transcription state in the existing `PhoneInferenceStatus` flow
  (model loaded / listening / last decode ms). Never display transcript text — see §9.

## 5. Backend work (also the verification reference)

1. Flip `--speech-model` to default `base.en`, add an explicit `--no-speech`.
   (`hub_server.py:381`)
2. Replace `find_phrase_match` with the §6 matcher; keep the signature so
   `pipeline.py:133` is untouched.
3. Honor `speechMode` / `SpeechSettings` in `hub_server._process_audio` — skip the
   recognizer entirely when disabled.
4. Extend `wire_codec.py` for the new fields, with bounds, matching the existing style.
5. Add `scripts/whisper_onnx_reference.py` — runs the *same* ONNX files the phone will
   use, greedy decode in NumPy, dumps per-stage tensors. This is the oracle for §7.

## 6. Fuzzy name matching

Exact matching is the single highest-value fix after turning the path on.

**Algorithm**

1. Normalize with the existing `_normalize` (`speech.py:305`).
2. Compute a phonetic key per token — a reduced Metaphone: map `ph→f`, `ck→k`, drop
   non-initial vowels, collapse doubled consonants.
3. Slide a window over transcript tokens at the phrase's token length ±1.
4. Score = `max(exact 1.0, phonetic-key equal 0.9, normalized edit similarity)`.
5. Accept above `SpeechSettings.sensitivity`; return the score as the event confidence so
   the profile's `name_called` threshold still applies on top.

**False-positive control.** Fuzzy matching trades precision for recall, so: keep
`name_called` at `attention`, never `emergency`; multiply the match score by ASR
confidence; rely on the existing per-profile threshold and cooldown; and log rejected
near-misses to make tuning empirical rather than guessed.

**Deferred: `initial_prompt` conditioning.** Whisper accepts a text prompt to bias it
toward known names, which would help a lot. It needs text→token encoding, i.e. the BPE
merges table and an encoder (~1 MB of assets, ~200 lines). Greedy decoding needs only
id→string. **Ship without it**; let fuzzy matching absorb the error. Revisit if measured
accuracy is short. The Python side keeps prompt support since `faster-whisper` already
does it (`speech.py:99`) — which also makes the accuracy delta measurable.

## 7. Verification without guessing

This is what makes a hand-written decode loop safe, and it is the core of the plan.

- **Python first, as the oracle.** Same `.onnx` files, greedy decode in NumPy, on this
  Mac. Confirm real transcripts on real audio *before* any Kotlin exists.
- **Dump reference tensors** at each stage — mel, encoder output, first-N decoder logits,
  token ids — into `tests/fixtures/whisper_reference/`.
- **JVM unit tests, no device needed.** `AcousticFingerprintTest` and
  `YamnetFeatureExtractorTest` already prove pure-math Kotlin runs under
  `gradlew test` with Android Studio's bundled JDK 25. `WhisperFeatureExtractorTest`
  asserts mel output against the Python dump within tolerance; `PhraseMatcherTest` runs
  entirely on strings.
- **arm64 emulator for real inference.** This is an arm64 Mac, so an arm64 system image
  runs *natively* and `onnxruntime-android`'s arm64 libraries execute for real. One
  `sdkmanager` download and the ONNX path is verifiable here, before the phone.
- **Phone last,** via `~/Library/Android/sdk/platform-tools/adb` — install, `logcat`,
  measure real latency.

So the only genuinely unverifiable-from-here step is the physical haptic buzz.

## 8. Sequence

| # | Task | Verifiable here? |
|---|---|---|
| 1 | Confirm AI Hub Whisper export shape (gates everything) | yes |
| 2 | Python fuzzy matcher + tests | yes |
| 3 | Turn on backend speech, end-to-end name alert on PC hub | yes |
| 4 | `whisper_onnx_reference.py` + tensor dumps | yes |
| 5 | `SpeechSettings` + `speechMode` — models, vault, codecs, wire, validators | yes (JVM) |
| 6 | Global + per-profile UI | compiles only |
| 7 | `WhisperFeatureExtractor` + test vs. Python mel | yes (JVM) |
| 8 | `WhisperOnnxTranscriber` decode loop | emulator |
| 9 | `SpeechGate` + service wiring | emulator |
| 10 | Phone install, latency + accuracy measurement | needs phone |

Steps 1–4 deliver a **working name alert on the PC hub** and stand alone. If time runs
out after step 4, the demo works. Everything after that moves it onto the phone.

## 9. Privacy

`AGENTS.md` forbids storing raw audio, and `IDENTITY_AND_MEMORY.md` promises the hub does
not persist the bank. Preserve both: transcripts stay in memory, never logged, never
written to the event JSONL, never shown on the dashboard. Only the *matched phrase* and a
confidence reach telemetry — which is what `pipeline.py:142` already does
(`source_label = 'phrase: "..."'`). The buffer holds at most 4 s and is cleared on
disconnect. New model assets ship in-app; no audio ever leaves the device.

## 10. Risks

| Risk | Mitigation |
|---|---|
| AI Hub export shape differs from assumption | Task 1 gates the rest; whisper.cpp is the fallback |
| Decode loop wrong | Python oracle + tensor diffing (§7) |
| Whisper pads to 30 s → constant encoder cost | Measure early; consider a variable-length export; budget 0.5–1.2 s |
| Fuzzy matching false-positives | Attention-only, ASR-weighted, per-profile threshold, cooldown, near-miss logging |
| Battery on the phone | Gated by VAD + master switch; measure |
| **Uno Q microphone may not work** | See below — this blocks any live demo |

**The microphone is the real external risk.**
`docs/benchmarks/HARDWARE_VALIDATION_2026-08-05.md` closes with the USB condenser mic
disconnected, `~/.quietcue_env` absent, and `quietcue-client.service` stopped. Every
validated audio result so far is a *replayed WAV*, not live capture. No microphone means
no live speech demo regardless of how good the model is.

## 11. What I need from you

1. **Yes to SSH on the Uno Q** — this is the highest-value thing you can hand me, and it
   is on the critical path. I would: confirm a capture device exists (`arecord -l`),
   record a few seconds and check levels, recreate `~/.quietcue_env`, restart
   `quietcue-client.service`, and verify live chunks reach a hub. Per `AGENTS.md` this is
   development/debugging use of SSH, which is explicitly allowed. Send the Tailscale
   hostname and credentials when ready.
2. **Permission to download an arm64 emulator image** via `sdkmanager` (a few minutes).
   This is what lets me verify ONNX inference here instead of on your phone.
3. **A decision on scope** — whether custom sounds (§12) are in or out for tomorrow.

## 12. Second track — custom sounds (scoped separately)

Not required for name detection; listed so it is not lost.

The enrollment prototype is 8 Goertzel magnitudes with cosine similarity
(`custom_sound_matcher.py:20`, `AcousticFingerprint.kt:19`). Eight frequency bins cannot
separate a doorbell from a microwave beep, and `PROFILE_AGENT_AND_ENROLLMENT.md` already
concedes this.

- **v2 prototypes.** Use YAMNet's 521-class score vector as a semantic audio embedding.
  It is already computed for every chunk on both hubs and costs nothing extra. The export
  exposes only `class_scores` — no penultimate embedding — so the 521-vector is the right
  substrate. Version it as `matcher_version: 2`, keep v1 decodable. Coordinated change
  across `custom_sound_matcher.py`, `wire_codec.py:76` (its validator hard-codes eight
  normalized features), `AcousticFingerprint.kt`, and `ProfileSyncJsonCodec.kt`.
- **Describe-a-sound, no recording.** Type "microwave"; fuzzy-match the 521 AudioSet
  labels; create a `ClassifierLabelRule`. This reuses the §6 matcher and the
  already-working `ClassifierLabelMatcher`, and it is the natural fit for adding a sound
  from the context section rather than the enrollment flow.

Recommendation: both, but only after §8 step 4 lands. On its own the v2 embedding improves
detection without giving a *better way to add* anything, which was the original ask.
