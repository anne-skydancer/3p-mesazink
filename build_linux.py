#!/usr/bin/env python3
"""Build the Linux x86-64 GLVND/GLX Mesa Zink runtime."""
import argparse
import os
from pathlib import Path
import platform
import shutil
import sys

from build import ROOT, MESA_VERSION, PACKAGE_VERSION, ensure_checkout, run
from package_support import begin, configure, build_directory, toolchain_identity, assemble


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'mesa-src')
    parser.add_argument('--out', type=Path, default=ROOT / 'build')
    args = parser.parse_args()
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        parser.error('requires Linux x86-64')
    source, out = args.root.resolve(), args.out.resolve()
    begin(out)
    ensure_checkout(source)
    if (source / 'VERSION').read_text().strip() != MESA_VERSION:
        raise RuntimeError('Unexpected Mesa source version')
    toolchain = toolchain_identity()
    build = build_directory(source, 'build-linux-zink', toolchain)
    meson = [sys.executable, '-m', 'mesonbuild.mesonmain']
    options = [
        '--prefix=/usr', '--libdir=lib', '-Dbuildtype=release',
        '-Dplatforms=x11', '-Dgallium-drivers=zink', '-Dvulkan-drivers=',
        '-Dllvm=disabled', '-Dglx=dri', '-Dglvnd=enabled', '-Dglvnd-vendor-name=vulkanstorm', '-Degl=disabled',
        '-Dgbm=disabled', '-Dgles1=disabled', '-Dgles2=disabled',
        '-Dgallium-va=disabled', '-Dmicrosoft-clc=disabled',
        '-Dbuild-tests=false', '-Dvideo-codecs=',
    ]
    configuration = configure(source, build, options, run)
    run(meson + ['compile', '-C', str(build), '-j', str(min(os.cpu_count() or 2, 4))])
    gallium = build / 'src/gallium/targets/dri' / f'libgallium-{MESA_VERSION}.so'
    glx = build / 'src/glx/libGLX_vulkanstorm.so.0.0.0'
    def relocate(stage):
        lib = stage / 'lib/release/mesa'
        for name in ['libgallium_vulkanstorm.so', 'libGLX_vulkanstorm.so.0']:
            run(['patchelf', '--set-rpath', '$ORIGIN', str(lib / name)])
        run(['patchelf', '--set-soname', 'libgallium_vulkanstorm.so', str(lib / 'libgallium_vulkanstorm.so')])
        run(['patchelf', '--replace-needed', gallium.name, 'libgallium_vulkanstorm.so',
             str(lib / 'libGLX_vulkanstorm.so.0')])
    assemble(out, [(gallium, 'lib/release/mesa/libgallium_vulkanstorm.so'),
                   (glx, 'lib/release/mesa/libGLX_vulkanstorm.so.0'),
                   (source / 'docs/license.rst', 'LICENSES/mesazink.txt')],
             configuration, toolchain, relocate)


if __name__ == '__main__':
    main()
