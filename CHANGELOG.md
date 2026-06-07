# Changelog

## Unreleased

### Changed

- Generated CMake configs now default to vcpkg's `unofficial-<port>` package
  name and `unofficial::<port>::<port>` target namespace. Explicit
  `cmake-package-name` and `cmake-target-name` inputs still override these
  defaults.

### Fixed

- Generated CMake config install blocks no longer install `usage` a second time
  when the port template already installs it.

## v1.1.0 - 2026-06-07

### Added

- Optional generated CMake package config support for simple single-target
  ports. When enabled, the action writes a package config, usage file, and
  portfile install block so consumers can use `find_package(... CONFIG
  REQUIRED)` with an imported target.
- Optional CMake consumer smoke test support. When enabled, the action builds a
  tiny downstream project through the vcpkg toolchain to verify package config,
  header include paths, and target linkage.

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
