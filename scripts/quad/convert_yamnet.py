"""Convert/quantize the YamNet ONNX model through the QUAD MCP server.

Uploads the local float ONNX, asks the server for an INT8 QDQ conversion
(the Hexagon HTP only accepts QDQ-format INT8), downloads the produced
artifact into models/converted/, and writes the raw tool envelope next to it
for the benchmark report.

Usage (from the repo root, inside the project venv):
    python scripts/quad/convert_yamnet.py [--quantization int8] [--target-sdk qnn]

Requires QUAD_MCP_URL/QUAD_MCP_TOKEN in the environment (or a discoverable
.claude/settings.json), and the fastmcp package.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from quad_mcp_client import create_client

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTED_MODEL = (
    REPO_ROOT / "models" / "source" / "yamnet-onnx-float" / "yamnet-onnx-float" / "yamnet.onnx"
)
SOURCE_MODEL = REPO_ROOT / "models" / "source" / "yamnet_fp32_selfcontained.onnx"
CONVERTED_DIR = REPO_ROOT / "models" / "converted"
DEFAULT_URL = "https://quad.infra.foundries.io/mcp"


def ensure_single_file_model() -> None:
    """Pack the external-data export into one uploadable .onnx file."""
    if SOURCE_MODEL.is_file():
        return
    if not EXTRACTED_MODEL.is_file():
        raise SystemExit(f"Source model missing: {EXTRACTED_MODEL} — run scripts/fetch_models.ps1")
    import onnx

    model = onnx.load(str(EXTRACTED_MODEL))  # resolves yamnet.data
    onnx.save_model(model, str(SOURCE_MODEL), save_as_external_data=False)
    print(f"Packed self-contained model: {SOURCE_MODEL}")


async def convert(quantization: str, target_sdk: str, runtime: str) -> dict:
    url = os.environ.get("QUAD_MCP_URL", DEFAULT_URL)
    async with create_client(url=url) as client:
        return await client.convert_model(
            source_format="onnx",
            upload=SOURCE_MODEL,
            target_sdk=target_sdk,
            quantization=quantization,
            runtime=runtime,
            download_dir=CONVERTED_DIR,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quantization", choices=("fp32", "int8", "int4"), default="int8")
    parser.add_argument(
        "--target-sdk", choices=("qnn", "snpe", "nwaios", "executorch"), default="qnn"
    )
    parser.add_argument("--runtime", default="qnn-htp")
    args = parser.parse_args()

    ensure_single_file_model()

    result = asyncio.run(convert(args.quantization, args.target_sdk, args.runtime))

    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    envelope_path = CONVERTED_DIR / f"convert-{args.quantization}-{args.target_sdk}.json"
    envelope_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print(json.dumps({k: v for k, v in result.items() if k != "logs"}, indent=2, default=str))
    local = result.get("local_path")
    print(f"\nEnvelope: {envelope_path}")
    print(f"Artifact: {local if local else '(no local artifact — check envelope)'}")


if __name__ == "__main__":
    main()
