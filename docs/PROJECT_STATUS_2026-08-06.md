# QuietCue project status — 2026-08-06

## Current implementation

The intended runtime boundary is now:

```text
UNO Q microphone
  -> 16 kHz mono PCM16 + signal diagnostics
  -> selected Samsung/PC inference hub
  -> environmental/speech/custom classifiers
  -> active profile, thresholds, quiet hours, and cooldowns
  -> alert command
  -> UNO Q App Lab Bridge
  -> STM32 vibration pattern
  -> haptic delivery result returned to the hub
```

The UNO Q is responsible for capture, transport, reconnect behavior, and haptic
delivery. All event inference is performed by the connected device. If no hub is
reachable, the board retries and does not invent a local event.

The automated integration suite covers raw audio transport, connected-hub
classification, profile decisions, alert commands, haptic dispatch, delivery
telemetry, and reconnect behavior. A replayed physical hardware test previously
confirmed App Lab Bridge delivery to the STM32; live microphone capture was
separately detected and level-checked.

## Physical UNO Q result

The physical board was authenticated and safely updated to the exact Arduino
UNO Q kernel/config while preserving the old boot kernel and the separate user
partition. After reboot it exposed:

- `/dev/fastrpc-adsp`
- `/dev/dma_heap/system` and the other DMA heaps
- a running QRB2210 ADSP remote processor
- Adreno DRM render devices

SSH, Docker, Arduino App Lab, routing, and Tailscale remained healthy. The
original QRB2210 UNO Q does not expose the newer Ventuno `/dev/fastrpc-cdsp`
interface.

A strict physical `snpe-net-run --use_dsp` launch of the checked-in INT8 DLC
reached SNPE but returned `No backend library matched for this build and target`.
The artifact targets a different Qualcomm DSP/HTP class than this board's V66
audio DSP. It must not be described as UNO Q accelerator inference.

Because the product no longer requires model execution on the UNO Q, the runtime
does not install QAIRT tools, load the DLC, or silently substitute board CPU
inference. The converted artifacts remain available to compatible connected
devices.

## QUAD artifacts

- W8A8 YAMNet ONNX external-data model for capable connected runtimes
- 3.63 MB INT8 QAIRT DLC with recorded SHA-256 `e716cdc2...042c34c`
- Snapdragon X Elite QNN/HTP benchmark evidence in `docs/benchmarks/`

Those X Elite measurements are valid for that connected PC and are not
transferable to the QRB2210 UNO Q.

## Next implementations

1. Implement the protocol-compatible audio inference server in the Samsung app;
   the existing Android companion currently edits profiles and displays state.
2. Run an attended live microphone -> connected model -> physical vibration test
   with representative environmental sounds and record accuracy/latency.
3. Add encrypted/authenticated transport beyond the current pairing-token
   development protocol.
4. Measure false positives, end-to-end latency, reconnect behavior, and battery
   impact before treating the prototype as safety-critical.
