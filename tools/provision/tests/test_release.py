"""Test release.fetch — the GitHub release downloader.

Uses `responses` to mock the GitHub API + asset downloads. Verifies:
  - resolves "latest" tag
  - downloads expected file set
  - sha256-verifies against the manifest
  - raises ReleaseError on mismatch
  - re-fetch hits the cache
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import responses

from smart_vent_provision import release as rel


SAMPLE_BOOTLOADER = b"BOOTLOADER" * 8
SAMPLE_PARTITIONS_BIN = b"PARTITIONS" * 4
SAMPLE_APP = b"APP" * 64
SAMPLE_MERGED = b"MERGED" * 64
SAMPLE_PARTITIONS_CSV = b"# partition table\nnvs, data, nvs, 0x9000, 0x6000\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_bytes() -> bytes:
    return json.dumps(
        {
            "version": "firmware-v0.1.0",
            "commit": "deadbeefcafe1234567890abcdef0123456789ab",
            "chip": "esp32c6",
            "idf_version": "v5.2.3",
            "flash": [
                {"name": "bootloader", "path": "bootloader.bin", "offset": "0x0", "sha256": _sha(SAMPLE_BOOTLOADER)},
                {"name": "partition_table", "path": "partition-table.bin", "offset": "0x8000", "sha256": _sha(SAMPLE_PARTITIONS_BIN)},
                {"name": "app", "path": "vent-controller.bin", "offset": "0x10000", "sha256": _sha(SAMPLE_APP)},
            ],
            "merged": {"path": "vent-controller-merged.bin", "offset": "0x0", "sha256": _sha(SAMPLE_MERGED)},
        }
    ).encode()


def _register_release(tag: str) -> None:
    base = f"https://example.com/{tag}"
    payloads = {
        "bootloader.bin": SAMPLE_BOOTLOADER,
        "partition-table.bin": SAMPLE_PARTITIONS_BIN,
        "partitions.csv": SAMPLE_PARTITIONS_CSV,
        "vent-controller.bin": SAMPLE_APP,
        "vent-controller-merged.bin": SAMPLE_MERGED,
        "firmware-manifest.json": _manifest_bytes(),
    }
    assets = [
        {"name": name, "browser_download_url": f"{base}/{name}"}
        for name in payloads
    ]
    responses.add(
        responses.GET,
        f"{rel.GITHUB_API}/repos/{rel.REPO}/releases/tags/{tag}",
        json={"tag_name": tag, "assets": assets},
    )
    for name, body in payloads.items():
        responses.add(responses.GET, f"{base}/{name}", body=body, status=200)


@responses.activate
def test_fetch_explicit_tag_downloads_and_verifies(tmp_path: Path):
    _register_release("firmware-v0.1.0")
    bundle = rel.fetch("firmware-v0.1.0", cache_root=tmp_path)

    assert bundle.version == "firmware-v0.1.0"
    assert bundle.chip == "esp32c6"
    assert {entry.name for entry in bundle.layout} == {"bootloader", "partition_table", "app"}
    for entry in bundle.layout:
        assert entry.path.exists()
    assert bundle.merged_image.read_bytes() == SAMPLE_MERGED


@responses.activate
def test_fetch_cached_skips_network(tmp_path: Path):
    _register_release("firmware-v0.1.0")
    rel.fetch("firmware-v0.1.0", cache_root=tmp_path)

    # Wipe registered responses; a second fetch should not hit the network.
    responses.reset()
    bundle = rel.fetch("firmware-v0.1.0", cache_root=tmp_path)
    assert bundle.version == "firmware-v0.1.0"


@responses.activate
def test_fetch_resolves_latest_to_published_release(tmp_path: Path):
    _register_release("firmware-v0.2.0")
    # The releases-list lookup is what "latest" goes through:
    responses.add(
        responses.GET,
        f"{rel.GITHUB_API}/repos/{rel.REPO}/releases",
        json=[
            {"tag_name": "hub-v0.1.0", "draft": False, "prerelease": False},
            {"tag_name": "firmware-v0.2.0", "draft": False, "prerelease": False},
            {"tag_name": "firmware-v0.1.0", "draft": False, "prerelease": False},
        ],
    )
    bundle = rel.fetch(None, cache_root=tmp_path)
    # The bundle's `version` is read from the manifest body, which is
    # always "firmware-v0.1.0" in the helper. The real assertion of
    # "latest" resolution is that the cache was created under the
    # resolved tag dir.
    assert bundle.cache_dir == tmp_path / "firmware-v0.2.0"


@responses.activate
def test_fetch_raises_on_sha256_mismatch(tmp_path: Path):
    tag = "firmware-v0.1.0"
    _register_release(tag)
    # Replace the bootloader response with corrupted bytes.
    responses.remove(responses.GET, f"https://example.com/{tag}/bootloader.bin")
    responses.add(
        responses.GET,
        f"https://example.com/{tag}/bootloader.bin",
        body=b"CORRUPTED",
        status=200,
    )
    with pytest.raises(rel.ReleaseError):
        rel.fetch(tag, cache_root=tmp_path)


@responses.activate
def test_fetch_raises_when_release_missing_files(tmp_path: Path):
    responses.add(
        responses.GET,
        f"{rel.GITHUB_API}/repos/{rel.REPO}/releases/tags/firmware-v0.1.0",
        json={"tag_name": "firmware-v0.1.0", "assets": []},
    )
    with pytest.raises(rel.ReleaseError):
        rel.fetch("firmware-v0.1.0", cache_root=tmp_path)
