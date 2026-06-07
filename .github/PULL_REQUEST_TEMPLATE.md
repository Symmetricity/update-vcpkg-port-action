## Summary

<!-- Describe what changed and why. -->

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation or example update
- [ ] CI, release, or security maintenance

## Validation

<!-- List the exact checks run, or explain why a check was not run. -->

- [ ] `actionlint .github/workflows/validate.yml .github/workflows/codeql.yml examples/generic/update-vcpkg-port.yml examples/upstream-maintainer/update-vcpkg-port-on-release.yml examples/user-maintained-release-watch/update-vcpkg-port.yml`
- [ ] `pipx run zizmor --pedantic .`
- [ ] `ruff check scripts tests`
- [ ] `ruff format --check scripts tests`
- [ ] `python3 -m py_compile scripts/update_vcpkg_port.py`
- [ ] `python3 -m unittest discover -s tests -v`

## Release and Documentation Impact

- [ ] README, examples, or changelog updated if user-facing behavior changed
- [ ] Inputs, outputs, or release tags considered for semver impact
- [ ] Marketplace metadata considered if `action.yml` changed

## Security Checklist

- [ ] No secrets, credentials, build artifacts, or generated `.env` files are committed
- [ ] Workflow changes avoid untrusted input interpolation in shell scripts
- [ ] Third-party actions in workflows or examples are pinned appropriately
