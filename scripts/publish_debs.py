#!/usr/bin/env python3
"""Publish Debian packages to signed static APT metadata in docs/.

APT_GPG_KEY_ID must identify a signing-capable SECRET key already loaded in
GnuPG; do not put private key material in this repository.

Example:
    APT_GPG_KEY_ID=FINGERPRINT python3 scripts/publish_debs.py dist/*.deb
"""

import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"
SUITE = "stable"
PACKAGE = "rhtop"
ARCHES = ("amd64", "arm64")
POOL = SITE / "pool" / "main" / "p" / PACKAGE
DIST = SITE / "dists" / SUITE
KEY_OUTPUT = SITE / "formaggio-software-archive-keyring.pgp"


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def deb_field(path: Path, field: str) -> str:
    return run(
        ["dpkg-deb", "--field", str(path), field], text=True, stdout=subprocess.PIPE
    ).stdout.strip()


def file_hash(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def publish_deb(source: Path):
    if not source.is_file() or source.suffix != ".deb":
        raise ValueError(f"Expected a .deb file: {source}")
    package = deb_field(source, "Package")
    version = deb_field(source, "Version")
    arch = deb_field(source, "Architecture")
    if package != PACKAGE:
        raise ValueError(f"Unexpected package {package!r} in {source.name}; expected {PACKAGE}")
    if arch not in (*ARCHES, "all"):
        raise ValueError(f"Unsupported architecture {arch!r}: {source.name}")
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]*", version):
        raise ValueError(f"Unsafe/invalid version {version!r}")
    POOL.mkdir(parents=True, exist_ok=True)
    dest = POOL / f"{PACKAGE}_{version}_{arch}.deb"
    if dest.exists():
        if file_hash(dest, "sha256") != file_hash(source, "sha256"):
            raise ValueError(f"Refusing to overwrite immutable package {dest.name}")
        print(f"Already present (identical): {dest.relative_to(ROOT)}")
    else:
        shutil.copyfile(source, dest)
        print(f"Added: {dest.relative_to(ROOT)}")


def make_indexes():
    if not any(POOL.glob("*.deb")):
        raise ValueError("No packages in pool; supply real .deb files first")
    for arch in ARCHES:
        binary = DIST / "main" / f"binary-{arch}"
        binary.mkdir(parents=True, exist_ok=True)
        data = run(
            ["dpkg-scanpackages", "--multiversion", "--arch", arch, "pool"],
            cwd=SITE,
            stdout=subprocess.PIPE,
        ).stdout
        (binary / "Packages").write_bytes(data)
        # Deterministic gzip output; no embedded filename or current timestamp.
        with (binary / "Packages.gz").open("wb") as f:
            with gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as gz:
                gz.write(data)
        print(f"Indexed {arch}: {len(data)} uncompressed bytes")

    meta = [
        "Origin: formaggio-software",
        "Label: formaggio-software rhtop",
        "Suite: stable",
        "Codename: stable",
        "Architectures: amd64 arm64",
        "Components: main",
        "Description: Signed APT packages for rhtop",
        f"Date: {format_datetime(datetime.now(UTC), usegmt=True)}",
    ]
    index_paths = sorted(
        p for p in DIST.rglob("*") if p.is_file() and p.name in ("Packages", "Packages.gz")
    )
    for label, algo in (("MD5Sum", "md5"), ("SHA256", "sha256")):
        meta.append(f"{label}:")
        for path in index_paths:
            relative = path.relative_to(DIST).as_posix()
            meta.append(f" {file_hash(path, algo)} {path.stat().st_size:16d} {relative}")
    (DIST / "Release").write_text("\n".join(meta) + "\n", encoding="utf-8")


def sign_indexes(key_id: str):
    # An empty/absent public key export means the requested key cannot be used.
    public_key = run(["gpg", "--batch", "--export", key_id], stdout=subprocess.PIPE).stdout
    if not public_key:
        raise ValueError(f"GPG public key not found for {key_id!r}")
    release = DIST / "Release"
    # CI may supply a protected key's passphrase through stdin, never argv.
    passphrase = os.environ.get("APT_GPG_PASSPHRASE")
    unlock = [] if passphrase is None else ["--pinentry-mode", "loopback", "--passphrase-fd", "0"]
    secret_input = {} if passphrase is None else {"input": (passphrase + "\n").encode()}
    run(
        [
            "gpg",
            "--batch",
            "--yes",
            *unlock,
            "--local-user",
            key_id,
            "--digest-algo",
            "SHA256",
            "--clearsign",
            "--output",
            str(DIST / "InRelease"),
            str(release),
        ],
        **secret_input,
    )
    run(
        [
            "gpg",
            "--batch",
            "--yes",
            *unlock,
            "--local-user",
            key_id,
            "--digest-algo",
            "SHA256",
            "--armor",
            "--detach-sign",
            "--output",
            str(DIST / "Release.gpg"),
            str(release),
        ],
        **secret_input,
    )
    KEY_OUTPUT.write_bytes(public_key)
    print(f"Signed indexes; exported PUBLIC key {KEY_OUTPUT.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debs", nargs="*", type=Path, help="Official release .deb files")
    args = parser.parse_args()
    key_id = os.environ.get("APT_GPG_KEY_ID", "").strip()
    if not key_id or key_id == "REPLACE_WITH_YOUR_SIGNING_KEY_FINGERPRINT":
        parser.error("set APT_GPG_KEY_ID to an existing private signing key ID/fingerprint")
    for executable in ("dpkg-deb", "dpkg-scanpackages", "gpg"):
        if not shutil.which(executable):
            parser.error(f"missing {executable}; install dpkg-dev, dpkg, and gnupg")
    try:
        for deb in args.debs:
            publish_deb(deb.resolve())
        make_indexes()
        sign_indexes(key_id)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print("Signed repository prepared in docs/. Review and publish through GitHub Pages.")


if __name__ == "__main__":
    main()
