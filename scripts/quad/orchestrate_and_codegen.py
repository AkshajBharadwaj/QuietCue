"""Ask the QUAD MCP server for orchestration advice and a generated runner.

Runs three tools against the converted YamNet artifact and stores the raw
envelopes under docs/benchmarks/ (plus the generated runner source under
scripts/quad/generated/) so the deployment decision is documented, not
guessed:

- orchestrate_workload: recommended execution target / power mode
- profile_workload:     server-side profile of the converted artifact
- generate_code:        runnable QNN inference scaffold for Windows/ARM64

Usage: python scripts/quad/orchestrate_and_codegen.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from quad_mcp_client import create_client

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO_ROOT / "docs" / "benchmarks"
GENERATED_DIR = Path(__file__).resolve().parent / "generated"
DEFAULT_URL = "https://quad.infra.foundries.io/mcp"

# Server-side path of the artifact produced by scripts/quad/convert_yamnet.py
# (recorded in models/converted/convert-int8-qnn.json).
def _converted_server_path() -> str:
    envelope = REPO_ROOT / "models" / "converted" / "convert-int8-qnn.json"
    if envelope.is_file():
        payload = json.loads(envelope.read_text(encoding="utf-8"))
        if payload.get("output_path"):
            return payload["output_path"]
    return "model.bin"


async def run() -> dict[str, dict]:
    url = os.environ.get("QUAD_MCP_URL", DEFAULT_URL)
    model_path = _converted_server_path()
    results: dict[str, dict] = {}
    async with create_client(url=url) as client:
        for name, call in {
            "orchestrate_workload": lambda: client.orchestrate_workload(
                model_path=model_path, power_mode="balanced"
            ),
            "profile_workload": lambda: client.profile_workload(
                model_path=model_path, platform="windows", runtime="npu"
            ),
            "generate_code": lambda: client.generate_code(
                platform="windows",
                sdk="qnn",
                language="python",
                model_path=model_path,
                runtime="npu",
            ),
        }.items():
            try:
                results[name] = await call()
            except Exception as exc:  # noqa: BLE001 — record and continue
                results[name] = {"ok": False, "error": str(exc)}
    return results


def main() -> None:
    results = asyncio.run(run())
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in results.items():
        path = BENCH_DIR / f"quad-{name.replace('_', '-')}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"{name}: ok={payload.get('ok', 'n/a')} -> {path.name}")

    code = results.get("generate_code", {})
    files = code.get("files") or {}
    if isinstance(files, dict) and files:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (GENERATED_DIR / Path(filename).name).write_text(str(content), encoding="utf-8")
            print(f"generated: {Path(filename).name}")
    elif code.get("code"):
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        (GENERATED_DIR / "qnn_runner.py").write_text(str(code["code"]), encoding="utf-8")
        print("generated: qnn_runner.py")


if __name__ == "__main__":
    main()
