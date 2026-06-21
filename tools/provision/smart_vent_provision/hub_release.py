"""Fetch hub SD-image releases from GitHub.

Companion to `release` (which handles firmware-v* releases). The hub
workflow on every hub-v* tag publishes a release with:

    smart-vent-hub-<ver>.img.xz
    smart-vent-hub-<ver>.img.xz.sha256

This module downloads + sha256-verifies the image into a cache dir.
The `image` CLI subcommand then writes the cached file to an SD card.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import platformdirs
import requests

GITHUB_API = "https://api.github.com"
REPO = "EtaCassiopeia/smart-vent"
DEFAULT_CACHE_ROOT = Path(platformdirs.user_cache_dir("smart-vent")) / "hub"

# What the sd-image workflow publishes.
IMG_GLOB = re.compile(r"^smart-vent-hub-.*\.img\.xz$")
SHA_SUFFIX = ".sha256"


@dataclass
class HubBundle:
    version: str            # tag, e.g. "hub-v0.1.0"
    image_path: Path        # cached .img.xz
    sha256: str             # hex digest of the image
    cache_dir: Path

    @property
    def size_bytes(self) -> int:
        return self.image_path.stat().st_size


class HubReleaseError(RuntimeError):
    """Raised when a hub release can't be fetched or verified."""


def _resolve_tag(tag: str | None) -> str:
    if tag and tag != "latest":
        return tag
    url = f"{GITHUB_API}/repos/{REPO}/releases"
    resp = requests.get(url, params={"per_page": 30}, timeout=15)
    resp.raise_for_status()
    for rel in resp.json():
        name = rel.get("tag_name", "")
        if name.startswith("hub-v") and not rel.get("draft") and not rel.get("prerelease"):
            return name
    raise HubReleaseError("no published hub-v* release found")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _expected_sha(sha_file: Path) -> str:
    """Read the sha256 hex digest from a `sha256sum`-style file."""
    line = sha_file.read_text().strip().split()
    if not line:
        raise HubReleaseError(f"{sha_file} is empty")
    return line[0].lower()


def _download(url: str, dest: Path, session: requests.Session) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def fetch(tag: str | None = None, *, cache_root: Path | None = None) -> HubBundle:
    """Fetch (or load from cache) the hub SD-image release for `tag`.

    Verifies the image's sha256 against the published .sha256 file. If
    the cache is already valid, no network calls happen.
    """
    cache_root = cache_root or DEFAULT_CACHE_ROOT
    resolved = _resolve_tag(tag)
    cache_dir = cache_root / resolved
    img_cache, sha_cache = _cached_paths(cache_dir)

    if _cache_is_complete_and_valid(img_cache, sha_cache):
        return _build_bundle(resolved, cache_dir, img_cache, sha_cache)

    _populate_cache(resolved, cache_dir)
    img_cache, sha_cache = _cached_paths(cache_dir)
    _verify(img_cache, sha_cache)
    return _build_bundle(resolved, cache_dir, img_cache, sha_cache)


def _cached_paths(cache_dir: Path) -> tuple[Path | None, Path | None]:
    if not cache_dir.exists():
        return None, None
    img = next((p for p in cache_dir.iterdir() if IMG_GLOB.match(p.name)), None)
    sha = cache_dir / f"{img.name}{SHA_SUFFIX}" if img else None
    if sha is not None and not sha.exists():
        sha = None
    return img, sha


def _cache_is_complete_and_valid(img: Path | None, sha: Path | None) -> bool:
    if img is None or sha is None:
        return False
    try:
        _verify(img, sha)
    except HubReleaseError:
        return False
    return True


def _populate_cache(tag: str, cache_dir: Path) -> None:
    url = f"{GITHUB_API}/repos/{REPO}/releases/tags/{tag}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    rel = resp.json()
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}

    img_name = next((n for n in assets if IMG_GLOB.match(n)), None)
    if img_name is None:
        raise HubReleaseError(
            f"release {tag} has no smart-vent-hub-*.img.xz asset (have: {sorted(assets)})"
        )
    sha_name = f"{img_name}{SHA_SUFFIX}"
    if sha_name not in assets:
        raise HubReleaseError(f"release {tag} has {img_name} but no {sha_name}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        _download(assets[img_name], cache_dir / img_name, session)
        _download(assets[sha_name], cache_dir / sha_name, session)


def _verify(img: Path, sha: Path) -> None:
    expected = _expected_sha(sha)
    actual = _sha256(img)
    if actual != expected:
        raise HubReleaseError(
            f"sha256 mismatch for {img.name}: expected {expected}, got {actual}"
        )


def _build_bundle(version: str, cache_dir: Path, img: Path, sha: Path) -> HubBundle:
    return HubBundle(
        version=version,
        image_path=img,
        sha256=_expected_sha(sha),
        cache_dir=cache_dir,
    )
