# Profile assistant and custom sound enrollment

## Situation-to-profile assistant

From the Profiles tab, choose **Describe a situation** and enter where the user is
going, what should be ignored, important sounds, and any name or phrase trigger.
The local constrained assistant:

- chooses the closest built-in profile as a starting point;
- recognizes explicit sound names and enrolled-sound names;
- applies requests such as "ignore phones" or "only alert me to...";
- keeps safety-critical detections enabled as a guardrail;
- extracts quoted phrases and simple "my name is" statements;
- produces assumptions and a complete profile draft;
- requires review in the normal editor before the profile can be saved.

The `ProfileGenerationService` interface is intentionally replaceable. A local
model on the Copilot+ PC can later implement the same contract, while the current
deterministic agent remains an offline fallback. Model output must still pass the
same profile validator and confirmation screen.

## Custom sound enrollment

From the Profiles tab, choose **Enroll a sound**:

1. Name and describe the sound.
2. Choose informational, attention, or emergency urgency.
3. Record three two-second examples from a realistic distance.
4. Record the room without the target sound.
5. QuietCue checks volume, example consistency, and background separation.
6. Review the resulting sound rule in the active profile.

The phone records 16 kHz mono PCM only for the duration of each explicit capture.
It extracts an eight-component normalized spectral fingerprint in memory and then
discards the PCM. The saved catalog contains the fingerprint, calibrated threshold,
sample count, matcher version, and event metadata—never raw audio.

The active Android profile synchronizes to the local hub over the development
state API. The hub validates all fields and prototypes before replacing its active
profile. Each incoming audio chunk is compared with enabled enrolled prototypes;
a match enters the same threshold, quiet-hours, cooldown, telemetry, and haptic
decision pipeline as built-in events.

## Current safety boundary

The spectral fingerprint is an intentionally small MVP used to validate product
behavior before the final microphone and learned embedding model are available.
It can confuse sounds with similar frequency content and is not the sole detector
for fire alarms, sirens, horns, or other critical events.

Before production use:

- replace it with a measured audio embedding model;
- recalibrate examples using the Uno Q microphone;
- add held-out validation and false-positive testing;
- encrypt/authenticate profile synchronization beyond localhost development;
- profile the selected embedding model normally, then use QUAD for target-specific
  conversion, quantization, and CPU/GPU/NPU comparison.
