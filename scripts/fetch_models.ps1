# Download the QuietCue environmental-classifier model artifacts.
# Source: Qualcomm AI Hub public release of YamNet (AudioSet, 521 classes).
# Model weights are not committed to git; run this once per clone.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $repoRoot "models\source"
$metadataDir = Join-Path $repoRoot "models\metadata"
New-Item -ItemType Directory -Force $sourceDir, $metadataDir | Out-Null

$release = "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/yamnet/releases/v0.59.0"

$floatZip = Join-Path $sourceDir "yamnet-onnx-float.zip"
if (-not (Test-Path (Join-Path $sourceDir "yamnet-onnx-float\yamnet-onnx-float\yamnet.onnx"))) {
    Write-Host "Downloading YamNet float ONNX (14 MB)..."
    Invoke-WebRequest "$release/yamnet-onnx-float.zip" -OutFile $floatZip
    Expand-Archive $floatZip -DestinationPath (Join-Path $sourceDir "yamnet-onnx-float") -Force
    Remove-Item $floatZip
}

$w8a8Zip = Join-Path $sourceDir "yamnet-onnx-w8a8.zip"
if (-not (Test-Path (Join-Path $sourceDir "yamnet-onnx-w8a8\yamnet-onnx-w8a8\yamnet.onnx"))) {
    Write-Host "Downloading YamNet w8a8 QDQ ONNX (4 MB)..."
    Invoke-WebRequest "$release/yamnet-onnx-w8a8.zip" -OutFile $w8a8Zip
    Expand-Archive $w8a8Zip -DestinationPath (Join-Path $sourceDir "yamnet-onnx-w8a8") -Force
    Remove-Item $w8a8Zip
}

$classMap = Join-Path $metadataDir "yamnet_class_map.csv"
if (-not (Test-Path $classMap)) {
    Write-Host "Downloading AudioSet class map..."
    Invoke-WebRequest "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv" -OutFile $classMap
}

Write-Host "Model artifacts ready under models\source and models\metadata."
