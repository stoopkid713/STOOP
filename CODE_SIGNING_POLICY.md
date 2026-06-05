# Code Signing Policy — STOOP

## Certificate

STOOP releases are signed using the **SignPath Foundation** free OSS code-signing program.

> **Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org)**

The code-signing certificate is issued to **SignPath Foundation** (not to the individual maintainer). SignPath Foundation acts as the publisher for OSS projects it sponsors.

## Team roles (solo maintainer)

| Role | Who | Responsibility |
|------|-----|----------------|
| Author | Kyle Ricciardi | Writes code; initiates signing requests |
| Reviewer | Kyle Ricciardi | Reviews build artifacts before approval |
| Approver | Kyle Ricciardi | Approves each release in the SignPath UI |

All three roles are held by the sole maintainer, as explicitly permitted by SignPath Foundation for single-maintainer projects.

## Build & signing process

- All release artifacts are built via **GitHub Actions** on **GitHub-hosted `windows-latest` runners** — not on local machines.
- Build output (`STOOP.exe`, `STOOP-Setup.exe`, `STOOP-portable.zip`) is uploaded as GitHub workflow artifacts before signing.
- SignPath performs Authenticode signing on its HSM; the private key never leaves SignPath's infrastructure.
- Every release requires **manual approval** in the SignPath UI before artifacts are signed and published.
- Artifacts are timestamped (RFC 3161) so signatures remain valid after certificate expiry.

## Source verifiability

All source code is publicly available at [github.com/stoopkid713/STOOP](https://github.com/stoopkid713/STOOP). Any user can reproduce the build by following the instructions in [README.md](README.md).

## Privacy

STOOP sends combat log data to a cloud relay (the party worker at `tldps-party.kyle-526.workers.dev`) **only** when the user explicitly joins a party session. No personal data, telemetry, or usage analytics are transmitted at any time. The party worker processes only the data needed to render the real-time party scoreboard.

> "This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it."

## Download page attribution

The [releases page](https://github.com/stoopkid713/STOOP/releases) and the [README](README.md) note that STOOP is signed using the SignPath Foundation certificate.
