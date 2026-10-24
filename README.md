# Nolde Launcher

[![Tests](https://github.com/NoldeTeam/nolde-launcher/actions/workflows/tests.yml/badge.svg)](https://github.com/NoldeTeam/nolde-launcher/actions/workflows/tests.yml)

A Windows launcher for community game projects listed in the [Nolde catalog](https://nolde.pages.dev/):
decompilation, recompilation, reimplementation and port projects. It finds projects, downloads
their public Windows builds from GitHub Releases, installs them, and starts them, without Steam,
Epic or another launcher.

> **Status: Early Access 0.3.0.** Working, but not finished, and it changes quickly. See
> [Known limitations](#known-limitations).

## Install (players)

1. Open the [Releases page](https://github.com/NoldeTeam/nolde-launcher/releases) and download
   `NoldeLauncher-Setup-<version>.exe`.
2. Run it. It installs for your user only, so no administrator rights are needed.
3. Check the SHA-256 published with the release before running the installer.

Windows 10 or 11, 64-bit. The installer is not code-signed yet, so SmartScreen may warn.

## What it does

- **Discover:** search and filter the catalog, sort it, and open a project page with its
  description, sources, links and build status.
- **Install:** downloads a verified Windows `.zip` build, checks its SHA-256 when GitHub
  publishes one, and extracts it safely into your library.
- **Library:** play installed games, see play time and available updates, verify the files
  against an integrity record, open the folder, or uninstall.
- **Downloads:** progress, speed, time left, pause, resume, cancel and retry.
- **Notifications:** Windows notifications when installs finish or updates are found.
- **Launcher updates:** checked against this repository's latest release when the launcher
  starts. A new version is downloaded, its SHA-256 is verified, and you are asked before it is
  installed and the launcher restarts. Turn this off in Settings.
- **Settings:** card appearance, animation level, artwork cache limit, download limit,
  update checks, and a diagnostics export with personal data removed.

Keyboard shortcuts: Ctrl+F search, Esc back, F5 refresh the catalog, Ctrl+1 to Ctrl+4 switch pages.

## Build from source

Requires Python 3.10 or newer on Windows.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py
```

Tests and lint:

```powershell
python -m pytest tests -q
python -m pyflakes nolde_launcher tests main.py scripts
```

The application icon (`nolde_launcher/ui/assets/images/nolde.ico`) is generated from the bundled
font; regenerate it with `python scripts\make_icon.py`.

Build the installer (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php)):

```powershell
.\scripts\build_installer.ps1
```

The output is `dist\installer\NoldeLauncher-Setup-<version>.exe`.

## Project layout

```
main.py                 entry point
nolde_launcher/
  app/                  version and the service container
  models/               catalog project model (defensive parsing)
  services/             catalog, GitHub releases, downloads, installs, launching,
                        library, integrity, updates, diagnostics
  storage/              user-data paths, versioned JSON store, settings
  localization/         English strings (en.json); no hardcoded interface text
  ui/                   PySide6 pages, cards, workers, theme
tests/                  automated tests (no network access needed)
packaging/              PyInstaller spec and Inno Setup script
scripts/                build scripts and the JUnit result checker
```

## How installs stay safe

- Downloads use HTTPS and only GitHub's release-asset hosts. Redirects are checked.
- Archives are checked before extraction. Absolute paths, `..` segments, symbolic links and
  suspicious compression ratios are refused.
- Installation never runs anything. The first launch of each game needs your confirmation.
- Games start without a shell and never with elevated rights.
- Launcher updates are installed only after you agree, and only if their SHA-256 matches the
  release.

Details are in [SECURITY.md](SECURITY.md).

## Known limitations

- **Pausing depends on the server.** Resuming uses HTTP byte ranges. A server that ignores
  them restarts the download from zero.
- **Game updates replace the game folder.** Save files kept inside it are replaced. The
  confirmation dialog warns about this.
- **Installers are not code-signed.** Windows SmartScreen may warn, and the update relies on the
  SHA-256 published with each release. Check it when you install by hand.
- **Early Access 0.2.x users** must install 0.3.0 once by hand. Automatic updates start from 0.3.0.
- **Game compatibility varies.** Many projects need extra files, specific game versions or
  setup steps that the launcher does not automate. Some need a copy of the original game,
  which the launcher never provides.
- **Only GitHub Releases is supported as a source.** GitLab projects show their project page.
- **Only `.zip` archives are installed.** Other formats are reported, not downloaded.
- **Windows only.** Other systems are not supported.
- **Scrolling speed** on very large catalogs depends on the computer. The grid reuses cards,
  but painting them is still the main cost.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems privately as described in
[SECURITY.md](SECURITY.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Released under the [MIT License](LICENSE). Copyright (c) 2026 NoldeTeam.

## Third-party components

PySide6 (LGPL), requests (Apache-2.0), Inter and Space Grotesk (SIL OFL). See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The launcher is inspired by [GithubLauncher](https://github.com/SirDiabo/GithubLauncher) (MIT)
by SirDiabo. No code was copied from it.
