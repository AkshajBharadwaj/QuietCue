# Final submission checklist

Repository: https://github.com/AkshajBharadwaj/quietcue

## Repository requirements

- [x] Application description is in `README.md`.
- [x] All five team members' names and emails are in `README.md`.
- [x] Clean-clone dependency, setup, run, and usage instructions are in `README.md`.
- [x] Open-source MIT license is in `LICENSE`.
- [x] Software-only demo runs without external packages or connected hardware.
- [x] Copilot+ PC, Uno Q, Android, demo, architecture, and benchmark instructions are documented.
- [x] Automated backend and Android tests are included with testing instructions.
- [x] Secrets, local configuration, raw audio, build outputs, and downloaded model weights are ignored.

## Human actions required before noon PDT on August 7, 2026

- [ ] Confirm every team member submitted the required feedback form.
- [ ] Commit and push the final intended working tree to the personal repository.
- [ ] Open the public GitHub repository in a logged-out/private browser and verify
  the README, license, and clone instructions are visible.
- [ ] Submit `https://github.com/AkshajBharadwaj/quietcue` through the required
  Microsoft Form before the deadline.

## Final verification commands

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/run_no_hardware_demo.py --event fire_alarm --profile home
python3 scripts/run_no_hardware_demo.py --event doorbell_knock --profile sleep

cd frontend/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

The no-hardware demo is intentionally deterministic. Live classifier and physical
haptic verification require the dependencies and hardware listed in `README.md`
and `docs/UNO_Q_MICROPHONE.md`.
