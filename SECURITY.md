# Security Policy

## Supported Versions

Only the latest release receives security fixes. If you're on an older version, update first.

| Version | Supported |
|---------|-----------|
| Latest  | ✅ |
| Older   | ❌ |

## Reporting a Vulnerability

**Please do not file public GitHub issues for security vulnerabilities.**

Email: **kjricciardi@gmail.com**

Include:
- What the vulnerability is and how to reproduce it
- Which component is affected (desktop app, party worker, or the join page)
- What impact you believe it has

You'll get a response within **5 business days**. If the report is valid, a fix will be prioritized for the next release and you'll be credited in the changelog (unless you prefer otherwise).

## Scope

**In scope:**
- The Cloudflare party worker (`tldps-party`) — remote code execution, data exposure, room takeover
- The desktop app — local privilege escalation, malicious log file parsing
- The join page (`github.io/STOOP/join.html`) — XSS, open redirect

**Out of scope:**
- Denial-of-service against the party worker (best-effort free infrastructure)
- Social engineering
- Issues in third-party dependencies without a clear STOOP-specific exploit path

## What STOOP Does and Doesn't Do

For reference: STOOP reads combat log files written by Throne & Liberty to disk. It does not touch the game process, store credentials, or transmit personal data. The party worker handles anonymous party sessions (no accounts, no passwords).
