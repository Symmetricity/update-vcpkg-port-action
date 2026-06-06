# update-vcpkg-port-action

Reusable GitHub Action for the mechanical part of maintaining a vcpkg port:

1. Resolve an upstream tag and source archive.
2. Compute the archive SHA512.
3. Render a port template.
4. Run `vcpkg format-manifest`.
5. Run `vcpkg x-add-version`.
6. Optionally run `vcpkg install`.

The Action does not commit, push, or open pull requests. The caller workflow
owns that policy.

The Action also does not infer a complete vcpkg recipe from arbitrary source
code. New ports normally need package-specific templates for the build system,
dependencies, install fixups, usage text, and validation behavior.

## Usage

```yaml
- name: Update port
  id: update
  uses: Symmetricity/update-vcpkg-port-action@v1
  with:
    port: examplelib
    upstream-repository: owner/examplelib
    tag: v1.2.3
    vcpkg-root: vcpkg
    template-dir: project/.vcpkg-port-template
    dry-run: true
```

The workflow should check out the upstream project and a writable vcpkg fork
before invoking the Action. For a fork in a different repository, use a secret
token with write access to that vcpkg fork; the default `github.token` cannot
push to another repository.

```yaml
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
  with:
    path: project

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

See `examples/generic/update-vcpkg-port.yml` for a complete workflow.

For cross-repository pushes, configure:

- repository variable `VCPKG_FORK_REPOSITORY`, for example `OWNER/vcpkg`
- repository secret `VCPKG_PR_TOKEN`, preferably a fine-grained PAT limited to
  contents read/write on that vcpkg fork

## Templates

Template mode is the normal reusable path. Keep the port-specific CMake,
features, patches, dependencies, install fixups, and usage text in a template
directory owned by the project or maintenance workflow, then let the Action fill
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

If `template-dir` is omitted, the Action can update an existing
`ports/<port>/vcpkg.json` and `ports/<port>/portfile.cmake`. This compatibility
mode expects one `REF` line and one `SHA512` line in the portfile; use a
template for ports with patches, multiple sources, custom features, or
non-standard update logic.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `port` | required | vcpkg port name. |
| `vcpkg-root` | `vcpkg` | Checked-out vcpkg repository or registry. |
| `upstream-repository` | empty | GitHub repository in `OWNER/REPO` form. |
| `tag` | latest tag | Upstream tag to package. |
| `version` | derived from tag | Version written to `vcpkg.json`. |
| `version-strip-prefix` | `v` | Prefix stripped when deriving version from tag. |
| `archive-url` | GitHub tag tarball | Source archive URL. Supports `{repository}`, `{tag}`, `{version}`. |
| `head-ref` | `master` | Template value for `@HEAD_REF@`. |
| `template-dir` | empty | Template directory for creating or replacing the port. |
| `overwrite-version` | `true` | Pass `--overwrite-version` to `x-add-version`. |
| `bootstrap` | `true` | Bootstrap vcpkg if the executable is missing. |
| `run-install` | `true` | Run `vcpkg install` after updating. |
| `test-triplet` | `x64-linux` | Triplet used for validation install. |
| `install-args` | `--clean-after-build` | Extra install arguments. |
| `x-add-version-args` | empty | Extra `x-add-version` arguments. |
| `dry-run` | `false` | Update the checked-out vcpkg tree and print the generated diff. The Action itself never commits, pushes, or opens a PR; caller workflows should gate those steps on this input. |

## Outputs

- `tag`
- `version`
- `sha512`
- `port-path`
- `port-relative-path`
- `version-path`
- `version-relative-path`
- `changed`

## Publishing workflow

After this Action runs, the caller can commit and push if `changed` is true:

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

Put any package-specific consumer smoke test between the update step and the
commit step. `vcpkg install` validates that the port builds and installs; a
small downstream compile test catches usage issues such as the required C++
standard, include paths, and link instructions.

Opening a pull request to `microsoft/vcpkg` should remain explicit in the
caller workflow because tokens, review gates, draft mode, and branch naming are
project policy decisions.
