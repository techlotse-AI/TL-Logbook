# Changelog

## v1.3.0 - 2026-07-19

Security and hardening release closing all findings from the 2026-07-18 audit (issues #17-#24).

- Added an hourly session-cleanup task and eviction of stuck sessions; cleanup no longer runs only at startup.
- Moved PDF parsing into an isolated subprocess with a hard `PARSE_TIMEOUT_SECONDS` limit (default 120 s).
- Session cookies are now HMAC-signed so only server-issued session IDs are accepted, and set `Secure` behind HTTPS.
- Added nginx rate limiting on uploads, a per-IP connection cap, and an app-side `MAX_SESSIONS` capacity guard.
- Added security headers (CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`) and Subresource Integrity hashes on CDN-loaded Leaflet assets.
- Uploaded PDFs are deleted immediately after parsing; only the derived summary is retained, and parse errors no longer expose internal details.
- Pinned `python:3.14-slim` and `nginx-unprivileged:1-alpine` base images and all GitHub Actions to commit SHAs.
- Performance: non-blocking upload writes, cached HTML responses, faster parser line grouping.

Note: existing browser sessions are re-issued cookies on first visit after upgrade (previous unsigned cookies are no longer honored).

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
