# Build the Windows installer: tests, PyInstaller folder build, then Inno Setup.
# Run from the project root in PowerShell, after: pip install -r requirements-dev.txt
# and after installing Inno Setup 6 (https://jrsoftware.org/isinfo.php).
param([string]$Version = "")
$ErrorActionPreference = "Stop"

if (-not $Version) {
    $Version = python -c "import sys; sys.path.insert(0, '.'); from nolde_launcher.app.version import __version__; print(__version__)"
}
Write-Host "Building Nolde Launcher $Version"

python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; not building." }

python -m PyInstaller packaging/nolde_launcher.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) { $iscc = $iscc.Source } else { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found. Install it, then run this script again." }

& $iscc "/DMyAppVersion=$Version" packaging\installer\NoldeLauncher.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }
Write-Host "Installer written to dist\installer\NoldeLauncher-Setup-$Version.exe"
