# Crash diagnostics and privacy boundary

OmniLit separates crash recovery from diagnostic sharing. Recovery and local collection work without a Cloud
account. Cloud sharing is disabled by default and starts only after the signed-in user enables
`shareDiagnostics` in Account → Research data controls.

## Local collection

- Qt startup, main-thread, worker-thread, QML, WebEngine, and Local Agent failures are classified into bounded
  JSON reports under the platform crash directory.
- React render errors, uncaught browser errors, and unhandled promise rejections are retained only in the
  current tab's `sessionStorage`.
- Both stores retain at most 20 reports. Collection failures never replace normal error handling or prevent
  the React error boundary from offering page reload.
- Local reports never persist exception messages, stack text, URLs, command-line arguments, current working
  directories, tokens, user paths, or research content. Stack metadata is used only as input to a one-way
  fingerprint on desktop.

## Opt-in Cloud sharing

The authenticated `POST /v1/diagnostics` route accepts only the shared `DiagnosticReportCreateRequest` schema.
It contains an ISO timestamp, enumerated source, controlled error code, whitelisted exception class, hexadecimal
fingerprint, severity, and bounded application version. Additional properties such as `message`, `stack`, `url`,
`path`, arbitrary context, actor ID, email, tenant resource ID, or research identifiers are rejected.

The Cloud service applies all of these controls:

- `shareDiagnostics=false` by default and a `403 diagnostic_sharing_disabled` response until explicit opt-in;
- normal Cloud authentication and origin enforcement;
- route rate limiting plus at most 100 accepted reports per tenant in 24 hours;
- a 30-day retention window and at most 500 retained reports per tenant;
- no user/actor column in the diagnostic table;
- tenant foreign-key isolation, account-export inclusion, and owner account deletion cascade;
- schema-v1 to schema-v2 additive migration inside one SQLite transaction.

The Web runtime reads the current session at event time, so revoking consent stops new uploads immediately. The
account-control response is written back to the current-tab session; a new login is not required. Upload errors
are intentionally swallowed after the local privacy-safe report is stored so reporting cannot create a crash
loop.

## Current boundary

The React runtime is connected to opt-in Cloud sharing. Desktop/Qt reports remain local because desktop Cloud
account transport and a user-facing review/send flow have not yet been implemented. The endpoint already accepts
the desktop source classifications, but local files are never uploaded implicitly. External incident tooling,
notification delivery, SLO ownership, and an on-call process remain deployment work; this repository does not
claim that those services are active.
