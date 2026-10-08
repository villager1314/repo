# Contributing

[README](README.md) · [Maintenance](docs/MAINTAINING.md)

Use the issue templates for bugs and feature requests. Include the client version, environment and a minimal reproduction. Check existing issues before opening a new one.

For changes, fork the repository and create a branch. Keep each pull request focused; describe the resulting behavior and validation. Add meaningful tests for behavior changes, especially trust checks, cache handling and device operations. Documentation-only changes need link and example checks rather than implementation-mirroring tests.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_repositories.py
```

Do not commit signing keys, tokens, pairing codes, real personal APKs or device identifiers. Tests must not mutate connected devices. Mocked success is not physical-device validation. Keep English README and Chinese README behavior descriptions aligned. CLI runtime localization remains partial; describe the scope of translation changes.

Package outputs in `site/` are maintainer-signed artifacts. Source contributions should explain when a new package version is needed; contributors do not need the repository's private key. Releases must preserve existing trust and signature checks.
