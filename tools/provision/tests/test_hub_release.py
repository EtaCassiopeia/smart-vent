"""Test hub_release.fetch — the GitHub SD-image downloader.

Mocks GH API + asset downloads via `responses`. Verifies:
  - resolves "latest" tag
  - downloads expected file set
  - sha256-verifies against the .sha256 file
  - raises HubReleaseError on mismatch / missing assets
  - re-fetch hits the cache
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import responses

from smart_vent_provision import hub_release as hr


SAMPLE_IMG = b"\xfd7zXZ" + b"FAKE-XZ-CONTENT" * 64  # not a real xz, just bytes
EXPECTED_SHA = hashlib.sha256(SAMPLE_IMG).hexdigest()


def _sha_body(filename: str) -> bytes:
    return f"{EXPECTED_SHA}  {filename}\n".encode()


def _register_release(tag: str, *, img_size: int = len(SAMPLE_IMG)) -> tuple[str, str]:
    img_name = f"smart-vent-hub-{tag}.img.xz"
    sha_name = f"{img_name}.sha256"
    base = f"https://example.com/{tag}"
    assets = [
        {"name": img_name, "browser_download_url": f"{base}/{img_name}"},
        {"name": sha_name, "browser_download_url": f"{base}/{sha_name}"},
    ]
    responses.add(
        responses.GET,
        f"{hr.GITHUB_API}/repos/{hr.REPO}/releases/tags/{tag}",
        json={"tag_name": tag, "assets": assets},
    )
    responses.add(responses.GET, f"{base}/{img_name}", body=SAMPLE_IMG)
    responses.add(responses.GET, f"{base}/{sha_name}", body=_sha_body(img_name))
    return img_name, sha_name


@responses.activate
def test_fetch_explicit_tag_downloads_and_verifies(tmp_path: Path):
    img_name, _ = _register_release("hub-v0.1.0")
    bundle = hr.fetch("hub-v0.1.0", cache_root=tmp_path)
    assert bundle.version == "hub-v0.1.0"
    assert bundle.image_path.name == img_name
    assert bundle.sha256 == EXPECTED_SHA
    assert bundle.size_bytes == len(SAMPLE_IMG)


@responses.activate
def test_fetch_cached_skips_network(tmp_path: Path):
    _register_release("hub-v0.1.0")
    hr.fetch("hub-v0.1.0", cache_root=tmp_path)

    # Wipe registered responses; second fetch should not hit the network.
    responses.reset()
    bundle = hr.fetch("hub-v0.1.0", cache_root=tmp_path)
    assert bundle.version == "hub-v0.1.0"


@responses.activate
def test_fetch_resolves_latest(tmp_path: Path):
    _register_release("hub-v0.2.0")
    responses.add(
        responses.GET,
        f"{hr.GITHUB_API}/repos/{hr.REPO}/releases",
        json=[
            {"tag_name": "firmware-v0.1.0", "draft": False, "prerelease": False},
            {"tag_name": "hub-v0.2.0", "draft": False, "prerelease": False},
            {"tag_name": "hub-v0.1.0", "draft": False, "prerelease": False},
        ],
    )
    bundle = hr.fetch(None, cache_root=tmp_path)
    # Returns the first matching hub-v* tag in the listed order.
    assert bundle.cache_dir == tmp_path / "hub-v0.2.0"


@responses.activate
def test_fetch_raises_on_sha256_mismatch(tmp_path: Path):
    tag = "hub-v0.1.0"
    img_name, sha_name = _register_release(tag)
    # Replace the image with corrupted content.
    responses.remove(responses.GET, f"https://example.com/{tag}/{img_name}")
    responses.add(
        responses.GET,
        f"https://example.com/{tag}/{img_name}",
        body=b"NOT THE IMAGE",
    )
    with pytest.raises(hr.HubReleaseError):
        hr.fetch(tag, cache_root=tmp_path)


@responses.activate
def test_fetch_raises_when_release_missing_assets(tmp_path: Path):
    responses.add(
        responses.GET,
        f"{hr.GITHUB_API}/repos/{hr.REPO}/releases/tags/hub-v0.1.0",
        json={"tag_name": "hub-v0.1.0", "assets": []},
    )
    with pytest.raises(hr.HubReleaseError):
        hr.fetch("hub-v0.1.0", cache_root=tmp_path)
