# Validation record — 2026-11-10

## 0.3.2 Login always renews — 2026-11-11

- **144 automated tests passed** on Home Assistant 2026.11.1 / Python 3.14. Account login no longer exposes an automatic-renewal checkbox and always uses renewal. Existing login entries with an old OFF setting are normalized on load. Direct UserToken input retains the OFF/ON choice and preserves it during reauthentication.
- Tests cover new login form/storage, existing login and direct-token entries, legacy login-OFF renewal before expiry, and preserving a direct-token-OFF entry when merging it with old login entries. Already expired/rejected tokens still require reauthentication; no renewal after expiry is attempted.
- No live credentials were used or tokens rotated for this change.

## 0.3.1 LocalWeb TCP service activation — 2026-11-11

- **138 automated tests passed** on Home Assistant 2026.11.1 / Python 3.14. LocalWeb enables the notification service with `EpConfigAgt`, `act: notifyTcpCfg`, and an empty object `actargs` before each TCP connection, following LocalWeb manual section 5.2.2.
- Real loopback HTTP/TCP tests verify activation before login, event reception, acknowledgement, clean closure and activation on reconnect. Protocol tests cover HTTP/HTTPS addresses, configured credentials, empty-object payloads, rejected/invalid responses and timeout outcomes without opening TCP or reporting readiness prematurely.
- Native HA integration tests verify that disabling push makes no activation request and activation failure leaves device polling operational. No physical station activation or control was performed for this change.

## 0.3.0 Cloud account discovery — 2026-11-11

- **131 automated tests passed** on Home Assistant 2026.11.1 / Python 3.14. Coverage includes all-station discovery from one device snapshot, one push connection per account, colliding device/scene/remote IDs across stations, exact station-specific request signatures, station exclusions, discovery/removal and partial scene failures.
- Native HA migration tests concurrently load old station entries and preserve device/entity IDs, user names, enabled/disabled settings and registry relationships through merging and reload. Failed authentication retains migration sources; subsequent login reconfiguration preserves the pending transfer. Any existing renewal-OFF preference wins when entries merge.
- **Read-only live account login succeeded** through the native config flow and integration setup: **3 stations, 8 device records, 21 entities, 1 scene**, with authenticated WebSocket updates. The API resolved the login identifier to a numeric UserNo; the password was not stored. The tested calls were login, authorization, station/device discovery and scene discovery. No device control, scene execution, IR transmission or token-refresh call was sent.
- The live test ran in an isolated HA instance. The running NAS configuration/service was not changed. Physical multi-station commands remain untested; routing is covered with synthetic transport and native HA service tests.
- Ruff lint/format, package/version/translation/document-link checks, installation/source ZIP construction and official hassfest passed (1 integration, 0 invalid).

## 0.2.1 distribution terms — 2026-11-11

- Runtime behavior is unchanged from 0.2.0; the integration/manifest version is 0.2.1. Updated the license text, English/Korean notices and contribution terms. The installed component includes the complete LICENSE and NOTICE.
- Local lint/format, metadata/version consistency, document links and archive construction passed. Packaging validates identical root/component licenses and excludes Git history, private plans, credentials and old artifacts. The optional source ZIP includes development/CI files; SHA-256 checksums identify both generated archives. CI also builds the archives.
- This validates packaging and consistent notices, not legal enforceability. No external legal review, Marketplace catalog acceptance, public release, or visibility change was performed. The publication repository starts from the current source with no parent commits; earlier development history remains in a separate private backup. This does not revoke rights already granted under earlier terms.

## 0.2.0 manual coverage, scenes and remotes — 2026-11-11

- **117 automated tests passed** on Home Assistant 2026.11.1 / Python 3.14. Added independent inventory coverage for the device manual appendix, fixed-point/IEEE754 decoding, board/controller-mode discrimination, station-filtered scene/remote discovery, exact Cloud/LocalWeb API payloads and SPOT signing, and no-retry behavior for uncertain writes.
- Real HA service tests use synthetic devices: RGBW plus DYN batch commands, curtain stop, packed fan-coil configuration preservation, ventilation speed, siren off, scene activation and remote key sending. Scene discovery failure leaves working device entities available; newly discovered scenes are registered and removed scenes become unavailable.
- **Physical LocalWeb read-only check:** isolated HA configuration loaded **76 device records / 130 entities**, including **31 scene entities**. Scene discovery succeeded through `GetAllAIs`; remote list discovery succeeded with zero eligible non-AC remotes. Follow-up refresh and session cleanup passed. No NAS files were changed and no physical control, scene execution or IR transmission was performed.
- **Cloud live rerun:** stored UserToken was rejected and HA requested reauthentication. This token has automatic renewal OFF; it was not rotated. New Cloud scene/remote behavior is verified against simulated protocol responses, not a successful live command. Historical Cloud results below refer to earlier versions and credentials.
- Ruff, package/link/translation validation and official hassfest passed. Model coverage means documented mappings or explicit telemetry/connectivity-only recognition, not complete support for every vendor feature or physical certification of 149 products.

## 0.1.4 documented Cloud servers

96 automated tests passed on HA 2026.11.1. Coverage includes all eight API endpoints from the supplied Cloud API v1.38 manual (Appendix 2, p.228), documented WebSocket URLs (p.195), CN0 polling without an assumed push address, returned service-partition routing, US defaults in both Cloud forms, and preservation of stored global/legacy server selections. No additional regional live login or token renewal was performed.


## 0.1.3 renewal choices and documentation

