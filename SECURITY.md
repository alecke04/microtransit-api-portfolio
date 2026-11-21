# Security boundaries

This repository is a standalone portfolio edition with synthetic data. It has no deployment integration, production URLs, operational GPS corpus or inherited Git/Actions history.

## Credentials

Generate independent random device and reader credentials with `python -m scripts.setup_demo`. Store them only in `.env` or your own secret store. Startup rejects absent, short, duplicate and placeholder credentials. Device keys authorize only their configured device; the reader cannot write. Database registration stores key digests. API validation responses omit submitted values, and settings hide secret strings.

Reader access is mandatory in this edition. A reader credential intentionally grants access to the configured demo fleet; it is not per-user authorization. Do not embed it in a public browser bundle. A public rider application should use an explicitly public feed or a trusted server/session layer with its own access model.

## Network and resource controls

Use HTTPS/WSS if deploying elsewhere. This example does not include plaintext TCP or MQTT ingestion. Browser origins are exact allowlists, not wildcard Vercel subdomains. Origin checks supplement authentication; they do not replace it.

Run one application process. Request/device rate limits and WebSocket connection state are bounded but process-local. Multiple processes or replicas require shared limits and a shared subscription/broadcast mechanism. Put an appropriate edge proxy, global abuse limits and request timeouts in front of any internet deployment. Do not blindly trust forwarded IP headers; the supplied server commands disable proxy-header trust.

The API caps body size, batch count, history count, telemetry lengths and WebSocket frame/application capacity. The supplied Uvicorn command also bounds incoming socket frames and queues. Slow or failed subscribers are released. Only authenticated subscriptions receive points.

## Storage and recovery

Writes commit before live notifications. The database is authoritative; a socket message is not a durable event log. After reconnecting, load REST history to recover missed points. A duplicate device timestamp returns 409; clients should check saved history after an interrupted response. Failed batches roll back atomically. Credentials and database connection strings are not part of HTTP error messages.

Schema bootstrap is an explicit local-demo command; the API does not create or migrate tables during startup. This portfolio baseline has no production migration or backup system. Existing deployments need a deliberately managed migration, backup and retention process.

## Publication and reporting

Keep `.env`, private keys, database files and collected logs out of Git. CI scans source/history and dependencies. If any actual credential is committed, revoke it before attempting history cleanup. The fresh portfolio history does not revoke credentials that may have appeared in the separate private project.

Report a suspected vulnerability through GitHub private vulnerability reporting when enabled, or contact the repository owner privately. Do not publish a real credential or private trip record in an issue. The tests and scans document checks performed; they are not a guarantee against every vulnerability.
