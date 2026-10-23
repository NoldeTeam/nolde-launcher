# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Use GitHub's
"Report a vulnerability" button in the Security tab of this repository. Include the
launcher version, Windows version, and steps to reproduce.

We will acknowledge the report, investigate, and publish a fix with a note in the changelog.

## What the launcher does to protect you

- Downloads are limited to HTTPS and to GitHub's release-asset hosts. Redirects are checked.
- Archives are checked before extraction: absolute paths, `..` segments, symbolic links and
  suspicious compression ratios are refused.
- When GitHub publishes a SHA-256 for an asset, the download is verified before installation.
- Installation never runs anything. The first launch of each game needs explicit confirmation.
- Games are started without a shell and never with elevated rights.

## Limits to be aware of

- Release installers are not code-signed yet, so Windows SmartScreen may warn.
- Games come from third-party projects. Trust the source before you run them.
