# Formaggio Software APT repository

Signed [rhtop](https://github.com/formaggio-software/rhtop) binary packages for
Debian 12 Bookworm or newer, amd64 and arm64.
Product, subscription, and licensing information: [rhtop.dev](https://rhtop.dev).

## Install

Obtain the public signing-key fingerprint from a trusted Formaggio Software
release announcement. Download the key and confirm that fingerprint:

```sh
curl -fsSLo formaggio-software-archive-keyring.pgp \
  https://formaggio-software.github.io/apt-repo/formaggio-software-archive-keyring.pgp
gpg --show-keys --with-fingerprint formaggio-software-archive-keyring.pgp
# Confirm the fingerprint before installing the key.
sudo install -d -m 0755 /etc/apt/keyrings
sudo install -m 0644 formaggio-software-archive-keyring.pgp /etc/apt/keyrings/
printf '%s\n' \
  'Types: deb' \
  'URIs: https://formaggio-software.github.io/apt-repo/' \
  'Suites: stable' \
  'Components: main' \
  'Architectures: amd64 arm64' \
  'Signed-By: /etc/apt/keyrings/formaggio-software-archive-keyring.pgp' \
  | sudo tee /etc/apt/sources.list.d/formaggio-software.sources >/dev/null
sudo apt-get update
sudo apt-get install rhtop
rhtop --demo
```

Upgrade with `sudo apt-get update` then
`sudo apt-get install --only-upgrade rhtop`. Remove with `sudo apt-get remove rhtop`;
user credentials/preferences are retained. No global trust override is required.

## Publish

Prerequisites: Python 3.11+, dpkg, dpkg-dev, gnupg, and an existing signing-capable
secret key in the local GnuPG keyring. Keep secret keys outside this repo.
For automated signing with a passphrase-protected key, supply
`APT_GPG_PASSPHRASE` through the job's protected secret environment; it is passed
to GnuPG through stdin, not command arguments.

```sh
python3 -m venv .venv
APT_GPG_KEY_ID=YOUR_FULL_SIGNING_KEY_FINGERPRINT \
  .venv/bin/python scripts/publish_debs.py \
  /path/to/rhtop_0.1.0_amd64.deb /path/to/rhtop_0.1.0_arm64.deb
gpg --verify docs/dists/stable/InRelease
gpg --verify docs/dists/stable/Release.gpg docs/dists/stable/Release
```

The publisher retains versions, rejects changed replacement packages, writes
both architecture indexes and signed Release metadata, and exports only the
public key. Enable GitHub Pages: Settings → Pages → deploy from the default
branch's `/docs` directory. Publish `docs/`, announce the public-key fingerprint,
and verify an actual APT update/install on both architectures before release.

Only binaries, indexes, signatures, public keys, and documentation belong here.

For support, email [contact@formaggio.software](mailto:contact@formaggio.software).

## Binary-use license

Installation does not grant unpaid use or redistribution rights. Review the
[complete binary-use license](https://rhtop.dev/terms/) before use.
The Debian package includes `/usr/share/doc/rhtop/LICENSE.txt` and third-party notices.
