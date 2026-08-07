#!/usr/bin/env python3
"""Validate a float32 AI Hub-style Whisper ONNX pair and stage Android assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


MODEL_IDS = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
}


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def external_data_files(model_path: Path) -> list[Path]:
    try:
        import onnx
    except ImportError as exc:
        raise RuntimeError("Install backend/requirements-whisper-onnx.txt") from exc
    model = onnx.load_model(str(model_path), load_external_data=False)
    locations: set[str] = set()
    for initializer in model.graph.initializer:
        for entry in initializer.external_data:
            if entry.key == "location":
                locations.add(entry.value)
    result: list[Path] = []
    for location in sorted(locations):
        relative = Path(location)
        if relative.is_absolute() or len(relative.parts) != 1:
            raise ValueError("Android Whisper external data must use a same-directory filename")
        source = model_path.parent / relative
        if not source.is_file():
            raise FileNotFoundError(f"Missing ONNX external data: {source}")
        result.append(source)
    return result


def build_vocabulary(model_id: str, expected_size: int) -> dict[str, object]:
    try:
        from transformers import WhisperTokenizer
    except ImportError as exc:
        raise RuntimeError("Install backend/requirements-whisper-onnx.txt") from exc
    tokenizer = WhisperTokenizer.from_pretrained(model_id)
    vocabulary = tokenizer.get_vocab()
    maximum_id = max(vocabulary.values())
    token_bytes: list[list[int]] = [[] for _ in range(maximum_id + 1)]
    byte_decoder = tokenizer.byte_decoder
    for token, token_id in vocabulary.items():
        if all(character in byte_decoder for character in token):
            token_bytes[token_id] = [byte_decoder[character] for character in token]
    if len(token_bytes) != expected_size:
        raise ValueError(
            f"Tokenizer has {len(token_bytes)} entries but decoder emits {expected_size} logits"
        )

    def token_id(value: str) -> int:
        result = int(tokenizer.convert_tokens_to_ids(value))
        if result < 0 or result >= len(token_bytes):
            raise ValueError(f"Tokenizer is missing {value}")
        return result

    return {
        "model_id": model_id,
        "eot": token_id("<|endoftext|>"),
        "sot": token_id("<|startoftranscript|>"),
        "english": token_id("<|en|>"),
        "transcribe": token_id("<|transcribe|>"),
        "no_speech": token_id("<|nospeech|>"),
        "no_timestamps": token_id("<|notimestamps|>"),
        "token_bytes": token_bytes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=tuple(MODEL_IDS), required=True)
    parser.add_argument("--encoder", type=Path, required=True)
    parser.add_argument("--decoder", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("models/source/whisper"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.encoder.is_file() or not args.decoder.is_file():
        raise FileNotFoundError("Encoder and decoder ONNX files are required")
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("Install backend/requirements-whisper-onnx.txt") from exc
    from whisper_onnx_reference import validate_contract

    encoder = ort.InferenceSession(str(args.encoder), providers=["CPUExecutionProvider"])
    decoder = ort.InferenceSession(str(args.decoder), providers=["CPUExecutionProvider"])
    logits = next(item for item in decoder.get_outputs() if item.name == "logits")
    vocabulary_size = int(logits.shape[1])
    contract = validate_contract(encoder, decoder, vocabulary_size)
    vocabulary = build_vocabulary(MODEL_IDS[args.model], vocabulary_size)

    destination = args.output_root / args.model
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.encoder, destination / "encoder.onnx")
    shutil.copy2(args.decoder, destination / "decoder.onnx")
    copied_external: dict[str, Path] = {}
    for source in [*external_data_files(args.encoder), *external_data_files(args.decoder)]:
        previous = copied_external.get(source.name)
        if previous is not None and file_digest(previous) != file_digest(source):
            raise ValueError(f"Encoder and decoder use conflicting external file {source.name}")
        shutil.copy2(source, destination / source.name)
        copied_external[source.name] = source
    (destination / "vocabulary.json").write_text(
        json.dumps(vocabulary, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Prepared {args.model} Whisper assets in {destination}")
    print(json.dumps(contract, sort_keys=True))


if __name__ == "__main__":
    main()
