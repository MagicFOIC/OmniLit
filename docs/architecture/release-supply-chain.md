# OmniLit release supply-chain baseline

This baseline turns dependency and license evidence into a repeatable release gate. It does not grant a
license, choose OmniLit's own distribution terms, or replace legal review.

## Generated evidence

Run:

```text
npm ci
python -m pip install --requirement services/cloud_api/requirements.in
npm run phase2:compliance
```

The command writes these ignored build artifacts under `build/compliance`:

- `omnilit-source.cdx.json`: deterministic CycloneDX 1.6 source SBOM. npm components use exact versions,
  package URLs and SHA integrity values from `package-lock.json`; Cloud Python uses exact direct
  requirements and installed metadata.
- `THIRD_PARTY_NOTICES.txt`: available license and notice texts from installed npm and Python packages,
  with explicit placeholders when a package did not ship its text.
- `compliance-report.json`: machine violations, unresolved notice gaps, manual release reviews, component
  counts and a deterministic dependency fingerprint.

`--strict` fails on missing npm license expressions, licenses outside the reviewed allow-list, missing
npm integrity, non-exact Cloud Python requirements, installed Python version mismatches, or missing
Python license policy. `--release` additionally fails every unresolved release and manual-review gate.

The allow-list in `tools/license_audit/policy.json` is intentionally explicit. Adding a dependency with a
new license requires a reviewed policy change; the generator never silently treats an unknown license as
permitted.

## Current release blockers

- There is no root `LICENSE`. Product ownership must choose and approve OmniLit's distribution terms.
- `services/cloud_api/requirements.in` is exact but the transitive, hash-locked
  `services/cloud_api/requirements.lock` is not generated. The attempted universal resolution could not
  access PyPI in the current tool environment; no unverified hashes were invented.
- The source SBOM does not represent OS packages in container base images or the native libraries copied
  by PyInstaller. Final images and desktop packages still need artifact scanning.
- Several optional platform npm packages and a few upstream packages do not include license text in the
  installed tree. Their declared SPDX expression is recorded, but the release gate retains a notice gap.
- Qt/PySide6 distribution terms, QtWebEngine Chromium notices, frozen Python/native libraries, project
  logo/assets, and Windows/macOS signing identities require evidence from the actual release package.

These blockers appear in `compliance-report.json`; they are not warnings that may be ignored for a formal
release.

## CI vulnerability and evidence gates

`.github/workflows/phase2-production-ci.yml` performs:

- `npm audit --audit-level=high` against the committed npm lock file;
- `pip-audit` against the exact Cloud direct requirements;
- deterministic source SBOM and notice generation with `--strict`;
- artifact upload of the SBOM, notices and compliance report;
- independent Cloud/Web image builds.

Before publishing, add registry image scanning that includes the base OS, signed provenance/attestations,
the universal Python hash lock, and platform-specific desktop package inventory. Scanner database outages
must be reported as unavailable evidence, not converted into a clean result.

## Formal release gate

A release workflow must stop unless all of the following are archived for the immutable release version:

1. source and final-artifact SBOMs;
2. complete third-party notices and the approved OmniLit license/copyright statement;
3. npm, Python, container OS and desktop-native vulnerability reports under an approved severity policy;
4. exact dependency locks and cryptographic artifact hashes;
5. CI provenance plus image and desktop artifact signatures;
6. Windows signature verification and macOS signing/notarization verification;
7. signed update metadata and rollback/revocation instructions.

The current CI is a pre-release evidence gate. It deliberately does not publish or sign artifacts because
no registry, signing identity, notarization credentials, or approved release license has been configured.

## Desktop signing and update trust

The desktop updater accepts only Ed25519-signed manifests using an embedded trusted public key, requires
an exact SHA-256 for the artifact, downloads to a temporary file, verifies before replacement, stages the
new executable, and rolls the previous executable back when replacement or final verification fails.
The transport now requires HTTPS for both the original URL and the final redirect, bounds manifests to
1 MiB and artifacts to 2 GiB, and accepts only numeric one-to-four-part versions.

A different hash under the same version is reported but is not installable. Every changed artifact must
increase the version, preventing replay of an older signed same-version manifest. The ignored local
Ed25519 development key is excluded from Docker build contexts; formal release mode requires an explicit
`OMNILIT_UPDATE_SIGNING_KEY_FILE` provided by the release environment.

`build_omnilit_exe.bat` signs with Authenticode and verifies the signature before hashing and signing the
update manifest when `OMNILIT_WINDOWS_SIGN_CERT_SHA1` is configured. Formal mode fails closed without
that identity. `build_omnilit_macos.sh` applies hardened-runtime codesigning, verifies with `codesign` and
Gatekeeper, submits with `notarytool`, staples and validates before creating the final archive. Formal mode
requires both `OMNILIT_MAC_SIGNING_IDENTITY` and `OMNILIT_MAC_NOTARY_PROFILE`.

The existing macOS GitHub workflow is now manual-only and labels its artifact as an unsigned smoke build;
tag pushes cannot accidentally produce a release-looking unsigned archive. Actual automated formal
release remains blocked until protected signing environments, credentials, the project license, complete
notices, artifact SBOMs and release approval are configured.
