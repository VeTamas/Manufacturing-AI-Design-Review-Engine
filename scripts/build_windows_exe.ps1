# Build Windows EXE for CNC Review Agent (windowed, no console).
# Run from repository root: .\scripts\build_windows_exe.ps1
# Optional: .\scripts\build_windows_exe.ps1 -IncludeHFCache

param(
    [switch]$IncludeHFCache
)

$ErrorActionPreference = "Stop"
$entry = "app/run_desktop_gui.py"
$name = "CNCReviewAgent"

$args = @(
    "--windowed",
    "--name", $name,
    "--paths", "."
)

# Collect full packages for Streamlit and sentence-transformers stacks
$collectAll = @(
    "streamlit",
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "tokenizers",
    "safetensors"
)
foreach ($pkg in $collectAll) {
    $args += "--collect-all"
    $args += $pkg
}

if ($IncludeHFCache) {
    # Windows: source;dest (semicolon). Bundle .cache/hf into the EXE directory.
    $args += "--add-data"
    $args += ".cache\hf;.cache\hf"
}

$args += $entry

$cmd = "pyinstaller " + ($args -join " ")
Write-Host "Running: $cmd"
& pyinstaller @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Output: dist\$name\${name}.exe (or dist\$name.exe with --onefile)"
