# QUAD status — 2026-08-05

Lane 4 report: QUAD connectivity, hardware detection, model export, and conversion attempts.
Everything below was actually run today on the workshop Snapdragon X Elite laptop; errors are
verbatim.

## 1. Connection: WORKING

```
✓ sse-http connected in 1205 ms — MCP handshake OK (QUAD — Qualcomm Unified Agent for Developers 3.4.4)
```

- Server: `https://quad.infra.foundries.io/mcp` (SSE HTTP transport), auth via `QUAD_MCP_TOKEN`.
- The token lives in `%USERPROFILE%\Downloads\QUAD\QUAD MCP Token` and is set as a **User
  environment variable** (`QUAD_MCP_TOKEN`) on this machine. Never commit it.
- No VPN was required from this network today.

**Fix that was needed:** the client venv (`Downloads\QUAD\QUAD-Client-main\.venv`) had
`quad-mcp-client` installed *editable* against `C:\Users\QCWorkshop6\Documents\projects\quad\QUAD-Client-main`,
a path that no longer exists (the tree was moved to Downloads). Symptom:
`ModuleNotFoundError: No module named 'quad_mcp_client'`. Fixed with:

```powershell
cd $env:USERPROFILE\Downloads\QUAD\QUAD-Client-main
.venv\Scripts\python.exe -m pip install -e . --no-deps
```

Re-verify any time with:

```powershell
cd $env:USERPROFILE\Downloads\QUAD\QUAD-Client-main
$env:QUAD_MCP_TOKEN = [Environment]::GetEnvironmentVariable('QUAD_MCP_TOKEN','User')
.venv\Scripts\python.exe -m quad_mcp_client.cli connect-test sse-http --sse-url "https://quad.infra.foundries.io/mcp" --auth-token "$env:QUAD_MCP_TOKEN"
```

## 2. `quad-client detect` (host)

| | Detail |
| :--- | :--- |
| CPU | Snapdragon X Elite X1E80100, 12 × ARM64 @ 3.417 GHz |
| GPU | Adreno X1-85 (4.6 TFLOPS) |
| NPU | Hexagon NPU v73, 45.0 TOPS |
| RAM | 31.6 GB |
| Runtimes | cpu, npu |
| SDK | **None (not configured)** |

## 3. `quad-client doctor`: 5 OK / 9 WARN / 0 errors

Relevant warnings (all boil down to "no local Qualcomm SDK"):

- `QAIRT_SDK_ROOT` / `QNN_SDK_ROOT` / `SNPE_ROOT` not set; `qairt-converter`, `snpe-net-run`
  not on PATH → **no local model conversion or on-host SNPE profiling is possible yet**.
- Neither `onnxruntime` nor `onnxruntime-qnn` installed in the client venv → no NPU
  execution-provider runs from that venv yet (`/quad-npu-prereqs` provisions this).
- `psutil` missing (live RSS/CPU sampling during profiling disabled).
- `adb` absent (only matters for Android targets; Uno Q uses SSH).

## 4. Model export: DONE

- `models/source/yamnet.tflite` — fixed-shape YAMNet TFLite (input `float32[15600]`,
  0.975 s @ 16 kHz), 16,096,668 bytes,
  sha256 `141fba1cdaae842c816f28edc4937e8b4f0af4c8df21862ccc6b52dc567993c3`.
- Provenance + input/output spec + pipeline integration notes: `models/metadata/yamnet.md`.
- The raw GCS link (`storage.googleapis.com/tfhub-lite-models/...`) is no longer anonymously
  accessible (403); the working URL is
  `https://tfhub.dev/google/lite-model/yamnet/tflite/1?lite-format=tflite`.

## 5. Conversion attempts: ALL BLOCKED (server-side), with exact errors

Attempted via the hosted server's `convert_model` MCP tool (model uploaded through the
`/uploads` data plane — upload itself works fine). Three attempts:

### 5a. `target_sdk=snpe, quantization=int8` and 5b. `target_sdk=qnn, quantization=int8`

Both fail identically — **the hosted QUAD server's own QAIRT SDK install is broken** (its
`qairt-converter` cannot start because the server machine is missing libpython3.10):

