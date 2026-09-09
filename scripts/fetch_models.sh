#!/usr/bin/env bash
# Download the QuietCue environmental-classifier model artifacts (macOS/Linux
# counterpart of fetch_models.ps1).
# Source: Qualcomm AI Hub public release of YamNet (AudioSet, 521 classes).
# The w8a8 export is checked in; the float export (15 MB) is not, and the hub
# prefers it when present because its confidences are continuous rather than
# quantized onto a coarse ladder.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir="$repo_root/models/source"
metadata_dir="$repo_root/models/metadata"
mkdir -p "$source_dir" "$metadata_dir"

release="https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/yamnet/releases/v0.59.0"

fetch_zip() {
  local name="$1" size="$2"
  if [ -f "$source_dir/$name/$name/yamnet.onnx" ]; then
    return
  fi
  echo "Downloading YamNet $name ($size)..."
  curl -fsSL "$release/$name.zip" -o "$source_dir/$name.zip"
  unzip -o -q "$source_dir/$name.zip" -d "$source_dir/$name"
  rm "$source_dir/$name.zip"
}

fetch_zip yamnet-onnx-float "14 MB"
fetch_zip yamnet-onnx-w8a8 "4 MB"

class_map="$metadata_dir/yamnet_class_map.csv"
if [ ! -f "$class_map" ]; then
  echo "Downloading AudioSet class map..."
  curl -fsSL "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv" -o "$class_map"
fi

echo "Model artifacts ready under models/source and models/metadata."
