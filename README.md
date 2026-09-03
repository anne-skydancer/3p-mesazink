# 3p-mesazink

Third-party Mesa Zink package for the Vulkanstorm viewer — the Gallium WGL
`opengl32.dll` + `libgallium_wgl.dll` that let the viewer run its OpenGL
pipeline over Vulkan ("Mesa/Zink" renderer selection).

## Contents

| Component | Upstream | Pinned | What we ship |
|---|---|---|---|
| Mesa (Zink gallium driver, WGL frontend) | [gitlab.freedesktop.org/mesa/mesa](https://gitlab.freedesktop.org/mesa/mesa) | `00e42c51b10d8e0769489156fa414f111897d515` (`26.3.0-devel`) | `bin/release/opengl32.dll`, `bin/release/libgallium_wgl.dll` |

The pinned Mesa main revision already carries AMD RX9000-series (gfx12/RADV)
support. Two local patches are applied on top:

| Patch | Purpose |
|---|---|
| `patches/mesa-zink-null-guards.patch` | Crash-region fix: degrade gracefully on failed shader/program creation instead of crashing (pipe_nir, zink batch/context/screen, null_fs). |
| `patches/mesa-msvc-release.patch` | MSVC release-build fix in the SPIR-V cooperative-matrix translator. |

## Build configuration

Meson, MSVC toolchain, release build, Zink only (no Vulkan drivers, no LLVM,
no EGL/GLX/GLES — the WGL frontend is self-contained):

```
meson setup build-vulkanstorm -Dbuildtype=release -Dvsenv=true \
    -Dgallium-drivers=zink -Dvulkan-drivers= -Dllvm=disabled \
    -Dgles1=disabled -Dgles2=disabled -Dglx=disabled -Degl=disabled \
    -Dmicrosoft-clc=disabled -Dzlib:default_library=static
ninja -C build-vulkanstorm
```

## How the viewer consumes this

The viewer fetches the package via `use_prebuilt_binary(mesazink)` (gated by
`-DUSE_MESAZINK:BOOL=ON`, default OFF). `indra/cmake/MesaZink.cmake` verifies
both DLLs, `Copy3rdPartyLibs.cmake` stages them, and `viewer_manifest.py`
installs them into the viewer's `mesa\` subdirectory. The viewer delay-loads
`opengl32.dll`; when the Mesa/Zink renderer is selected,
`LLAppViewerWin32::selectGLBackend()` points the DLL search path at `mesa\`
and preloads the bundled `opengl32.dll` before the first GL import resolves.

## Building the package

Prerequisites: Visual Studio 2022 (MSVC), Python 3, and the Python packages
`meson>=1.4 mako packaging pyyaml setuptools ninja` (the build script can
install them).

```
python build.py            # clone, patch, build Mesa, assemble build/
autobuild package          # produce the release tarball
```

`python build.py --check` fetches and patches the sources without compiling.

## Licenses

Mesa: MIT (see `LICENSES/mesazink.txt`, copied from Mesa's
`docs/license.rst`).
