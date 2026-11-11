"""Validate distributable structure, translation parity and local document links."""

import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/lifesmart_ulroot"


def leaves(value, prefix=""):
    if isinstance(value, dict):
        return {key for name, child in value.items() for key in leaves(child, f"{prefix}.{name}")}
    return {prefix}


def main():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert manifest["domain"] == COMPONENT.name
    assert manifest["config_flow"] is True
    constants = (COMPONENT / "const.py").read_text(encoding="utf-8")
    assert f'VERSION = "{manifest["version"]}"' in constants, "Version constants differ"
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("ULROOT Source-Available License 1.0\n")
    assert (COMPONENT / "LICENSE").read_text(encoding="utf-8") == license_text, (
        "Installed component must carry the complete current license"
    )
    assert (COMPONENT / "NOTICE").is_file(), "Installed attribution notices missing"
    assert hacs["homeassistant"] == "2026.11.1"
    assert all(
        manifest.get(k) for k in ("name", "version", "documentation", "issue_tracker", "codeowners")
    )
    assert [
        p.name
        for p in (ROOT / "custom_components").iterdir()
        if p.is_dir() and p.name != "__pycache__"
    ] == [COMPONENT.name]
    en = json.loads((COMPONENT / "translations/en.json").read_text(encoding="utf-8"))
    ko = json.loads((COMPONENT / "translations/ko.json").read_text(encoding="utf-8"))
    assert leaves(en) == leaves(ko), "Translation keys differ"
    assert re.search("[\uac00-\ud7a3]", json.dumps(ko, ensure_ascii=False)), "Korean text missing"
    assert "ss.kim@ulroot.com" in (ROOT / "README.md").read_text(encoding="utf-8")
    for path in [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *(ROOT / "docs").rglob("*.md")]:
        text = path.read_text(encoding="utf-8")
        assert "\ufffd" not in text, f"Invalid text encoding: {path}"
        assert "???" not in text, f"Possible text encoding loss: {path}"
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in target or target.startswith(("mailto:", "#")):
                continue
            resolved = (path.parent / target.split("#")[0]).resolve()
            assert resolved.exists(), f"Broken link: {path.name} -> {target}"
            assert "intent" not in resolved.relative_to(ROOT).parts, (
                "Public docs link to ignored planning files"
            )
    image = (COMPONENT / "brand/icon.png").read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack("!II", image[16:24]) == (256, 256)
    print("Package structure, licenses, versions, translations, brand and document links: PASS")


if __name__ == "__main__":
    main()
