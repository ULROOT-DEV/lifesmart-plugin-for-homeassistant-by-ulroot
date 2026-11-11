# Development

Runtime: Home Assistant 2026.11.1, Python 3.14, asyncio/aiohttp. No additional runtime packages are required beyond Home Assistant. Develop/test on Linux or in a Linux container; Home Assistant is not a native Windows runtime.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install homeassistant==2026.11.1 -r requirements-test.txt
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
python scripts/test.py -q
python scripts/validate.py
python scripts/package.py
```

`scripts/test.py` initializes the HA runtime before pytest and enables only pytest-asyncio. Tests use real HA config entries, entity/device registries and service calls with simulated transports. HTTP and TCP station tests use loopback servers. Test data is synthetic and needs no account secrets or physical devices.

The local installation package is `dist/lifesmart-ulroot-0.3.2.zip`. Packaging uses an allowlist: runtime, public docs, metadata, license, notices and contribution terms. Development plans, credentials, tests and caches are excluded. `CHANGELOG.md` is local-only, ignored by Git and excluded from both archives. The root and installed component both carry the same full LICENSE, verified before packaging.

`dist/lifesmart-ulroot-0.3.2-source.zip` additionally includes tests, scripts, CI and development metadata for a fresh source publication. Neither archive includes `.git`, commit history, old release artifacts, `intent/`, or `.local/`. Validate both archives before publication.

## Structure

- `api/`: Cloud signing/authentication, LocalWeb HTTP and bounded push transports.
- `models.py`, `devices.py`, `manual_devices.py`: normalized snapshots, typed readings, existing mappings and manual device families. Keep board/controller-mode distinctions explicit and never infer writable channels solely from their names.
- `coordinator.py`: one Cloud account or LocalWeb station, station-qualified state, shared push/poll recovery and command serialization.
- `identity.py` / `migration.py`: stable account/station identities and migration of legacy Cloud entries without replacing device/entity registry IDs.
- `config_flow.py`: login/token/LocalWeb UI, reauthentication, reconfiguration and options.
- Platform modules: native HA entities; `diagnostics.py`: sanitized summary.

Scenes use native `scene` entities and existing LifeSmart definitions; remotes send documented non-AC SPOT keys. Their discovery runs separately from device capabilities and must not break device polling when unsupported. Validate protocol payloads and uncertain-write handling with mocks before any user-observed actuator test. Manual references and partial-support limits live in [SUPPORTED_DEVICES.md](SUPPORTED_DEVICES.md).

Stable identities combine station, device and capability, independent of connection mode. An uncertain write is never automatically repeated. Unsupported channels do not become writable entities. Cloud passwords are used only for token issuance; tokens and LocalWeb credentials remain in HA config entry storage.

## Release process

The current distribution uses ULROOT Source-Available License 1.0. At the owner's direction, version 0.3.2 is published as one parentless commit containing the current files. The public repository URL is unchanged. Future history rewrites require an explicit owner instruction.

The history-free source ZIP is an optional publication snapshot. Resetting publication history does not revoke rights in copies already lawfully supplied under earlier terms. Old local ZIPs remain private historical artifacts, not current distribution candidates. Packaging scripts do not change repository visibility or publish releases.

Keep the release version, license text, commit/tag and original ZIP together when documenting the terms of a distribution. Packaging writes `dist/lifesmart-ulroot-0.3.2-SHA256SUMS.txt` with the exact installation/source ZIP hashes. These records help identify the files supplied; they are not independent legal certification or trusted timestamps. Preserve records of any separate commercial permissions as well.

Review third-party notices and legal terms before public distribution. No external legal review or Marketplace catalog acceptance of the custom license has been completed. Do not claim that passing automated checks establishes either. Contributions follow [CONTRIBUTING.md](../CONTRIBUTING.md); a new commercial license for contributed code may require the relevant copyright holders' permission.

Pushes and pull requests automatically run tests and hassfest. HACS catalog review is a separate, manual workflow: **Actions → HACS catalog review (manual) → Run workflow**. It runs only for public repositories. The current custom license fails the catalog's OSI-approved license requirement; that known policy conflict must not cause a failure notification on every push. Manual review still reports failures normally, and moving it out of automatic CI does not mean catalog approval. URL-based custom installation remains separate from default catalog inclusion. See the [HACS license requirement](https://hacs.xyz/docs/publish/include/#check-license).

1. Complete remaining physical checks in [VALIDATION.md](VALIDATION.md), recording model and firmware without identifying information.
2. Run lint, tests, structure validation, hassfest and Marketplace/HACS validation. GitHub workflows are included; external repository checks run after publication.
3. Update the manifest version and local change notes, build and inspect the ZIP, commit reviewed source and publish a GitHub release/tag. Do not stage or upload `CHANGELOG.md`.
4. Verify a clean Marketplace **Add from link** install and update using the public repository URL.
5. Submit for [catalog inclusion](https://contributors.home-assistant.io/marketplace/guides/catalog/) once the release is verified.

Do not publish `.local/`, `intent/`, credentials, private raw snapshots or HA configuration backups. Never copy production secrets into test fixtures or CI.

## README presentation

Keep the English/Korean READMEs focused on installation and use. Internal test records and protocol provenance belong in the linked technical documents. Badge maintenance and FOSSA setup are described in [BADGES.md](BADGES.md). Do not publish a FOSSA passing card without an actual project analysis, or a catalog badge before catalog registration.
