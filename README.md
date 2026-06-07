# Update vcpkg port v1

[![Validate](https://github.com/Symmetricity/update-vcpkg-port-action/actions/workflows/validate.yml/badge.svg)](https://github.com/Symmetricity/update-vcpkg-port-action/actions/workflows/validate.yml)
[![CodeQL](https://github.com/Symmetricity/update-vcpkg-port-action/actions/workflows/codeql.yml/badge.svg)](https://github.com/Symmetricity/update-vcpkg-port-action/actions/workflows/codeql.yml)

This action handles the mechanical release-update work for a vcpkg port:

- Resolve an upstream tag and source archive.
- Compute the source archive SHA512.
- Render a package-specific port template.
- Optionally generate a simple CMake package config and usage file.
- Run `vcpkg format-manifest`.
- Run `vcpkg x-add-version`.
- Optionally run `vcpkg install` and a CMake consumer smoke test for validation.

The action does not infer a complete vcpkg recipe from arbitrary source code.
New ports normally need package-specific templates for the build system,
dependencies, install fixups, usage text, and validation behavior.

The action does not commit, push, open issues, or open pull requests. Caller
workflows own those policy decisions.

## What's New

### v1

- Adds template-based vcpkg port creation and update support.
- Supports latest-tag lookup, explicit tags, custom archive URLs, and
  tag-derived versions.
- Can generate simple CMake package configs for single-target ports.
- Can build a generated downstream CMake consumer after `vcpkg install`.
- Refreshes the vcpkg versions database with `vcpkg x-add-version`.
- Provides manual, upstream-maintainer, and user-maintained workflow examples.

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Usage

See [action.yml](action.yml).

<!-- start usage -->
```yaml
- name: Update vcpkg port
  id: update
  uses: Symmetricity/update-vcpkg-port-action@v1
  with:
    port: examplelib
    upstream-repository: owner/examplelib
    tag: v1.2.3
    vcpkg-root: vcpkg
    template-dir: project/.vcpkg-port-template
```
<!-- end usage -->

The workflow should check out the upstream project and a writable vcpkg fork
before invoking the action:

```yaml
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
  with:
    path: project
    persist-credentials: false

- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
  with:
    fetch-depth: 0
    path: vcpkg
    repository: ${{ vars.VCPKG_FORK_REPOSITORY }}
    token: ${{ secrets.VCPKG_PR_TOKEN }}

- run: |
    git -C vcpkg remote add upstream https://github.com/microsoft/vcpkg.git || true
    git -C vcpkg fetch upstream master
    git -C vcpkg switch -C "update/examplelib-v1.2.3-${GITHUB_RUN_ID}" upstream/master
```

For a fork in a different repository, use a secret token with write access to
that vcpkg fork. The default `github.token` cannot push to another repository.

For simple single-target CMake packages, add the optional CMake config and
consumer-test inputs:

```yaml
with:
  cmake-config: true
  cmake-package-name: examplelib
  cmake-target-name: examplelib::examplelib
  cmake-header-names: examplelib.h
  cmake-library-names: examplelib
  consumer-test: true
  consumer-test-language: CXX
```

## Prerequisites

- A checked-out vcpkg repository or registry.
- A package-specific template directory for new ports.
- Python on the runner. GitHub-hosted runners include it by default.
- Network access to download the source archive and any vcpkg dependencies.

For cross-repository pushes, configure:

- Repository variable `VCPKG_FORK_REPOSITORY`, for example `OWNER/vcpkg`.
- Repository secret `VCPKG_PR_TOKEN`, preferably a fine-grained PAT limited to
  contents read/write on that vcpkg fork.

## Workflow Examples

- [examples/generic/update-vcpkg-port.yml](examples/generic/update-vcpkg-port.yml):
  manual starter workflow for a package-specific template.
- [examples/upstream-maintainer/update-vcpkg-port-on-release.yml](examples/upstream-maintainer/update-vcpkg-port-on-release.yml):
  advanced workflow for package maintainers. It runs on `release.published`,
  packages that release tag, skips if a draft branch for the tag already exists,
  pushes a branch to the configured vcpkg fork, and opens or updates a tracking
  issue in the package repository.
- [examples/user-maintained-release-watch/update-vcpkg-port.yml](examples/user-maintained-release-watch/update-vcpkg-port.yml):
  advanced workflow for user-maintained ports. It runs on a schedule or
  manually, detects the latest upstream release or tag, skips tags that already
  have a draft branch in the vcpkg fork, pushes a new branch, and opens or
  updates a tracking issue in the configured notification repository.

Use the scheduled user-maintained example only where automated notification is
appropriate. By default it notifies the repository that owns the workflow; if
you set `NOTIFY_REPOSITORY` to an upstream project, use a suitable token and
make sure the upstream maintainers expect those issues.

## Templates

Template mode is the normal reusable path. Keep the port-specific CMake,
features, patches, dependencies, install fixups, and usage text in a template
directory owned by the project or maintenance workflow, then let the action fill
in release-specific values.

Provide `template-dir`. Text files are rendered with these placeholders:

- `@PORT@`
- `@VERSION@`
- `@TAG@`
- `@UPSTREAM_REPOSITORY@`
- `@SOURCE_SHA512@`
- `@ARCHIVE_URL@`
- `@HEAD_REF@`

Files ending in `.in` have that suffix removed, so `portfile.cmake.in` renders
to `portfile.cmake`.

Example:

```text
.vcpkg-port-template/
  portfile.cmake.in
  vcpkg.json.in
  usage
```

The template in `examples/generic/.vcpkg-port-template` is a starting point for
a simple CMake package. Real ports should adjust the CMake options,
dependencies, usage text, license metadata, and install fixups for the package.
Header-only libraries, non-CMake projects, moved upstream archives, and packages
with required transitive dependencies usually need different templates.

### Generated CMake Config

For simple ports that install one library or one header-only target but do not
install an upstream CMake package config, set `cmake-config: true`.

```yaml
with:
  port: examplelib
  cmake-config: true
  cmake-package-name: examplelib
  cmake-target-name: examplelib::examplelib
  cmake-header-names: examplelib.h
  cmake-library-names: examplelib
```

This generates `<package>Config.cmake`, installs it from the portfile, and
writes usage text like:

```cmake
find_package(examplelib CONFIG REQUIRED)
target_link_libraries(main PRIVATE examplelib::examplelib)
```

Use this only for straightforward targets. Packages with multiple libraries,
component selection, transitive `find_dependency()` calls, unusual debug/release
names, or an upstream CMake config should keep that logic in the template.

### Consumer Smoke Test

Set `consumer-test: true` to build a tiny downstream CMake project after
`vcpkg install`. The generated project calls `find_package(... CONFIG
REQUIRED)`, includes the configured headers, links the configured target, and
builds through the checked-out vcpkg toolchain.

```yaml
with:
  run-install: true
  consumer-test: true
  consumer-test-language: CXX
  cmake-package-name: examplelib
  cmake-target-name: examplelib::examplelib
  cmake-header-names: examplelib.h
```

This is generic enough to catch broken package config, include path, and target
linkage for simple CMake consumers. It is not a replacement for package-specific
runtime tests, component tests, or feature matrix tests.

If `template-dir` is omitted, the action can update an existing
`ports/<port>/vcpkg.json` and `ports/<port>/portfile.cmake`. This compatibility
mode expects one `REF` line and one `SHA512` line in the portfile; use a
template for ports with patches, multiple sources, custom features, or
non-standard update logic.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `port` | Yes | | vcpkg port name to create or update. |
| `vcpkg-root` | No | `vcpkg` | Checked-out vcpkg repository or registry. |
| `upstream-repository` | No | | GitHub repository in `OWNER/REPO` form. Required when `tag` or `archive-url` is omitted. |
| `tag` | No | Latest tag | Upstream tag to package. |
| `version` | No | Derived from `tag` | Version written to `vcpkg.json`. |
| `version-strip-prefix` | No | `v` | Prefix stripped when deriving `version` from `tag`. |
| `archive-url` | No | GitHub tag tarball | Source archive URL. Supports `{repository}`, `{tag}`, and `{version}`. |
| `head-ref` | No | `master` | Template value for `@HEAD_REF@`. |
| `template-dir` | No | | Template directory for creating or replacing the port. |
| `cmake-config` | No | `false` | Generate a simple CMake package config, imported target, and usage file for the port. |
| `cmake-package-name` | No | `port` | Package name used with `find_package(... CONFIG REQUIRED)`. |
| `cmake-target-name` | No | `<package>::<package>` | Imported target defined by the generated CMake config. |
| `cmake-header-names` | No | | Header names passed to `find_path`, separated by spaces, commas, or semicolons. |
| `cmake-library-names` | No | | Library names passed to `find_library`, separated by spaces, commas, or semicolons. |
| `consumer-test` | No | `false` | Build a tiny CMake consumer project after `vcpkg install` using the configured package, target, and headers. |
| `consumer-test-language` | No | `CXX` | Language for the generated consumer source. Use `C` or `CXX`. |
| `overwrite-version` | No | `true` | Pass `--overwrite-version` to `vcpkg x-add-version`. |
| `bootstrap` | No | `true` | Bootstrap vcpkg if the executable is missing. |
| `run-install` | No | `true` | Run `vcpkg install` after updating. |
| `test-triplet` | No | `x64-linux` | Triplet used when `run-install` is true. |
| `install-args` | No | `--clean-after-build` | Extra arguments passed to `vcpkg install`. |
| `x-add-version-args` | No | | Extra arguments passed to `vcpkg x-add-version`. |
| `dry-run` | No | `false` | Update the checked-out vcpkg tree and print the generated diff. The action itself never commits, pushes, or opens a PR; caller workflows should gate those steps on this input. |

## Outputs

| Output | Description |
| --- | --- |
| `tag` | Resolved upstream tag. |
| `version` | Resolved package version. |
| `sha512` | SHA512 of the resolved source archive. |
| `port-path` | Path to the updated port directory. |
| `port-relative-path` | Port directory path relative to `vcpkg-root`. |
| `version-path` | Expected vcpkg versions file path for the port. |
| `version-relative-path` | Expected vcpkg versions file path relative to `vcpkg-root`. |
| `changed` | Whether the vcpkg checkout has changes for this port or versions database. |

## Scenarios

### Commit and push a draft branch

After this action runs, the caller can commit and push if `changed` is true:

```yaml
- name: Commit and push branch
  if: ${{ steps.update.outputs.changed == 'true' && !inputs.dry_run }}
  env:
    PORT: examplelib
    TAG: ${{ steps.update.outputs.tag }}
    VERSION: ${{ steps.update.outputs.version }}
    PORT_PATH: ${{ steps.update.outputs.port-relative-path }}
    VERSION_PATH: ${{ steps.update.outputs.version-relative-path }}
  run: |
    git -C vcpkg add "${PORT_PATH}" versions/baseline.json "${VERSION_PATH}"
    git -C vcpkg commit -m "[${PORT}] Update to ${VERSION}"
    git -C vcpkg push origin "HEAD:update/${PORT}-${TAG}-${GITHUB_RUN_ID}"
```

### Add Consumer Validation

For simple CMake consumers, set `consumer-test: true` on the action. The action
will build a generated downstream project after `vcpkg install`.

For package-specific runtime checks, feature checks, or multi-component
consumers, put a custom smoke test between the update step and the commit step.
`vcpkg install` validates that the port builds and installs; downstream tests
catch usage issues such as the required C++ standard, include paths, and link
instructions.

### Open a pull request

Opening a pull request to `microsoft/vcpkg` should remain explicit in the
caller workflow because tokens, review gates, draft mode, and branch naming are
project policy decisions.

## Recommended Permissions

The action itself only needs to read files from the caller workspace and write
inside the checked-out vcpkg tree. The caller workflow should grant the minimum
`GITHUB_TOKEN` permissions it needs for its surrounding steps.

For the examples in this repository:

- Use `contents: read` for the workflow repository.
- Use `issues: write` only for workflows that create or update notification
  issues.
- Use `VCPKG_PR_TOKEN` for cross-repository writes to the vcpkg fork.

## Security Notes

- Prefer a fine-grained `VCPKG_PR_TOKEN` limited to the vcpkg fork contents
  permission required by the workflow.
- Do not give notification tokens access to upstream repositories unless
  upstream maintainers expect automated issues.
- Keep package-specific templates under review. The action renders templates
  and executes vcpkg commands; it does not determine whether a port recipe is
  semantically correct for the package.

## Release Management

This action follows the same release model recommended for GitHub Actions:

- Immutable semantic version release tags such as `v1.1.0`.
- A moving major version tag such as `v1` for the latest backward-compatible
  release.
- New major tags such as `v2` for breaking input, output, or behavior changes.

Use `Symmetricity/update-vcpkg-port-action@v1` for the latest stable v1 release.
Pin to `@v1.1.0` or a full commit SHA when you need stricter reproducibility.

## License

This project is licensed under the terms of the [MIT License](LICENSE).