```
Error calling tool 'convert_model': qairt-converter failed (exit 1):
  File ".../sdks/v2.41.0.251128/lib/python/qti/aisw/dlc_utils/__init__.py", line 59, in <module>
    import libDlModelToolsPy as modeltools
ImportError: libpython3.10.so.1.0: cannot open shared object file: No such file or directory
```

This is not fixable from our side — it needs the QUAD server operators (or hackathon
organizers) to repair the Python 3.10 runtime on `quad.infra.foundries.io`.

### 5c. `aihub=force` (route around the broken local converter via AI Hub cloud)

- INT8: `Cannot quantize yamnet.tflite via AI Hub: no calibration data supplied and none could
  be synthesised from the model's inputs (is it a valid ONNX with readable input shapes?)` —
  the AI Hub path wants **ONNX**, and INT8 additionally wants calibration data.
- FP32: `Input model type cannot be compiled.` — AI Hub compile jobs do not accept TFLite.

### 5d. Local conversion on this laptop

Not possible today: no QAIRT/QNN/SNPE SDK installed (doctor §3), and a local
TFLite→ONNX re-export is blocked because TensorFlow/tf2onnx ship no win-arm64 wheels.

### AI Hub catalog check

`aihub_select` over the 195-model catalog returns **0 matches** for
yamnet/audio-classification — no pre-optimized drop-in exists there.

## 6. Exact next commands

### (a) Snapdragon INT8 profile — once conversion is unblocked

Unblock = any one of: server SDK fixed by operators / QAIRT SDK installed locally
(`/quad-configure` then `/quad-npu-prereqs` inside `Downloads\QUAD\QUAD-Client-main`) /
an ONNX YAMNet obtained (then the AI Hub route works — supply calibration WAVs from
`scripts/generate_demo_audio.py` + real mic captures).

From Claude Code launched inside `Downloads\QUAD\QUAD-Client-main` (that folder's
`.claude/settings.json` carries the MCP server config):

```
/quad-convert   models/source/yamnet.tflite → INT8, target qnn (host) and snpe (Uno Q)
/quad-profile   the converted artifact — CPU vs NPU latency/memory on the X Elite
/quad-orchestrate  power-mode + op-placement comparison
```

Convert BOTH fp32 and int8 and let measured latency decide — on IQ-9075 hardware INT8 was
observed 42% *slower* than FP32 (see `.claude/skills/quad-convert/SKILL.md`), so do not
assume INT8 wins on v73 either. (On the Uno Q's Hexagon **v66**, INT8 is mandatory — FP32
falls back to CPU.)

### (b) Uno Q on-device profile — once a board IP exists

```powershell
cd $env:USERPROFILE\Downloads\QUAD\QUAD-Client-main
.venv\Scripts\quad-client.exe unoq configure <board-ip> --user root   # prints [target.*] stanza → paste into quad.toml
.venv\Scripts\quad-client.exe unoq status    <board-ip> --user root   # connectivity + RAM + thermal + DSP state
.venv\Scripts\quad-client.exe unoq deploy    <board-ip> --model .\models\converted\yamnet_int8.dlc --user root
.venv\Scripts\quad-client.exe unoq perf      <board-ip> --model /data/local/tmp/quad/models/yamnet_int8.dlc --duration 30 --profile balanced
.venv\Scripts\quad-client.exe unoq power     <board-ip>
```

Targets from the skill's KPI framework: P50 < 33 ms, P99 < 50 ms, `balanced` profile
(~0.8 W NPU) for sustained use; keep model + runtime well under 1.5 GB of the board's 2 GB.

## 7. Blocker summary (most important first)

1. **Hosted server's qairt-converter is broken** (`libpython3.10.so.1.0` missing on the
   server) → report to QUAD organizers; this blocks all TFLite/ONNX → DLC/QNN conversion
   through the server.
2. **No local QAIRT/QNN/SNPE SDK on this laptop** → `/quad-configure` + SDK install is the
   self-service workaround for blocker 1.
3. **AI Hub route needs ONNX** → obtaining a YAMNet ONNX export (from an x86 machine with
   TensorFlow, or WSL) would open the cloud conversion path; then supply calibration WAVs.
4. **No Uno Q board IP recorded yet** → §6(b) is ready to paste the moment the board is on
   Tailscale/LAN.
