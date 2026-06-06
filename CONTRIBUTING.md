# Contributing

Keep changes small and focused. This repository contains a reusable GitHub
Action, so documentation, examples, and workflow security are part of the
public API.

## Development

Run the same checks used by CI before opening a pull request:

```bash
actionlint .github/workflows/validate.yml .github/workflows/codeql.yml examples/generic/update-vcpkg-port.yml examples/upstream-maintainer/update-vcpkg-port-on-release.yml examples/user-maintained-release-watch/update-vcpkg-port.yml
pipx run zizmor --pedantic .
ruff check scripts tests
ruff format --check scripts tests
python3 -m py_compile scripts/update_vcpkg_port.py
python3 -m unittest discover -s tests -v
```

For workflow examples with inline shell, run `shellcheck` on the extracted
scripts before claiming they work.

## Release Policy

This action uses semantic version release tags such as `v1.0.0` and a moving
major tag such as `v1` for the latest backward-compatible v1 release.

Breaking changes to inputs, outputs, or core behavior require a new major tag.
