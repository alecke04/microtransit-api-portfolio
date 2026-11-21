# Portfolio publication review

Prepared November 21, 2026.

This is a curated extraction of the original backend's core GPS models, validation, persistence and HTTP/WebSocket architecture, with standalone configuration and additional security controls. It is intentionally a smaller reference implementation. It does not claim to reproduce the original operational ETA/trip planner, calibration or deployment.

The public tree starts with a new root commit. No private branches, tags, pull-request refs, workflow history, artifacts, Git metadata, recordings or deployment credentials are transferred.

Included:

- Core device, GPS and heartbeat models adapted from the original backend.
- Async transactional writes, PostGIS point conversion and bounded history queries.
- Standalone HTTP and authenticated WebSocket endpoints with resource controls.
- Generated loopback-only demo data and random local credentials.
- Unit/API/security checks and isolated PostGIS integration checks.
- CI with read-only repository permissions and dependency/source scans.

Excluded:

- Historical private Git commits and credential values.
- Field recordings, raw GPS/heartbeat logs and research datasets.
- Production route geometry, historical ETA profiles, field-day metrics and trained calibration assets.
- Private deployment URLs, Railway/account configuration, firmware provisioning and optional TCP/MQTT ingestion.
- Private workflow logs, artifacts and old deployment hooks.

The original repository remains private and is not a deployment target of this public repository. Replacing that deployment, rotating its hardware credentials or publishing its operational datasets requires a separate task. No claim is made here that historical credentials were revoked.
