# Artwork and reference sources

The ULROOT project owner requested reuse of the existing RootON artwork for this integration. The following files were copied without modification. They retain their original ownership and are excluded from the ULROOT Source-Available License's code grant. Inclusion here does not grant trademark rights or permission to use them in unrelated products. Third-party code and runtime dependencies also retain their own licenses; see the installed [NOTICE](../custom_components/lifesmart_ulroot/NOTICE).

| Bundled file | Original source |
|---|---|
| `custom_components/lifesmart_ulroot/brand/icon.png` | RootONLocal: `apps/common/public/logo.png` |
| `docs/assets/station.webp` | RootONWeb: `apps/common/public/img/control-images/NO3_Station.webp` |
| `docs/assets/polar-switch.webp` | RootONWeb: `apps/common/public/img/control-images/NO11_Polar스위치2구.webp` |
| `docs/assets/air-switch.webp` | RootONWeb: `apps/common/public/img/control-images/No8_Air스위치.webp` |

The integration uses standard Home Assistant entity icons. Product illustrations are documentation assets; they do not replace every dashboard card icon automatically.

Protocol behavior was studied in RootONWeb, RootONLocal, and RootONApp, with structural comparisons to [iKaew/hass-lifesmart-addon](https://github.com/iKaew/hass-lifesmart-addon) and [MapleEve/lifesmart-for-homeassistant](https://github.com/MapleEve/lifesmart-for-homeassistant). This repository contains a new Python implementation; no source files from those two public integrations were copied. References are not endorsements or compatibility guarantees.

## README illustration

`docs/assets/readme-banner.svg` is an original vector illustration created for this integration. It may be redistributed unchanged with this project's documentation. Its generic house, cloud and device symbols do not claim certification or endorsement by Home Assistant or LifeSmart. Brand/trademark rights are not granted.
