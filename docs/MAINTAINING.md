# Maintenance and releases

[README](../README.md)

Build dependencies: Python 3, dpkg-dev, zstd and GnuPG. PGPy is an optional build-only alternative when gpg-agent is unavailable; clients use gpgv.

```sh
python3 scripts/build.py --key FINGERPRINT
python3 scripts/build_termux.py --key FINGERPRINT
python3 -m unittest discover -s tests -v
python3 scripts/check_repositories.py
```

Alternatively pass `--private-key /private/path/repository-private.asc` with PGPy installed. Never commit that key. The workflows publish already-signed artifacts and do not rebuild with private keys.

For a client release, update the runtime and both build-script versions, version-specific repository checks, README version badge, manuals and CHANGELOG. Build all five repositories and verify their signatures. Check Termux separately, since its paths and dependencies differ from Debian even though both packages use Architecture: all. Synchronize public document copies under `site/` and keep their links valid.

The release workflow reads the runtime version and publishes a GitHub Release only if its tag is absent. It attaches Debian, Arch and Termux packages with unambiguous names, the Arch detached signature, the public repository key and SHA256SUMS. SHA256SUMS helps compare downloads; it does not independently authenticate the publisher. Repository clients verify signed indexes; Arch clients also verify package signatures.

Release workflow dispatch republishes only missing releases; it never overwrites existing assets. Historical versions remain documented in CHANGELOG; do not invent historical tags or attach current binaries to them. Review Actions and the online repository indexes after publication.
