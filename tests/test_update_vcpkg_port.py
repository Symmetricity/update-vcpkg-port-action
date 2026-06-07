import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.request import pathname2url


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_vcpkg_port.py"


def file_url(path: Path) -> str:
    return "file://" + pathname2url(str(path.resolve()))


def make_fake_vcpkg(root: Path, log_path: Path) -> None:
    exe = root / "vcpkg"
    exe.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$VCPKG_FAKE_LOG"
if [ "${1:-}" = "x-add-version" ]; then
  port="${2:-}"
  mkdir -p "versions/${port:0:1}-"
  cat > "versions/${port:0:1}-/${port}.json" <<JSON
{"versions":[{"version":"0.0.0","port-version":0,"git-tree":"fake"}]}
JSON
fi
""",
        encoding="utf-8",
    )
    exe.chmod(0o755)
    os.environ["VCPKG_FAKE_LOG"] = str(log_path)


def make_fake_cmake(root: Path, log_path: Path) -> None:
    exe = root / "cmake"
    exe.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$CMAKE_FAKE_LOG"
if [ "${1:-}" = "-S" ]; then
  source_dir="${2:-}"
  build_dir="${4:-}"
  grep -q "project(vcpkg_consumer_smoke LANGUAGES C)" "$source_dir/CMakeLists.txt"
  grep -q "find_package(streamvbyte CONFIG REQUIRED)" "$source_dir/CMakeLists.txt"
  grep -q "target_link_libraries(consumer PRIVATE streamvbyte::streamvbyte)" "$source_dir/CMakeLists.txt"
  grep -q "#include <streamvbyte.h>" "$source_dir/main.c"
  mkdir -p "$build_dir"
elif [ "${1:-}" = "--build" ]; then
  test -d "${2:-}"
fi
""",
        encoding="utf-8",
    )
    exe.chmod(0o755)
    os.environ["CMAKE_FAKE_LOG"] = str(log_path)


