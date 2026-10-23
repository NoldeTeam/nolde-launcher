# Build a Windows folder distribution of Nolde Launcher.
# Run in PowerShell from the project root after: pip install -r requirements-dev.txt
$ErrorActionPreference = "Stop"
python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; not building." }
python -m PyInstaller packaging/nolde_launcher.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
Write-Host "Built dist/NoldeLauncher/NoldeLauncher.exe"
