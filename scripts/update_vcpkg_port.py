#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(shlex.quote(part) for part in command))
    return subprocess.run(command, cwd=cwd, check=True, text=True)


def capture(command: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def latest_github_tag(repository: str) -> str:
    request = urllib.request.Request(f"https://api.github.com/repos/{repository}/tags")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")

    with urllib.request.urlopen(request) as response:
        tags = json.loads(response.read().decode("utf-8"))

    if not tags:
        fail(f"{repository} has no tags")
    return tags[0]["name"]


def read_url(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url) as response:
            return response.read()
    except urllib.error.URLError as error:
        fail(f"failed to download {url}: {error}")


def is_probably_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def render_text(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(f"@{key}@", value)
    return text


def render_name(name: str, values: dict[str, str]) -> str:
    rendered = render_text(name, values)
    if rendered.endswith(".in"):
        rendered = rendered[:-3]
    return rendered


def render_template_tree(template_dir: Path, port_dir: Path, values: dict[str, str]) -> None:
    if not template_dir.is_dir():
        fail(f"template directory does not exist: {template_dir}")

    if port_dir.exists():
        shutil.rmtree(port_dir)
    port_dir.mkdir(parents=True)

    for source in sorted(template_dir.rglob("*")):
        relative = source.relative_to(template_dir)
        target_parts = [render_name(part, values) for part in relative.parts]
        target = port_dir.joinpath(*target_parts)

        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        data = source.read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_probably_text(data):
            rendered = render_text(data.decode("utf-8"), values)
            target.write_text(rendered, encoding="utf-8")
        else:
            target.write_bytes(data)


def update_manifest(path: Path, version: str) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    version_keys = ["version", "version-semver", "version-date", "version-string"]

    present = [key for key in version_keys if key in manifest]
    if not present:
        manifest["version"] = version
    else:
        for key in present:
            manifest[key] = version

    manifest.pop("port-version", None)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def update_portfile(path: Path, tag: str, sha512: str) -> None:
    text = path.read_text(encoding="utf-8")

    text, ref_count = re.subn(
        r"(^\s*REF\s+)(\"[^\"]+\"|[^\s)]+)",
        rf'\g<1>"{tag}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text, sha_count = re.subn(
        r"(^\s*SHA512\s+)[A-Fa-f0-9]+",
        rf"\g<1>{sha512}",
        text,
        count=1,
        flags=re.MULTILINE,
    )

    if ref_count != 1:
        fail(f"could not find a single REF line in {path}; provide a template-dir")
    if sha_count != 1:
        fail(f"could not find a single SHA512 line in {path}; provide a template-dir")

    path.write_text(text, encoding="utf-8")


def update_existing_port(port_dir: Path, tag: str, version: str, sha512: str) -> None:
    manifest = port_dir / "vcpkg.json"
    portfile = port_dir / "portfile.cmake"
    if not manifest.is_file() or not portfile.is_file():
        fail(f"{port_dir} is missing vcpkg.json or portfile.cmake; provide a template-dir")

    update_manifest(manifest, version)
    update_portfile(portfile, tag, sha512)


def split_input_list(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\s,;]+", value) if part.strip()]


def validate_cmake_package_name(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", value):
        fail(f"invalid CMake package name: {value}")


def validate_cmake_target_name(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.+:-]+", value):
        fail(f"invalid CMake target name: {value}")


def validate_cmake_names(label: str, values: list[str], pattern: str) -> None:
    for value in values:
        if not re.fullmatch(pattern, value):
            fail(f"invalid {label}: {value}")


def default_cmake_package_name(port: str) -> str:
    return f"unofficial-{port}"


def default_cmake_target_name(port: str) -> str:
    return f"unofficial::{port}::{port}"


def cmake_variable_stem(package_name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_]", "_", package_name).upper()
    if stem[0].isdigit():
        stem = "_" + stem
    return stem


def cmake_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def cmake_names_block(values: list[str], indent: str = "        ") -> str:
    return "\n".join(f"{indent}{cmake_quote(value)}" for value in values)


def generated_cmake_config(
    package_name: str,
    target_name: str,
    header_names: list[str],
    library_names: list[str],
) -> str:
    stem = cmake_variable_stem(package_name)
    prefix_var = f"_{stem}_PREFIX"
    include_var = f"{stem}_INCLUDE_DIR"
    release_var = f"{stem}_LIBRARY_RELEASE"
    debug_var = f"{stem}_LIBRARY_DEBUG"
    target_type = "UNKNOWN" if library_names else "INTERFACE"
    lines = [
        f'get_filename_component({prefix_var} "${{CMAKE_CURRENT_LIST_DIR}}/../.." ABSOLUTE)',
        "",
    ]

    if header_names:
        lines.extend(
            [
                f"find_path({include_var}",
                "    NAMES",
                cmake_names_block(header_names),
                f'    PATHS "${{{prefix_var}}}/include"',
                "    NO_DEFAULT_PATH",
                ")",
                f"if(NOT {include_var})",
                f'    message(FATAL_ERROR "{package_name} headers not found")',
                "endif()",
                "",
            ]
        )

    if library_names:
        lines.extend(
            [
                f"find_library({release_var}",
                "    NAMES",
                cmake_names_block(library_names),
                f'    PATHS "${{{prefix_var}}}/lib"',
                "    NO_DEFAULT_PATH",
                ")",
                f"find_library({debug_var}",
                "    NAMES",
                cmake_names_block(library_names),
                f'    PATHS "${{{prefix_var}}}/debug/lib"',
                "    NO_DEFAULT_PATH",
                ")",
                f"if(NOT {release_var} AND NOT {debug_var})",
                f'    message(FATAL_ERROR "{package_name} library not found")',
                "endif()",
                "",
            ]
        )

    lines.extend(
        [
            f"if(NOT TARGET {target_name})",
            f"    add_library({target_name} {target_type} IMPORTED)",
        ]
    )

    if header_names:
        lines.extend(
            [
                f"    set_target_properties({target_name} PROPERTIES",
                f'        INTERFACE_INCLUDE_DIRECTORIES "${{{include_var}}}"',
                "    )",
            ]
        )

    if library_names:
        lines.extend(
            [
                f"    if({release_var})",
                f"        set_property(TARGET {target_name} APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)",
                f"        set_target_properties({target_name} PROPERTIES",
                f'            IMPORTED_LOCATION "${{{release_var}}}"',
                f'            IMPORTED_LOCATION_RELEASE "${{{release_var}}}"',
                "            MAP_IMPORTED_CONFIG_MINSIZEREL RELEASE",
                "            MAP_IMPORTED_CONFIG_RELWITHDEBINFO RELEASE",
                "        )",
                "    endif()",
                f"    if({debug_var})",
                f"        set_property(TARGET {target_name} APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG)",
                f"        set_target_properties({target_name} PROPERTIES",
                f'            IMPORTED_LOCATION_DEBUG "${{{debug_var}}}"',
                "        )",
                "    endif()",
                f"    if(NOT {release_var} AND {debug_var})",
                f'        set_target_properties({target_name} PROPERTIES IMPORTED_LOCATION "${{{debug_var}}}")',
                "    endif()",
            ]
        )

    lines.extend(["endif()", ""])
    return "\n".join(lines)


def write_generated_cmake_config(
    port_dir: Path,
    package_name: str,
    target_name: str,
    header_names: list[str],
    library_names: list[str],
) -> None:
    if not header_names and not library_names:
        fail("--cmake-header-names or --cmake-library-names is required when --cmake-config is true")

    validate_cmake_package_name(package_name)
    validate_cmake_target_name(target_name)
    validate_cmake_names("CMake header name", header_names, r"[A-Za-z0-9_./+-]+")
    validate_cmake_names("CMake library name", library_names, r"[A-Za-z0-9_.+-]+")

    config_filename = f"{package_name}Config.cmake"
    (port_dir / config_filename).write_text(
        generated_cmake_config(package_name, target_name, header_names, library_names),
        encoding="utf-8",
    )
    (port_dir / "usage").write_text(
        "The package provides CMake targets:\n\n"
        f"  find_package({package_name} CONFIG REQUIRED)\n"
        f"  target_link_libraries(main PRIVATE {target_name})\n",
        encoding="utf-8",
    )
    ensure_portfile_installs_generated_cmake_files(port_dir / "portfile.cmake", package_name, config_filename)


def ensure_portfile_installs_generated_cmake_files(portfile: Path, package_name: str, config_filename: str) -> None:
    if not portfile.is_file():
        fail(f"{portfile} does not exist; cannot install generated CMake config")

    start = "# Generated CMake package config install begin"
    end = "# Generated CMake package config install end"
    text = portfile.read_text(encoding="utf-8")
    pattern = rf"\n?{re.escape(start)}.*?{re.escape(end)}\n?"
    text = re.sub(pattern, "\n", text, flags=re.DOTALL).rstrip()
    usage_install = ""
    if "${CMAKE_CURRENT_LIST_DIR}/usage" not in text:
        usage_install = (
            "file(INSTALL\n"
            '    "${CMAKE_CURRENT_LIST_DIR}/usage"\n'
            '    DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"\n'
            ")\n"
        )
    block = (
        f"{start}\n"
        "file(INSTALL\n"
        f'    "${{CMAKE_CURRENT_LIST_DIR}}/{config_filename}"\n'
        f'    DESTINATION "${{CURRENT_PACKAGES_DIR}}/share/{package_name}"\n'
        ")\n" + usage_install + f"{end}\n"
    )
    text = text + "\n\n" + block
    portfile.write_text(text, encoding="utf-8")


def consumer_test_source(header_names: list[str], language: str) -> str:
    includes = "".join(f"#include <{header}>\n" for header in header_names)
    if language == "CXX":
        return includes + "int main() { return 0; }\n"
    return includes + "int main(void) { return 0; }\n"


def consumer_test_cmake(package_name: str, target_name: str, language: str, source_name: str) -> str:
    return (
        "cmake_minimum_required(VERSION 3.20)\n"
        f"project(vcpkg_consumer_smoke LANGUAGES {language})\n"
        f"find_package({package_name} CONFIG REQUIRED)\n"
        f"add_executable(consumer {source_name})\n"
        f"target_link_libraries(consumer PRIVATE {target_name})\n"
    )


def run_consumer_test(
    vcpkg_root: Path,
    package_name: str,
    target_name: str,
    header_names: list[str],
    language: str,
    triplet: str,
) -> None:
    language = language.strip().upper()
    if language not in {"C", "CXX"}:
        fail("--consumer-test-language must be C or CXX")

    validate_cmake_package_name(package_name)
    validate_cmake_target_name(target_name)
    validate_cmake_names("CMake header name", header_names, r"[A-Za-z0-9_./+-]+")

    cmake = shutil.which("cmake")
    if not cmake:
        fail("cmake is required when --consumer-test is true")

    toolchain = vcpkg_root / "scripts" / "buildsystems" / "vcpkg.cmake"
    if not toolchain.is_file():
        fail(f"vcpkg CMake toolchain file does not exist at {toolchain}")

    source_name = "main.cpp" if language == "CXX" else "main.c"
    with tempfile.TemporaryDirectory(prefix="update-vcpkg-port-consumer-") as tmp:
        tmp_path = Path(tmp)
        source_dir = tmp_path / "src"
        build_dir = tmp_path / "build"
        source_dir.mkdir()
        (source_dir / "CMakeLists.txt").write_text(
            consumer_test_cmake(package_name, target_name, language, source_name),
            encoding="utf-8",
        )
        (source_dir / source_name).write_text(
            consumer_test_source(header_names, language),
            encoding="utf-8",
        )

        run(
            [
                cmake,
                "-S",
                str(source_dir),
                "-B",
                str(build_dir),
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
                f"-DVCPKG_TARGET_TRIPLET={triplet}",
            ]
        )
        run([cmake, "--build", str(build_dir)])


def bootstrap_vcpkg(vcpkg_root: Path) -> None:
    shell_script = vcpkg_root / "bootstrap-vcpkg.sh"
    batch_script = vcpkg_root / "bootstrap-vcpkg.bat"
    if shell_script.is_file():
        run([str(shell_script), "-disableMetrics"], cwd=vcpkg_root)
    elif batch_script.is_file():
        run([str(batch_script), "-disableMetrics"], cwd=vcpkg_root)
    else:
        fail(f"could not find bootstrap script in {vcpkg_root}")


def vcpkg_executable(vcpkg_root: Path) -> Path:
    exe = vcpkg_root / ("vcpkg.exe" if os.name == "nt" else "vcpkg")
    if exe.exists():
        return exe

    fallback = vcpkg_root / "vcpkg"
    if fallback.exists():
        return fallback
    return exe


def write_outputs(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    with open(output_path, "a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def print_diff(vcpkg_root: Path, port: str, version_path: str) -> None:
    paths = [f"ports/{port}", "versions/baseline.json", version_path]
    run(["git", "status", "--short", "--", *paths], cwd=vcpkg_root)
    run(["git", "--no-pager", "diff", "--stat", "--", *paths], cwd=vcpkg_root)
    run(["git", "--no-pager", "diff", "--", *paths], cwd=vcpkg_root)

    untracked = capture(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *paths],
        cwd=vcpkg_root,
    )
    for line in untracked.splitlines():
        print()
        subprocess.run(
            ["git", "--no-pager", "diff", "--no-index", "--", "/dev/null", line],
            cwd=vcpkg_root,
            check=False,
            text=True,
        )


def changed(vcpkg_root: Path, port: str, version_path: str) -> bool:
    paths = [f"ports/{port}", "versions/baseline.json", version_path]
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", *paths],
            cwd=vcpkg_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError:
        return True
    if result.returncode != 0:
        return True
    return bool(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--vcpkg-root", required=True)
    parser.add_argument("--upstream-repository", default="")
    parser.add_argument("--tag", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--version-strip-prefix", default="v")
    parser.add_argument("--archive-url", default="")
    parser.add_argument("--head-ref", default="master")
    parser.add_argument("--template-dir", default="")
    parser.add_argument("--cmake-config", default="false")
    parser.add_argument("--cmake-package-name", default="")
    parser.add_argument("--cmake-target-name", default="")
    parser.add_argument("--cmake-header-names", default="")
    parser.add_argument("--cmake-library-names", default="")
    parser.add_argument("--consumer-test", default="false")
    parser.add_argument("--consumer-test-language", default="CXX")
    parser.add_argument("--overwrite-version", default="true")
    parser.add_argument("--bootstrap", default="true")
    parser.add_argument("--run-install", default="true")
    parser.add_argument("--test-triplet", default="x64-linux")
    parser.add_argument("--install-args", default="--clean-after-build")
    parser.add_argument("--x-add-version-args", default="")
    parser.add_argument("--dry-run", default="false")
    parser.add_argument("--skip-x-add-version", action="store_true")
    args = parser.parse_args()

    vcpkg_root = Path(args.vcpkg_root).resolve()
    if not (vcpkg_root / "ports").is_dir():
        fail(f"{vcpkg_root} does not look like a vcpkg checkout or registry")

    tag = args.tag.strip()
    if not tag:
        if not args.upstream_repository:
            fail("--upstream-repository is required when --tag is omitted")
        tag = latest_github_tag(args.upstream_repository)

    version = args.version.strip()
    if not version:
        version = tag
        if args.version_strip_prefix and version.startswith(args.version_strip_prefix):
            version = version[len(args.version_strip_prefix) :]

    archive_url = args.archive_url.strip()
    if not archive_url:
        if not args.upstream_repository:
            fail("--upstream-repository is required when --archive-url is omitted")
        archive_url = "https://github.com/{repository}/archive/refs/tags/{tag}.tar.gz"
    archive_url = archive_url.format(repository=args.upstream_repository, tag=tag, version=version)

    archive = read_url(archive_url)
    sha512 = hashlib.sha512(archive).hexdigest()

    port_dir = vcpkg_root / "ports" / args.port
    port_path = f"ports/{args.port}"
    values = {
        "PORT": args.port,
        "VERSION": version,
        "TAG": tag,
        "UPSTREAM_REPOSITORY": args.upstream_repository,
        "SOURCE_SHA512": sha512,
        "ARCHIVE_URL": archive_url,
        "HEAD_REF": args.head_ref,
    }

    if args.template_dir:
        render_template_tree(Path(args.template_dir).resolve(), port_dir, values)
    else:
        if not port_dir.is_dir():
            fail(f"{port_dir} does not exist; provide --template-dir for new ports")
        update_existing_port(port_dir, tag, version, sha512)

    cmake_package_name = args.cmake_package_name.strip() or default_cmake_package_name(args.port)
    cmake_target_name = args.cmake_target_name.strip() or default_cmake_target_name(args.port)
    cmake_header_names = split_input_list(args.cmake_header_names)
    cmake_library_names = split_input_list(args.cmake_library_names)

    if parse_bool(args.cmake_config):
        write_generated_cmake_config(
            port_dir,
            cmake_package_name,
            cmake_target_name,
            cmake_header_names,
            cmake_library_names,
        )

    vcpkg = vcpkg_executable(vcpkg_root)
    if not vcpkg.exists() and parse_bool(args.bootstrap):
        bootstrap_vcpkg(vcpkg_root)
    if not vcpkg.exists():
        fail(f"vcpkg executable does not exist at {vcpkg}")

    run([str(vcpkg), "format-manifest", str(port_dir / "vcpkg.json")])

    version_path = f"versions/{args.port[0]}-/{args.port}.json"
    if not args.skip_x_add_version:
        add_version_command = [str(vcpkg), "x-add-version", args.port]
        if parse_bool(args.overwrite_version):
            add_version_command.append("--overwrite-version")
        add_version_command.extend(shlex.split(args.x_add_version_args))
        run(add_version_command, cwd=vcpkg_root)

    if parse_bool(args.run_install):
        install_command = [str(vcpkg), "install", f"{args.port}:{args.test_triplet}"]
        install_command.extend(shlex.split(args.install_args))
        run(install_command, cwd=vcpkg_root)

    if parse_bool(args.consumer_test):
        if not parse_bool(args.run_install):
            fail("--consumer-test requires --run-install true")
        run_consumer_test(
            vcpkg_root,
            cmake_package_name,
            cmake_target_name,
            cmake_header_names,
            args.consumer_test_language,
            args.test_triplet,
        )

    did_change = changed(vcpkg_root, args.port, version_path)
    if parse_bool(args.dry_run):
        print_diff(vcpkg_root, args.port, version_path)

    write_outputs(
        {
            "tag": tag,
            "version": version,
            "sha512": sha512,
            "port-path": str(port_dir),
            "port-relative-path": port_path,
            "version-path": str(vcpkg_root / version_path),
            "version-relative-path": version_path,
            "changed": "true" if did_change else "false",
        }
    )

    print(f"Updated {args.port} to {version} from {archive_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
