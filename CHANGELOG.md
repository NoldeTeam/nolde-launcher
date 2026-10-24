# Changelog

## 0.3.2
- Colour themes: choose a primary colour (backgrounds) and a secondary colour (buttons and
  lines) in Settings. The other colours are derived from these two.
- Add your own app: name, author, display name, GitHub repository, release file filter,
  folder name, tags, icon address, files to copy in, mods folder, mod sources, and one folder per mod.
  Managed apps install from their repository and update from it. Manual apps have no download:
  you put the files in their folder and register the program.
- Sidebar: the GitHub mark links to the repository; the launcher's icon links to the website.
- The title bar shows only the window buttons.

## 0.3.1 - Pre Early Access
- Bugs Fixes
- Add nolde.ico

## 0.3.0 — Early Access
- First public Early Access release.
- Automatic launcher updates from GitHub releases. The installer's SHA-256 is verified before
  anything is installed, and the launcher asks before it restarts.
- Welcome message on the first launch, explaining the Early Access status.
- Link to the GitHub repository, next to the website link.
- Release workflow publishes a `.sha256` file next to the installer.

## 0.2.0
- Virtualised catalog and library grids; cards are reused while scrolling.
- Motion levels (full, reduced, off), chosen in Settings.
- Artwork disk limit with oldest-first cleanup and a clear-cache button.
- Discover sorting by name, recent update or development progress.
- Pause and resume for downloads.
- Play time per game.
- Game update checks and in-place updates that keep play time and launch options.
- Launcher update check against an HTTPS manifest, with SHA-256 verification.
- Diagnostics export with personal data removed.
- Keyboard shortcuts: Ctrl+F, Esc, F5, Ctrl+1 to Ctrl+4.
- Windows notifications through the system tray.
- Integrity records and verification for installed games.
- Per-user Windows installer (Inno Setup).

## 0.1.0
- First working version: catalog, library, downloads, installation and launching.
