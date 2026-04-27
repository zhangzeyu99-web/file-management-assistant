# Security Policy

## Supported Versions

The `main` branch is the supported version.

## Reporting Security Issues

Open a private report through GitHub if available, or create an issue with reproduction details and omit secrets.

## Secret Handling

Do not commit:

- Notification provider app secrets.
- Access tokens.
- Webhooks.
- Open IDs.
- OpenClaw private config files.
- Codex or OpenClaw session archives.

Use `config.local.json` for machine-specific paths. It is ignored by Git.

## Safety Scope

This project is report-first and local-first. It does not delete, move, rename, or rewrite source files by default.

Any future destructive operation must include:

- Explicit allow-list.
- Dry-run manifest.
- Rollback plan.
- Tests.
- Human confirmation before enabling scheduled execution.