79 automated tests passed on HA 2026.11.1. Direct UserToken OFF never calls refresh; ON bootstraps an unknown expiry and renews within the pre-expiry window. Tests cover stored expiry/token updates, no repeated refresh outside the window, already expired and rejected tokens, missing expiry responses, concurrent station synchronization excluding OFF entries, and repair/reauthentication preserving the renewal preference and entity identities. No live shared token was renewed.

Marketplace instructions were checked against the HA 2026.11 official release notes and installation documentation. All 45 mapped devtypes are named in English/Korean READMEs using RootON product labels. Marketplace installation of this private repository remains untested and unavailable until publication.


## Direct-token reauthentication — 2026-11-11, version 0.1.2

- **70 automated tests passed.** Direct tokens never invoke refresh, including legacy opt-in entries and known-expiry cases. Login renewal is limited to before expiry; a rejected or known-expired token requests reauthentication.
- Real HA registry/flow tests with synthetic credentials verified that an authentication failure creates the native reauthentication repair, repeated failures do not duplicate the flow, a rejected replacement leaves the saved token unchanged, and a valid replacement reloads the same entry with unchanged entity identities and clears the repair.
- Actuator-service authentication errors also initiate reauthentication without replaying the command. No real Cloud token was rotated or revoked to test this change.

## LocalWeb connection fix — 2026-11-11, version 0.1.1

- Reproduced setup failure from the NAS: `ServerDisconnectedError` when reusing an HTTP connection. A `Connection: close` request header alone did not resolve it. A dedicated connector with `force_close=True` did.
- Executed the updated LocalWeb client inside a separate Python process in the NAS HA container. Three consecutive validation/discovery cycles returned 76 physical-station device records; session cleanup succeeded. Installed integration files and the running HA service were not changed during this diagnostic.
- A separate HA 2026.11.1 instance completed the actual HTTP configuration flow against that station, loaded 76 device records and 90 mapped entities, refreshed successfully and closed its private session on unload. No physical control commands were sent. Official hassfest validation passed with zero invalid integrations.
- **60 automated tests passed**, including a simulated station rejecting reused connections, owned/injected session cleanup, HTTP hiding irrelevant TLS settings, and HTTPS fixed-port/certificate choices.
- Activation request wording now follows the owner's required LifeSmart userno/app-pw process. HTTP 8008 and HTTPS 8080 were explicitly confirmed.
- Physical HTTPS and TCP notifications, actual control operations, and the updated UI in the running NAS instance remain to be tested.

## Follow-up — 2026-11-11

- First hosted CI run: Tests and hassfest passed. HACS failed before validation because the repository is private. The workflow now skips HACS only for private repositories and runs it automatically on public visibility, subsequent pushes/PRs, or manual dispatch. A skipped HACS job does not establish catalog compatibility. Marketplace URL installation requires a public repository.

- **55 automated tests passed** on HA 2026.11.1, including two additional multi-station tests. Ruff and package structure/translation/link checks passed.
- Two LocalWeb setup flows preserve separate IP/ID/password credentials. Two simultaneously loaded station entries with identical product IDs keep separate device/entity identities and route commands to the intended station. An outage or unloading of one station leaves the other operational. These are synthetic transport tests in a real HA runtime, not physical station validation.
- English/Korean LocalWeb setup and README now explain repeated station registration explicitly. Marketplace URL distribution structure is ready locally; public publication and an actual URL installation remain pending.

## Completed

- Home Assistant **2026.11.1**, Python **3.14**, isolated Linux container.
- **53 automated tests passed**: both Cloud authentication flows, returned region propagation, token renewal policy and shared-entry synchronization, strict responses/signatures, LocalWeb identity and HTTP bodies, fragmented/bounded TCP frames, partial event merging, native platform setup, grouping, commands against mocks, reconfiguration, reload identity, failure recovery and diagnostic redaction. One upstream Home Assistant/aiohttp deprecation warning was reported.
- Official `ghcr.io/home-assistant/hassfest` validator: **1 integration, 0 invalid integrations**. Ruff lint/format and package metadata, translation parity, artwork dimensions and document-link checks passed.
- Actual Cloud login succeeded on the account's **US endpoint**; direct-token read access and WebSocket authentication succeeded. Cloud account discovery returned **19 stations / 98 device records**.
- Read-only integration setup inside a separate actual HA runtime loaded **51 device records / 129 mapped entities** for one selected station. CUBE temperature, humidity and illuminance were read and grouped as one physical product. Cloud push authenticated; an actual device-change notification was not observed in the short smoke window.
- Synthetic LocalWeb HTTP server verified identity, listing and command payloads. Synthetic TCP station verified login, fragmented notifications and acknowledgement.

No real actuator service/EpSet call was made. The user's existing Home Assistant server was inspected read-only; this integration was not installed there and the server was not restarted.

## Remaining before a verified public release

- Physical LocalWeb follow-up: HTTPS authentication, TCP notifications, reconnect and broader firmware-specific errors. HTTP identity/discovery on one station passed in 0.1.1 as recorded above.
- User-observed physical controls: switch, brightness/color temperature, cover direction/stop and climate modes. Mock tests do not establish actual model compatibility.
- Physical Cloud event updates and long-duration outage/token renewal tests. Token renewal was simulated to avoid invalidating credentials used elsewhere.
- Installation/update on the user's HA after backup; public repository release, hosted CI hassfest/Marketplace checks, clean URL installation and catalog submission.

The device matrix documents implemented mappings, not blanket physical certification. Public artifacts contain no account/station identifiers or credentials.
