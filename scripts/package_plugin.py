#!/usr/bin/env python3
"""Build an installable local-marketplace ZIP from files not ignored by Git."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLUGIN_DIR = Path("plugins/travel-planning")
DEFAULT_MARKETPLACE_FILE = Path(".agents/plugins/marketplace.json")
DEFAULT_OUTPUT = Path("output/travel-planning-marketplace.zip")
DEFAULT_BUNDLE_NAME = "travel-planning-marketplace"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=DEFAULT_PLUGIN_DIR,
        help=f"plugin directory relative to the repository (default: {DEFAULT_PLUGIN_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"ZIP path relative to the repository (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--bundle-name",
        default=DEFAULT_BUNDLE_NAME,
        help=f"top-level directory inside the ZIP (default: {DEFAULT_BUNDLE_NAME})",
    )
    return parser.parse_args()


def repository_relative(path: Path, argument_name: str) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPOSITORY_ROOT / path).resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise SystemExit(f"{argument_name} must stay inside {REPOSITORY_ROOT}") from error


def package_files(plugin_dir: Path) -> list[Path]:
    included_paths = [Path("README.md"), Path("LICENSE"), DEFAULT_MARKETPLACE_FILE, plugin_dir]
    result = subprocess.run(
        [
            "git",
            "-C",
            os.fspath(REPOSITORY_ROOT),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *(os.fspath(path) for path in included_paths),
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    candidates = [Path(os.fsdecode(item)) for item in result.stdout.split(b"\0") if item]
    return sorted(
        path
        for path in candidates
        if (REPOSITORY_ROOT / path).is_file() or (REPOSITORY_ROOT / path).is_symlink()
    )


def add_symlink(archive: zipfile.ZipFile, source: Path, archive_name: Path) -> None:
    mode = source.lstat().st_mode
    info = zipfile.ZipInfo(archive_name.as_posix())
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | stat.S_IMODE(mode)) << 16
    archive.writestr(info, os.readlink(source).encode())


def build_archive(plugin_dir: Path, output: Path, bundle_name: str) -> int:
    source_root = REPOSITORY_ROOT / plugin_dir
    if not source_root.is_dir():
        raise SystemExit(f"plugin directory does not exist: {source_root}")
    if not (source_root / ".codex-plugin/plugin.json").is_file():
        raise SystemExit(f"missing plugin manifest: {source_root / '.codex-plugin/plugin.json'}")
    if not (REPOSITORY_ROOT / DEFAULT_MARKETPLACE_FILE).is_file():
        raise SystemExit(
            f"missing marketplace catalog: {REPOSITORY_ROOT / DEFAULT_MARKETPLACE_FILE}"
        )

    files = package_files(plugin_dir)
    if not files:
        raise SystemExit(f"no packageable files found under {plugin_dir}")

    output_path = REPOSITORY_ROOT / output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for relative_path in files:
                source = REPOSITORY_ROOT / relative_path
                archive_name = Path(bundle_name) / relative_path
                if source.is_symlink():
                    add_symlink(archive, source, archive_name)
                else:
                    archive.write(source, archive_name.as_posix())
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return len(files)


def main() -> None:
    args = parse_args()
    plugin_dir = repository_relative(args.plugin_dir, "--plugin-dir")
    output = repository_relative(args.output, "--output")
    bundle_name = args.bundle_name.strip()
    if not bundle_name or Path(bundle_name).name != bundle_name or bundle_name in {".", ".."}:
        raise SystemExit("--bundle-name must be one directory name")
    if output == plugin_dir or plugin_dir in output.parents:
        raise SystemExit("--output must not be inside the plugin directory")

    file_count = build_archive(plugin_dir, output, bundle_name)
    print(f"Created {REPOSITORY_ROOT / output} ({file_count} files)")


if __name__ == "__main__":
    main()