class UpdateVcpkgPortTests(unittest.TestCase):
    def test_template_rendering_runs_vcpkg_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vcpkg_root = tmp_path / "vcpkg"
            template_dir = tmp_path / "template"
            archive = tmp_path / "source.tar.gz"
            log_path = tmp_path / "vcpkg.log"
            output_path = tmp_path / "outputs.txt"

            (vcpkg_root / "ports").mkdir(parents=True)
            (vcpkg_root / "versions").mkdir()
            make_fake_vcpkg(vcpkg_root, log_path)
            archive.write_bytes(b"archive bytes")
            expected_sha = hashlib.sha512(b"archive bytes").hexdigest()

            template_dir.mkdir()
            (template_dir / "portfile.cmake.in").write_text(
                'REF "@TAG@"\nSHA512 @SOURCE_SHA512@\n',
                encoding="utf-8",
            )
            (template_dir / "vcpkg.json.in").write_text(
                '{"name":"@PORT@","version":"@VERSION@"}\n',
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["GITHUB_OUTPUT"] = str(output_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--port",
                    "examplelib",
                    "--vcpkg-root",
                    str(vcpkg_root),
                    "--upstream-repository",
                    "owner/examplelib",
                    "--tag",
                    "v3.0.0",
                    "--archive-url",
                    file_url(archive),
                    "--template-dir",
                    str(template_dir),
                    "--run-install",
                    "true",
                ],
                check=True,
                env=env,
            )

            portfile = (vcpkg_root / "ports" / "examplelib" / "portfile.cmake").read_text(encoding="utf-8")
            manifest = json.loads((vcpkg_root / "ports" / "examplelib" / "vcpkg.json").read_text(encoding="utf-8"))
            log = log_path.read_text(encoding="utf-8")
            outputs = dict(line.split("=", 1) for line in output_path.read_text(encoding="utf-8").splitlines())

            self.assertIn('REF "v3.0.0"', portfile)
            self.assertIn(f"SHA512 {expected_sha}", portfile)
            self.assertEqual(manifest["version"], "3.0.0")
            self.assertEqual(outputs["port-relative-path"], "ports/examplelib")
            self.assertEqual(outputs["version-relative-path"], "versions/e-/examplelib.json")
            self.assertIn("format-manifest", log)
            self.assertIn("x-add-version examplelib --overwrite-version", log)
            self.assertIn("install examplelib:x64-linux --clean-after-build", log)

    def test_existing_port_update_resets_port_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vcpkg_root = tmp_path / "vcpkg"
            port_dir = vcpkg_root / "ports" / "demo"
            archive = tmp_path / "source.tar.gz"
            log_path = tmp_path / "vcpkg.log"

            port_dir.mkdir(parents=True)
            (vcpkg_root / "versions").mkdir()
            make_fake_vcpkg(vcpkg_root, log_path)
            archive.write_bytes(b"new archive")
            expected_sha = hashlib.sha512(b"new archive").hexdigest()

            (port_dir / "portfile.cmake").write_text(
                'vcpkg_from_github(\n    REF "v1.0.0"\n    SHA512 ' + "0" * 128 + "\n)\n",
                encoding="utf-8",
            )
            (port_dir / "vcpkg.json").write_text(
                json.dumps({"name": "demo", "version": "1.0.0", "port-version": 2}) + "\n",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--port",
                    "demo",
                    "--vcpkg-root",
                    str(vcpkg_root),
                    "--tag",
                    "v2.0.0",
                    "--archive-url",
                    file_url(archive),
                    "--run-install",
                    "false",
                ],
                check=True,
                env=os.environ.copy(),
            )

            portfile = (port_dir / "portfile.cmake").read_text(encoding="utf-8")
            manifest = json.loads((port_dir / "vcpkg.json").read_text(encoding="utf-8"))

            self.assertIn('REF "v2.0.0"', portfile)
            self.assertIn(f"SHA512 {expected_sha}", portfile)
            self.assertEqual(manifest["version"], "2.0.0")
            self.assertNotIn("port-version", manifest)

    def test_generated_cmake_config_adds_imported_target_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vcpkg_root = tmp_path / "vcpkg"
            template_dir = tmp_path / "template"
            archive = tmp_path / "source.tar.gz"
            log_path = tmp_path / "vcpkg.log"

            (vcpkg_root / "ports").mkdir(parents=True)
            (vcpkg_root / "versions").mkdir()
            make_fake_vcpkg(vcpkg_root, log_path)
            archive.write_bytes(b"archive bytes")

            template_dir.mkdir()
            (template_dir / "portfile.cmake.in").write_text(
                'REF "@TAG@"\nSHA512 @SOURCE_SHA512@\n',
                encoding="utf-8",
            )
            (template_dir / "vcpkg.json.in").write_text(
                '{"name":"@PORT@","version":"@VERSION@"}\n',
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--port",
                    "streamvbyte",
                    "--vcpkg-root",
                    str(vcpkg_root),
                    "--upstream-repository",
                    "fast-pack/streamvbyte",
                    "--tag",
                    "v3.0.0",
                    "--archive-url",
                    file_url(archive),
                    "--template-dir",
                    str(template_dir),
                    "--cmake-config",
                    "true",
                    "--cmake-package-name",
                    "streamvbyte",
                    "--cmake-target-name",
                    "streamvbyte::streamvbyte",
                    "--cmake-header-names",
                    "streamvbyte.h",
                    "--cmake-library-names",
                    "streamvbyte",
                    "--run-install",
                    "false",
                ],
                check=True,
                env=os.environ.copy(),
            )

            port_dir = vcpkg_root / "ports" / "streamvbyte"
            portfile = (port_dir / "portfile.cmake").read_text(encoding="utf-8")
            config = (port_dir / "streamvbyteConfig.cmake").read_text(encoding="utf-8")
            usage = (port_dir / "usage").read_text(encoding="utf-8")

            self.assertIn('"${CMAKE_CURRENT_LIST_DIR}/streamvbyteConfig.cmake"', portfile)
            self.assertIn('"${CMAKE_CURRENT_LIST_DIR}/usage"', portfile)
            self.assertIn('DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"', portfile)
            self.assertIn("find_path(STREAMVBYTE_INCLUDE_DIR", config)
            self.assertIn('"streamvbyte.h"', config)
            self.assertIn("find_library(STREAMVBYTE_LIBRARY_RELEASE", config)
            self.assertIn("add_library(streamvbyte::streamvbyte UNKNOWN IMPORTED)", config)
            self.assertIn('INTERFACE_INCLUDE_DIRECTORIES "${STREAMVBYTE_INCLUDE_DIR}"', config)
            self.assertIn('IMPORTED_LOCATION_RELEASE "${STREAMVBYTE_LIBRARY_RELEASE}"', config)
            self.assertIn("find_package(streamvbyte CONFIG REQUIRED)", usage)
            self.assertIn("target_link_libraries(main PRIVATE streamvbyte::streamvbyte)", usage)

    def test_consumer_test_builds_generated_cmake_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vcpkg_root = tmp_path / "vcpkg"
            template_dir = tmp_path / "template"
            archive = tmp_path / "source.tar.gz"
            fake_bin = tmp_path / "bin"
            vcpkg_log_path = tmp_path / "vcpkg.log"
            cmake_log_path = tmp_path / "cmake.log"

            (vcpkg_root / "ports").mkdir(parents=True)
            (vcpkg_root / "versions").mkdir()
            (vcpkg_root / "scripts" / "buildsystems").mkdir(parents=True)
            (vcpkg_root / "scripts" / "buildsystems" / "vcpkg.cmake").write_text("", encoding="utf-8")
            fake_bin.mkdir()
            make_fake_vcpkg(vcpkg_root, vcpkg_log_path)
            make_fake_cmake(fake_bin, cmake_log_path)
            archive.write_bytes(b"archive bytes")

            template_dir.mkdir()
            (template_dir / "portfile.cmake.in").write_text(
                'REF "@TAG@"\nSHA512 @SOURCE_SHA512@\n',
                encoding="utf-8",
            )
            (template_dir / "vcpkg.json.in").write_text(
                '{"name":"@PORT@","version":"@VERSION@"}\n',
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--port",
                    "streamvbyte",
                    "--vcpkg-root",
                    str(vcpkg_root),
                    "--upstream-repository",
                    "fast-pack/streamvbyte",
                    "--tag",
                    "v3.0.0",
                    "--archive-url",
                    file_url(archive),
                    "--template-dir",
                    str(template_dir),
                    "--cmake-config",
                    "true",
                    "--cmake-package-name",
                    "streamvbyte",
                    "--cmake-target-name",
                    "streamvbyte::streamvbyte",
                    "--cmake-header-names",
                    "streamvbyte.h",
                    "--cmake-library-names",
                    "streamvbyte",
                    "--consumer-test",
                    "true",
                    "--consumer-test-language",
                    "C",
                ],
                check=True,
                env=env,
            )

            vcpkg_log = vcpkg_log_path.read_text(encoding="utf-8")
            cmake_log = cmake_log_path.read_text(encoding="utf-8")
            self.assertIn("install streamvbyte:x64-linux --clean-after-build", vcpkg_log)
            self.assertIn("-DCMAKE_TOOLCHAIN_FILE=", cmake_log)
            self.assertIn("-DVCPKG_TARGET_TRIPLET=x64-linux", cmake_log)
            self.assertIn("--build", cmake_log)


if __name__ == "__main__":
    unittest.main()
