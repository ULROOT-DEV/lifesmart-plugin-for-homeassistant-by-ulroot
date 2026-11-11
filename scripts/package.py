"""Create a local release ZIP from an allowlist; no secrets or planning files."""

import hashlib
import json
import zipfile
from pathlib import Path

from validate import main as validate

ROOT = Path(__file__).resolve().parents[1]


def write_archive(output, files):
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert not any(
            name.startswith(("intent/", ".local/", ".git/")) for name in archive.namelist()
        )
        assert "CHANGELOG.md" not in archive.namelist()
        assert archive.read("LICENSE") == archive.read("custom_components/lifesmart_ulroot/LICENSE")
        assert "custom_components/lifesmart_ulroot/NOTICE" in archive.namelist()
    print(f"Created {output.name}: {len(set(files))} files")


def distributable_files(directory):
    return [
        p
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]


def main():
    validate()
    component = ROOT / "custom_components/lifesmart_ulroot"
    version = json.loads((component / "manifest.json").read_text())["version"]
    output = ROOT / "dist" / f"lifesmart-ulroot-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    files = [ROOT / name for name in ("README.md", "LICENSE", "hacs.json", "CONTRIBUTING.md")]
    for directory in (component, ROOT / "docs"):
        files.extend(distributable_files(directory))
    write_archive(output, files)
    # A fresh publication snapshot: no Git history, earlier tags, or old archives.
    source_files = files + [
        ROOT / name for name in (".gitignore", "pyproject.toml", "requirements-test.txt")
    ]
    for name in ("scripts", "tests", ".github/workflows"):
        source_files.extend(distributable_files(ROOT / name))
    source_output = ROOT / "dist" / f"lifesmart-ulroot-{version}-source.zip"
    write_archive(source_output, source_files)
    checksum_output = ROOT / "dist" / f"lifesmart-ulroot-{version}-SHA256SUMS.txt"
    checksum_output.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in (output, source_output)
        ),
        encoding="utf-8",
    )
    print(f"Created {checksum_output.name}")


if __name__ == "__main__":
    main()
