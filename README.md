# TL-Logbook-Dashboard

[![Container Build](https://github.com/techlotse-AI/TL-Logbook/actions/workflows/dockerhub-monthly.yml/badge.svg)](https://github.com/techlotse-AI/TL-Logbook/actions/workflows/dockerhub-monthly.yml)
[![Security Scan](https://github.com/techlotse-AI/TL-Logbook/actions/workflows/security-scan.yml/badge.svg)](https://github.com/techlotse-AI/TL-Logbook/actions/workflows/security-scan.yml)
[![Latest Version](https://img.shields.io/badge/latest-v1.1.0-00D1C7)](https://github.com/techlotse-AI/TL-Logbook/releases/latest)
[![Docker Hub](https://img.shields.io/badge/docker-techlotse%2Ftl--logbook--dashboard-2496ED?logo=docker)](https://hub.docker.com/r/techlotse/tl-logbook-dashboard)

Dark-mode FOCA logbook dashboard for uploaded PDF exports.

TL-Logbook-Dashboard parses a FOCA paper logbook export and shows:

- Zoomable world map with airports and flown routes
- Total, PIC, dual, XC, and PIC XC time
- Aircraft type and registration breakdowns
- PIC-name, monthly, airport, route, and recent-flight tables
- Per-browser-session upload isolation for simultaneous users

This is a personal analytics tool only. It is not for operational aviation, licensing, legal records, currency, recency, insurance, or regulatory use.

## Usage Guide

End-user instructions live in the Techlotse blog post:

[Using TL-Logbook-Dashboard](https://techlotse.cloud/tl-logbook-dashboard-usage/)

The Ghost-ready post draft is included in [docs/ghost-blog-post-tl-logbook-dashboard-v1.md](docs/ghost-blog-post-tl-logbook-dashboard-v1.md).

## Quick Start

```bash
docker compose up -d
```

Open:

```text
http://localhost:8082
```

Upload a FOCA PDF from the page. Each browser session gets its own private server-side session, so simultaneous users only see the logbook uploaded in their own active session.

## Deployment

### Source Deployment

Use this when deploying from a cloned repository:

```bash
git clone https://github.com/techlotse-AI/TL-Logbook.git
cd TL-Logbook
cp .env.example .env
docker compose up -d
```

Change `HOST_PORT` in `.env` if `8082` is already in use.

### Docker Hub Deployment

Use the published image directly:

```bash
docker run -d \
  --name tl-logbook-dashboard \
  --restart unless-stopped \
  -p 8082:8000 \
  -e DATA_DIR=/data \
  -e SESSION_TTL_SECONDS=86400 \
  -e MAX_UPLOAD_BYTES=83886080 \
  -v tl-logbook-dashboard-data:/data \
  techlotse/tl-logbook-dashboard:latest
```

Open `http://localhost:8082`.

### Reverse Proxy

Put the service behind your normal TLS reverse proxy for public hosting. Forward HTTPS traffic to the app or Nginx container and preserve standard proxy headers:

- `Host`
- `X-Forwarded-For`
- `X-Forwarded-Proto`

For the included Compose stack, the public entrypoint is the `web` service on `${HOST_PORT:-8082}`.

The Compose deployment uses the published Docker Hub image, an unprivileged Nginx image, a dedicated project network, a read-only app filesystem, dropped Linux capabilities, `no-new-privileges`, `/tmp` tmpfs, and CPU/memory/PID limits.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `HOST_PORT` | `8082` | Host port exposed by the included Nginx service. |
| `APP_IMAGE` | `techlotse/tl-logbook-dashboard:latest` | Image name used by Compose. |
| `DATA_DIR` | `/data` | Container path for server-side session storage. |
| `SESSION_TTL_SECONDS` | `86400` | Session data lifetime. Defaults to 24 hours. |
| `MAX_UPLOAD_BYTES` | `83886080` | Max PDF upload size. Defaults to 80 MiB. |

## Session And Privacy Model

- Uploaded PDFs are stored per browser session in the `tl-logbook-dashboard-data` Docker volume.
- A required HTTP-only session cookie keeps active users isolated.
- The dashboard does not include analytics tracking or advertising cookies.
- Users can clear their active session from the UI.
- Runtime `data/` is gitignored for local development artifacts and should not be committed.

## Legal Hosting Notes

The app includes:

- Red operational-use disclaimer near upload
- Footer links to `/legal` and the Techlotse Impressum
- Legal, privacy, cookie, retention, external-services, warranty, and license notices

Review the copy for your exact hosting entity, jurisdiction, reverse proxy, logging, backup, and map-tile setup before public deployment.

## Airport Coordinates

ICAO/IATA coordinates come from the `airportsdata` package. Custom `ZZZZ` places are resolved from logbook remarks such as:

- `DEP: Rhino Park`
- `ARR: Roodia Aero`
- `zzzz - Roodia Aero Estate`

Add more private strips in `app/logbook_parser.py` under `CUSTOM_LOCATIONS`.

## Docker Hub Publishing

The workflow in `.github/workflows/dockerhub-monthly.yml` builds and pushes `techlotse/tl-logbook-dashboard`.

It runs:

- On pushes to `main`
- On version tags like `v1.0.0`
- Monthly on the first day of the month
- Manually through `workflow_dispatch`

Set these GitHub repository secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

The Dockerfile uses `python:slim` rather than a pinned base tag. The scheduled build uses `pull: true` and no cache so the image picks up current upstream base-image security updates on each monthly run.

Before Docker Hub login and push, the workflow builds a local image and runs Trivy against both the repository and container image. The publish job fails on fixable `CRITICAL` vulnerabilities, secret findings, or configuration misconfigurations.

## Container Security

Security checks are handled with Trivy in `.github/workflows/security-scan.yml`.

It runs:

- On pull requests
- On pushes to `main`
- Weekly on Monday
- Manually through `workflow_dispatch`

The workflow scans:

- Repository dependencies, secrets, Dockerfile, Compose, and config
- A freshly built local container image
- The published `docker.io/techlotse/tl-logbook-dashboard:latest` image on scheduled/manual runs

Reports are uploaded as GitHub Actions artifacts for 30 days and cover both `HIGH` and `CRITICAL` findings. The enforcement gate fails the build only on fixable `CRITICAL` findings, while ignoring unfixed vulnerabilities to avoid blocking on issues with no upstream remediation.

Run equivalent local checks before pushing:

```bash
docker compose build
trivy fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .
trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 techlotse/tl-logbook-dashboard:latest
```

## Release

Current version: `v1.1.0`

Releases are cut by pushing a semver tag. Update `VERSION` and `CHANGELOG.md`, then:

```bash
git tag v1.1.0
git push origin main --tags
```

Pushing a `v*.*.*` tag triggers two workflows automatically:

- `release.yml` publishes a GitHub release with generated notes.
- `dockerhub-monthly.yml` builds, scans, and pushes the matching Docker Hub tags.

## License

Personal use only. See [LICENSE](LICENSE).
