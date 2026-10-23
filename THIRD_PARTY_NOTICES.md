# Third-party notices

## Functional reference
Nolde Launcher was designed after studying the workflow of **GithubLauncher**
by SirDiabo (https://github.com/SirDiabo/GithubLauncher), which is released
under the **MIT License**. No source code from that project was copied or
translated; this implementation is independent Python code. If any MIT-licensed
code is ever reused, its copyright notice and license text must be preserved.

## Bundled fonts
- **Inter** (Rasmus Andersson) — SIL Open Font License 1.1. Licence text:
  `nolde_launcher/ui/assets/fonts/LICENSE-Inter.txt`.
- **Space Grotesk** (Florian Karsten) — SIL Open Font License 1.1. Licence text:
  `nolde_launcher/ui/assets/fonts/LICENSE-SpaceGrotesk.txt`.

Both fonts may be bundled and redistributed with the application under the OFL,
provided the licence text travels with them, as it does here.

## Runtime dependencies
- **PySide6 / Qt for Python** — LGPL-3.0 / GPL / commercial. Distribution of a
  packaged build must comply with the LGPL terms (for example, allowing users
  to replace the Qt libraries). Review the Qt licensing documentation before
  publishing a release.
- **requests** — Apache-2.0.
- **PyInstaller** (build tool only) — GPL-2.0 with a bootloader exception that
  permits distributing bundled applications.

Verify these against the exact versions you package before publishing.
