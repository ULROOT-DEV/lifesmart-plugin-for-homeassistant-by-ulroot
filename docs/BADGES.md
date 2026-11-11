# README badges and FOSSA

This page is for repository maintainers. User setup instructions belong in the READMEs; badge configuration and external service registration do not.

## Header badges

Badges are images wrapped in links. The README uses [Shields.io](https://shields.io/) for version, Home Assistant requirement, connection modes, language and license labels. They describe supported features and terms, not a third-party certification. Keep the static version aligned with `manifest.json`; the custom license badge links to LICENSE rather than advertising MIT/GPL.

Do not copy another repository's `HACS Default` badge: it can imply catalog registration. This project uses an **Add from link** installation button. Its presence is not a catalog approval claim.

## Live GitHub counts and checks

Once the repository is public, these snippets can be placed under the header. They query the actual repository/workflow rather than a manually written passing status. Public badge services may show inaccessible or unavailable results while a repository is private; do not embed access tokens in badge URLs.

```markdown
[![Stars](https://img.shields.io/github/stars/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot?style=flat-square)](https://github.com/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot/stargazers)
[![Issues](https://img.shields.io/github/issues/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot?style=flat-square)](https://github.com/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot/issues)
[![Tests](https://github.com/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot/actions/workflows/tests.yml)
[![Integration validation](https://github.com/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/ULROOT-DEV/lifesmart-plugin-for-homeassistant-by-ulroot/actions/workflows/validate.yml)
```

The validation workflow includes hassfest and conditionally HACS. Its overall success while private does not mean the skipped public HACS check passed. GitHub also provides workflow badge snippets through the workflow's **Create status badge** menu. [GitHub documentation](https://docs.github.com/en/actions/how-tos/monitor-workflows/add-a-status-badge)

## FOSSA shield and large report card

The green shield and the larger card showing **No issues found / obligations / dependencies** come from a real FOSSA project. They are license-analysis results, not a copyright registration, permission to sell, or proof that the project's license is legally enforceable.

1. Sign in to FOSSA with the account that will manage this project.
2. Import the GitHub repository using Quick Import, or analyze it through the FOSSA CLI. Review the GitHub organization/repository access requested before connecting a private repository.
3. Complete a scan and review detected licenses, dependencies and policy issues. This project uses a custom source-available license; do not label it MIT or GPL to obtain a green result. Record or review custom-license detection as appropriate for the account's features.
4. Open **Project Settings → General → Embed Status Badge**.
5. Select **License Shield** for the small header badge, or **Large** for the card shown in the example screenshot.
6. Copy the project's generated **Markdown** or **HTML** snippet into the README license section. Use the generated project locator; changing the owner/name in another project's badge does not create a FOSSA project.
7. For ongoing results, check **Settings → Hooks** or configure scans in CI. Keep API keys in GitHub Actions secrets, never in README or committed files.

For public GitHub repositories imported through Quick Import, **Submit badge PRs after import** can create the README change automatically. Private or CLI-imported projects use the copied snippet. Account features and access requirements must be checked in FOSSA before enabling it. The READMEs embed the owner's FOSSA project URLs and display live results rather than a hard-coded passing label.

## Reviewed finding: Ruff 0.14.0

On 2026-11-11, the owner connected the repository through the GitHub App and ran an issue scan. FOSSA flagged GPL-2.0-only in `crates/ty_vendored/vendor/typeshed/stdlib/urllib/robotparser.pyi` within Ruff 0.14.0. The supplied file evidence explicitly offers a choice between GNU GPLv2 and the PSF license for Python 2.2; the PSF alternative is selected for this file. This is not a blanket MIT classification of every file bundled with Ruff.

Ruff is a development lint/format tool declared in `requirements-test.txt`, not a runtime dependency of this integration. The installation and source ZIPs do not bundle Ruff or this vendored file. The source ZIP includes the development requirements so contributors can install the tool separately.

The owner's FOSSA screen subsequently showed **Active 0 / Ignored 1**. The comment feature required Premium, so this document preserves the review rationale. The ignore rule's version/project scope was not shown in the supplied confirmation screen; review it in FOSSA's Ignore Rules and restrict it to this project and Ruff 0.14.0. Reassess if the package, matching file, terms, or distribution scope changes. Do not allow GPL globally just to clear this finding.

The initial large badge reported **No issues found**, **6 obligations from 4 licenses**, and **3 dependencies**. This reflects the scanned scope and the ignored finding, not proof of complete dependency coverage or absence of license obligations. Future badge contents are controlled by FOSSA's current analysis and policies.

References: [Badge pull requests](https://docs.fossa.com/docs/project-setup/badge-pull-requests), [embed a badge and automatic updates](https://docs.fossa.com/docs/project-setup/automatic-updates#embedding-a-status-badge), [license policies](https://docs.fossa.com/docs/policies/licensing-policies), [license management](https://docs.fossa.com/docs/licenses).
