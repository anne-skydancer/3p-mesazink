#!/usr/bin/env python3
"""Build the mesazink package: clone patched Mesa, build Zink/WGL, assemble layout.

Produces under build/ (which autobuild then packages):
  bin/release/opengl32.dll        Mesa GDI opengl32 frontend
  bin/release/libgallium_wgl.dll  Gallium WGL driver (Zink over Vulkan)
  LICENSES/mesazink.txt           Mesa license (docs/license.rst)

The Mesa checkout is pinned to MESA_REVISION and patched with the files under
patches/; a marker file (.vulkanstorm-source.json) makes repeated runs idempotent.

Layout note: the viewer's Copy3rdPartyLibs.cmake copies
${AUTOBUILD_INSTALL_DIR}/bin/release/{opengl32,libgallium_wgl}.dll into the
staging dir, and viewer_manifest.py installs them into the viewer's mesa\
subdirectory.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

MESA_REPOSITORY = "https://gitlab.freedesktop.org/mesa/mesa.git"
MESA_REVISION = "00e42c51b10d8e0769489156fa414f111897d515"
MESA_VERSION = "26.3.0-devel"

ROOT = Path(__file__).resolve().parent
PATCH_DIR = ROOT / "patches"
PATCHES = [
    PATCH_DIR / "mesa-zink-null-guards.patch",
    PATCH_DIR / "mesa-msvc-release.patch",
]


def run(command, cwd=None):
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def patch_digest(patches):
    digest = hashlib.sha256()
    for patch in patches:
        digest.update(patch.read_bytes())
    return digest.hexdigest()


def remove_tree(path: Path):
    def remove_readonly(function, filename, error_info):
        os.chmod(filename, stat.S_IWRITE)
        function(filename)

    # The freshly-created directory is briefly grabbed by the Windows search
    # indexer / AV scanner, so deletion can fail with WinError 32. Retry a
    # few times with a short backoff.
    import time
    for attempt in range(10):
        try:
            shutil.rmtree(path, onerror=remove_readonly)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(1)


def swap_into_place(temp: Path, out: Path):
    """Atomically-ish replace out with temp (built alongside, then moved)."""
    if out.exists():
        remove_tree(out)
    temp.rename(out)


def ensure_checkout(destination: Path):
    marker = destination / ".vulkanstorm-source.json"
    expected = {
        "repository": MESA_REPOSITORY,
        "revision": MESA_REVISION,
        "patches": patch_digest(PATCHES),
    }
    if marker.exists() and json.loads(marker.read_text(encoding="utf-8")) == expected:
        print(f"Mesa: using prepared source at {destination}")
        return

    if destination.exists():
        remove_tree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--filter=blob:none", "--no-checkout", MESA_REPOSITORY, str(destination)])
    run(["git", "checkout", "--detach", MESA_REVISION], cwd=destination)
    for patch in PATCHES:
        run(["git", "apply", "--check", "--ignore-space-change", str(patch)], cwd=destination)
        run(["git", "apply", "--ignore-space-change", str(patch)], cwd=destination)
    marker.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")


def ensure_python_build_tools() -> Path:
    modules = ("mesonbuild", "mako", "packaging", "yaml", "setuptools")
    if any(importlib.util.find_spec(module) is None for module in modules):
        run([sys.executable, "-m", "pip", "install",
             "meson>=1.4", "mako", "packaging", "pyyaml", "setuptools"])

    ninja = shutil.which("ninja")
    if ninja is None:
        run([sys.executable, "-m", "pip", "install", "ninja"])
        scripts = Path(sys.executable).parent / "Scripts"
        ninja_path = scripts / ("ninja.exe" if os.name == "nt" else "ninja")
        if not ninja_path.exists():
            raise RuntimeError("ninja was installed but its executable could not be located")
        return ninja_path
    return Path(ninja)


def build_mesa(source: Path, check_only: bool) -> None:
    version = (source / "VERSION").read_text(encoding="utf-8").strip()
    if version != MESA_VERSION:
        raise RuntimeError(f"Mesa revision declares {version}, expected {MESA_VERSION}")
    if check_only:
        return

    ninja = ensure_python_build_tools()
    build_dir = source / "build-vulkanstorm"
    configured = (build_dir / "build.ninja").exists()
    if not configured:
        run([
            sys.executable, "-m", "mesonbuild.mesonmain", "setup", str(build_dir),
            "-Dbuildtype=release",
            "-Dvsenv=true",
            "-Dgallium-drivers=zink",
            "-Dvulkan-drivers=",
            "-Dllvm=disabled",
            "-Dgles1=disabled",
            "-Dgles2=disabled",
            "-Dglx=disabled",
            "-Degl=disabled",
            "-Dmicrosoft-clc=disabled",
            "-Dzlib:default_library=static",
        ], cwd=source)
        # -Dvsenv=true makes meson capture the Visual Studio environment and
        # drive the compile through its own vsenv-activated backend. A bare
        # ninja invocation afterwards would not have cl.exe on PATH, so the
        # first compile must go through meson.
        run([sys.executable, "-m", "mesonbuild.mesonmain", "compile", "-C", str(build_dir)], cwd=source)
    else:
        run([str(ninja), "-C", str(build_dir)])


def assemble(source: Path, out: Path) -> None:
    # Assemble in place: never delete the output directory. Deleting a
    # just-created directory races the Windows search indexer / AV scanner
    # (WinError 32 on the directory handle), which is unrecoverable from
    # inside the process once the handle is taken.
    build_dir = source / "build-vulkanstorm"
    artifacts = [
        (build_dir / "src/gallium/targets/wgl/libgallium_wgl.dll", out / "bin" / "release" / "libgallium_wgl.dll"),
        (build_dir / "src/gallium/targets/libgl-gdi/opengl32.dll", out / "bin" / "release" / "opengl32.dll"),
        (source / "docs/license.rst", out / "LICENSES" / "mesazink.txt"),
    ]
    for src, _ in artifacts:
        if not src.exists():
            raise RuntimeError(f"Expected build artifact missing: {src}")

    (out / "bin" / "release").mkdir(parents=True, exist_ok=True)
    (out / "LICENSES").mkdir(parents=True, exist_ok=True)
    for src, dst in artifacts:
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dst)

    # autobuild reads version_file relative to the build directory.
    (out / "VERSION.txt").write_text("26.3.0-devel-git.00e42c51b1\n", encoding="utf-8")
    print(f"mesazink package assembled: {out}")


def parse_args():
    parser = argparse.ArgumentParser(description="Build the mesazink 3p package")
    parser.add_argument("--root", type=Path, default=ROOT / "mesa-src",
                        help="Mesa checkout location (default: ./mesa-src)")
    parser.add_argument("--out", type=Path, default=ROOT / "build",
                        help="Package assembly output (default: ./build)")
    parser.add_argument("--check", action="store_true",
                        help="fetch and patch sources without building Mesa")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_checkout(args.root)
    build_mesa(args.root, args.check)
    if not args.check:
        assemble(args.root, args.out)
        print(f"mesazink package assembled: {args.out}")
        print(f"  Mesa: {MESA_REVISION} ({MESA_VERSION})")
        for patch in PATCHES:
            print(f"  patch: {patch.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
