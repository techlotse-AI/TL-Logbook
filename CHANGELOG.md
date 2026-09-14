# Changelog

## v1.3.0 - 2026-09-14

Security and hardening release — closes all 2026-07-18 audit findings (#17-#24).

- Periodic session cleanup loop (hourly) plus stuck-processing eviction; cleanup no longer runs only at startup.
- PDF parsing moved to a killable subprocess with a hard `PARSE_TIMEOUT_SECONDS` wall clock; progress streamed via stdout protocol, summary handed over via file.
- Session cookies are now HMAC-signed (server-issued IDs only, secret persisted `0600` under `DATA_DIR`) and `Secure` behind HTTPS.
- nginx rate limiting on `/api/upload` (6 r/m, burst 3) and per-IP connection cap; app-side `MAX_SESSIONS` capacity guard.
- Security headers (CSP, nosniff, frame denial, referrer, permissions) on every response; SRI hashes on CDN-loaded Leaflet assets.
- Uploaded PDF deleted right after parsing (only `summary.json` is retained); raw exception text no longer sent to clients.
- `python:3.14-slim` and `nginx-unprivileged:1-alpine` pins; all workflow actions pinned to commit SHAs.
- Perf: non-blocking file writes in upload path, HTML cached at import, running-sum line grouping in the parser.

## v1.2.0 - 2026-07-18

- Updated all Python dependencies to their latest releases: `fastapi` 0.139.2, `uvicorn` 0.51.0, `PyMuPDF` 1.28.0, `pdfplumber` 0.11.10 (`airportsdata` 20260315 and `python-multipart` 0.0.32 already current).
- Updated Docker workflow actions to their latest majors: `docker/login-action` v4, `docker/build-push-action` v7, `docker/metadata-action` v6, `docker/setup-buildx-action` v4, `docker/setup-qemu-action` v4.
- Completed a security and performance audit; findings tracked in issues #17–#24.

## v1.1.0 - 2026-07-05

- Improved PDF parser performance.
- Improved Docker Compose example.
- Hardened the Dockerfile with base-image package upgrades.
- Tightened the Trivy publish gate to fail only on fixable `CRITICAL` findings.
- Bumped `python-multipart` to 0.0.32 and `PyMuPDF` to 1.26.7 to clear Dependabot security advisories (DoS, parameter smuggling, path traversal).

## v1.0.0 - 2026-05-01

Initial GitHub-ready release.

- Added session-isolated FOCA PDF uploads.
- Added dashboard analytics for total, PIC, dual, XC, and PIC XC time.
- Added aircraft type and registration breakdowns.
- Added zoomable world map with airports and routes.
- Added Techlotse dark-mode styling.
- Added operational-use disclaimer and legal/privacy notice pages.
- Added Docker Compose deployment and Docker Hub publishing workflow.
- Added personal-use-only license.
