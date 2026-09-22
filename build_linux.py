#!/usr/bin/env python3
"""Build the Linux x86-64 GLVND/GLX Mesa Zink runtime."""
import argparse
import os
from pathlib import Path
import platform
import shutil
import sys

from build import ROOT, MESA_VERSION, PACKAGE_VERSION, ensure_checkout, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'mesa-src')
    parser.add_argument('--out', type=Path, default=ROOT / 'build')
    args = parser.parse_args()
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        parser.error('requires Linux x86-64')
    source, out = args.root.resolve(), args.out.resolve()
    ensure_checkout(source)
    if (source / 'VERSION').read_text().strip() != MESA_VERSION:
        raise RuntimeError('Unexpected Mesa source version')
    build = source / 'build-linux-zink'
    meson = [sys.executable, '-m', 'mesonbuild.mesonmain']
    options = [
        '--prefix=/usr', '--libdir=lib', '-Dbuildtype=release',
        '-Dplatforms=x11', '-Dgallium-drivers=zink', '-Dvulkan-drivers=',
        '-Dllvm=disabled', '-Dglx=dri', '-Dglvnd=enabled', '-Degl=disabled',
        '-Dgbm=disabled', '-Dgles1=disabled', '-Dgles2=disabled',
        '-Dgallium-va=disabled', '-Dmicrosoft-clc=disabled',
        '-Dbuild-tests=false', '-Dvideo-codecs=',
    ]
    run(meson + ['setup'] + (['--reconfigure'] if (build / 'build.ninja').exists() else [])
        + [str(build), str(source)] + options)
    run(meson + ['compile', '-C', str(build), '-j', str(min(os.cpu_count() or 2, 4))])
    lib = out / 'lib/release/mesa'
    lib.mkdir(parents=True, exist_ok=True)
    gallium = build / 'src/gallium/targets/dri' / f'libgallium-{MESA_VERSION}.so'
    glx = build / 'src/glx/libGLX_mesa.so.0.0.0'
    for src, name in [(gallium, gallium.name), (glx, 'libGLX_mesa.so.0')]:
        shutil.copy2(src, lib / name)
        # Keep the matching Gallium library beside its GLX provider after relocation.
        run(['patchelf', '--set-rpath', '$ORIGIN', str(lib / name)])
    (out / 'LICENSES').mkdir(exist_ok=True)
    shutil.copy2(source / 'docs/license.rst', out / 'LICENSES/mesazink.txt')
    (out / 'VERSION.txt').write_text(PACKAGE_VERSION + '\n')


if __name__ == '__main__':
    main()
