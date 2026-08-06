# Sound Scout discovery

Sound Scout turns recurring high-confidence classifier labels that QuietCue does
not map yet into reviewable suggestions. It is advisory and never enters the
safety-critical alert path.

## Current flow

1. The computer hub retains metadata from the latest 100 inference observations:
   sequence, capture time, active profile, top predictions, mapped events, alert
   decisions, and suppression reasons.
2. Predictions below 35% confidence, already-mapped source labels, custom-sound
   matches, and broad speech/music/noise labels are excluded.
3. Consecutive detections less than three seconds apart are one episode. This
   prevents a ten-second sound from being reported as ten separate occurrences.
4. After three separate episodes, the candidate appears in `/api/state` and on
   the Android Home screen.
5. **Add to profile** shows the proposed informational haptic, confidence threshold,
   cooldown, and profile scope before creating an exact classifier-label rule.
   **Teach QuietCue this sound** opens custom enrollment with the label prefilled.
   **Ignore suggestion** dismisses it.

Only inference metadata is retained. Sound Scout never receives or stores raw PCM.
Candidates and dismissals persist as metadata in `.quietcue/discovery_state.json`
by default. Discovery currently runs on the computer hub; parity with the Android
phone hub is future work.

## Deterministic demo

Run the complete no-hardware discovery loop:

```bash
python3 scripts/run_no_hardware_demo.py --event vacuum_cleaner --profile home
```

The simulator replays three distinct `Vacuum cleaner` episodes. It should finish
with `Completed Sound Scout loop` rather than an alert because the label is not a
configured QuietCue event.

To show the card in Android, keep the hub running, forward port 8787 with `adb
reverse`, generate the `vacuum_cleaner` fixture, and replay it three times with at
least 3.1 seconds between completed replays.

## Current boundary

- Suggestions require explicit user action.
- Explicitly mapped sounds—including sounds disabled by a profile—are not discovery
  candidates.
- Direct addition creates an exact, case-insensitive YAMNet label rule. It does not
  retrain YAMNet or make a broad class specific to one appliance.
- Enrollment still creates the provisional acoustic fingerprint when a personal
  instance needs more specificity.
- Embedding clustering, false-positive feedback, Android phone-hub discovery, and
  agent-generated profile diffs remain future work.
