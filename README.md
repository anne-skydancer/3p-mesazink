# 3p-mesazink

Third-party Mesa Zink package for the Vulkanstorm viewer — the Gallium WGL
`opengl32.dll` + `libgallium_wgl.dll` that let the viewer run its OpenGL
pipeline over Vulkan ("Mesa/Zink" renderer selection).

## Contents

| Component | Upstream | Pinned | What we ship |
|---|---|---|---|
| Mesa (Zink gallium driver, WGL frontend) | [gitlab.freedesktop.org/mesa/mesa](https://gitlab.freedesktop.org/mesa/mesa) | `00e42c51b10d8e0769489156fa414f111897d515` (`26.3.0-devel`) | `bin/release/opengl32.dll`, `bin/release/libgallium_wgl.dll` |

The pinned Mesa main revision already carries AMD RX9000-series (gfx12/RADV)
support. Three local patches are applied on top:

| Patch | Purpose |
|---|---|
| `patches/mesa-zink-null-guards.patch` | Crash-region fix: degrade gracefully on failed shader/program creation instead of crashing (pipe_nir, zink batch/context/screen, null_fs). |
| `patches/mesa-msvc-release.patch` | MSVC release-build fix in the SPIR-V cooperative-matrix translator. |
| `patches/mesa-wgl-loader-init.patch` | Initialize all Kopper loader metadata and inherit the effective WGL swap interval. |

The loader metadata correction is included in the existing package baseline,
without changing its version or the pinned Mesa revision. The patch preserves
alpha-capable presentation; it does not force opaque surfaces or change Windows
present-mode selection or fence waits. Performance and visual effects require
runtime validation.

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

For the loader initialization regression check on Windows, with a Windows-targeting
Clang on PATH:

```
python tests/check_wgl_loader_init.py <patched-mesa-source>
```

This compiles the actual helper extracted from that source and checks surface
fields and complete metadata against 32 poisoned-output cases. It does not open
a window or qualify driver behavior. Use Meson `debugoptimized` for diagnostic
DLLs with symbols; compare builds made with identical options and toolchain.

## Licenses

Mesa: MIT (see `LICENSES/mesazink.txt`, copied from Mesa's
`docs/license.rst`).

## Linux x86-64 package

`build_linux.py` builds the same pinned Mesa revision and patches as Windows,
with Zink as the only Gallium driver and a GLVND GLX provider for the viewer's
SDL/X11 OpenGL path. The package contains:

- `lib/release/mesa/libGLX_mesa.so.0`
- `lib/release/mesa/libgallium-26.3.0-devel.so`
- `LICENSES/mesazink.txt`

The GLX provider locates its matching Gallium library through `$ORIGIN`.
System GLVND, X11/XCB, libdrm, and the system Vulkan loader/ICD remain external
runtime dependencies. The CI build targets Ubuntu 24.04 x86-64, matching the
viewer CI; compatibility with older distributions has not been qualified.
EGL/Wayland and vendor Vulkan drivers are not included in this package.

The Linux package workflow records ELF dependencies and runs `glxinfo` through
Zink using Xvfb and the runner's software Vulkan driver before packaging.
This smoke check does not qualify AMD/NVIDIA rendering or viewer performance.

For an extracted package, a standalone GLX smoke check is:

```sh
LD_LIBRARY_PATH="$PWD/lib/release/mesa${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
__GLX_VENDOR_LIBRARY_NAME=mesa MESA_LOADER_DRIVER_OVERRIDE=zink \
GALLIUM_DRIVER=zink glxinfo -B
```

Do not install these libraries over the system Mesa libraries. Viewer package
staging and renderer selection must explicitly opt into this private provider.
The viewer's Linux renderer selector integration is separate from producing
this downloadable runtime.
