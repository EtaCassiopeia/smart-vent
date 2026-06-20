"""Fetch firmware release artifacts from GitHub Releases.

The CI workflow on every firmware-v* tag publishes a release with:
  bootloader.bin, partition-table.bin, vent-controller.bin,
  vent-controller-merged.bin, partitions.csv, firmware-manifest.json

This module downloads the set into a cache dir (under platformdirs)
and verifies every file's sha256 against the manifest before returning
the local paths.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import platformdirs
import requests

GITHUB_API = "https://api.github.com"
REPO = "EtaCassiopeia/smart-vent"
DEFAULT_CACHE_ROOT = Path(platformdirs.user_cache_dir("smart-vent")) / "firmware"

# Files we expect in every firmware release.
EXPECTED_FILES = (
    "bootloader.bin",
    "partition-table.bin",
    "partitions.csv",
    "vent-controller.bin",
    "vent-controller-merged.bin",
    "firmware-manifest.json",
)


@dataclass
class FlashLayout:
    """A single piece of the per-board flash, with its target offset."""

    name: str  # "bootloader" | "partition_table" | "app"
    path: Path  # local path to the binary
    offset: str  # e.g. "0x0", "0x8000", "0x10000"


@dataclass
class FirmwareBundle:
    version: str
    commit: str
    chip: str
    idf_version: str
    cache_dir: Path
    layout: list[FlashLayout]
    merged_image: Path

    @property
    def manifest_path(self) -> Path:
        return self.cache_dir / "firmware-manifest.json"


class ReleaseError(RuntimeError):
    """Raised when a release can't be fetched or verified."""


def _resolve_tag(tag: str | None) -> str:
    """Resolve None/`latest` to the actual latest firmware-v* tag."""
    if tag and tag != "latest":
        return tag
    url = f"{GITHUB_API}/repos/{REPO}/releases"
    resp = requests.get(url, params={"per_page": 30}, timeout=15)
    resp.raise_for_status()
    for rel in resp.json():
        name = rel.get("tag_name", "")
        if name.startswith("firmware-v") and not rel.get("draft") and not rel.get("prerelease"):
            return name
    raise ReleaseError("no published firmware-v* release found")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(asset_url: str, dest: Path, session: requests.Session) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(asset_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)


def fetch(tag: str | None = None, *, cache_root: Path | None = None) -> FirmwareBundle:
    """Fetch (or load from cache) the firmware release for the given tag.

    Verifies every binary's sha256 against the manifest. If the cache
    is already populated and verifies clean, no network calls happen.
    """
    cache_root = cache_root or DEFAULT_CACHE_ROOT
    resolved = _resolve_tag(tag)
    cache_dir = cache_root / resolved

    if not _cache_is_complete_and_valid(cache_dir):
        _populate_cache(resolved, cache_dir)
        _verify_cache(cache_dir)

    return _build_bundle(cache_dir)


def _cache_is_complete_and_valid(cache_dir: Path) -> bool:
    if not all((cache_dir / f).exists() for f in EXPECTED_FILES):
        return False
    try:
        _verify_cache(cache_dir)
    except ReleaseError:
        return False
    return True


def _populate_cache(tag: str, cache_dir: Path) -> None:
    url = f"{GITHUB_API}/repos/{REPO}/releases/tags/{tag}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    rel = resp.json()
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    missing = [f for f in EXPECTED_FILES if f not in assets]
    if missing:
        raise ReleaseError(f"release {tag} is missing assets: {', '.join(missing)}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        for name in EXPECTED_FILES:
            _download(assets[name], cache_dir / name, session)


def _verify_cache(cache_dir: Path) -> None:
    manifest_path = cache_dir / "firmware-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest.get("flash", []):
        local = cache_dir / entry["path"]
        actual = _sha256(local)
        if actual != entry["sha256"]:
            raise ReleaseError(
                f"sha256 mismatch for {entry['path']}: expected {entry['sha256']}, got {actual}"
            )
    merged = manifest.get("merged")
    if merged:
        local = cache_dir / merged["path"]
        actual = _sha256(local)
        if actual != merged["sha256"]:
            raise ReleaseError(
                f"sha256 mismatch for {merged['path']}: expected {merged['sha256']}, got {actual}"
            )


def _build_bundle(cache_dir: Path) -> FirmwareBundle:
    manifest = json.loads((cache_dir / "firmware-manifest.json").read_text())
    layout = [
        FlashLayout(name=e["name"], path=cache_dir / e["path"], offset=e["offset"])
        for e in manifest["flash"]
    ]
    merged = cache_dir / manifest["merged"]["path"]
    return FirmwareBundle(
        version=manifest["version"],
        commit=manifest["commit"],
        chip=manifest["chip"],
        idf_version=manifest["idf_version"],
        cache_dir=cache_dir,
        layout=layout,
        merged_image=merged,
    )
