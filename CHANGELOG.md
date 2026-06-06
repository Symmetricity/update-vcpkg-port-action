# Changelog

## v1.0.0

Initial stable release of `update-vcpkg-port-action`.

### Added

- Composite GitHub Action for rendering or updating vcpkg ports from upstream
  releases.
- SHA512 computation for source archives.
- Template rendering for package-specific vcpkg port recipes.
- vcpkg manifest formatting and versions database refresh support.
- Optional `vcpkg install` validation.
- Manual, upstream-maintainer, and user-maintained workflow examples.
- CI coverage with actionlint, zizmor, ruff, Python compilation, unit tests,
  self-use action validation, and CodeQL.

### Release Notes

This release is intended to be consumed as:

```yaml
- uses: Symmetricity/update-vcpkg-port-action@v1
```

For stricter reproducibility, pin to `@v1.0.0` or a full commit SHA.
