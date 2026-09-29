# Mesa 26.3 upstream refresh qualification

Candidate: `26.3.0-devel-git.4c18bbc637-pkg1`.
Mesa: `4c18bbc63765c2f468c3fa094242e8654e78d196` (2026-09-29 09:26:29 UTC).
Recipe commit used by CI: `4ab3c9f`.
CI: https://github.com/anne-skydancer/3p-mesazink/actions/runs/36554675650

## Source and patch review

- Upstream main was queried directly before selecting the pin.
- Contains `3fe13b1c074fb1a3f804f315b52b9324b82036c0`, the null Vulkan pipeline guard.
- All three retained patches pass apply checks against this exact revision.
- The separate shader/program null checks and Windows loader metadata initialization
  are still absent upstream. No local protection was removed.
- The existing pinned/modified source checkout was not replaced.

## Completed source tests

- 16 package configuration, assembly, provenance and archive tests passed.
- Actual patched WGL loader helper: 32 poisoned-output cases passed.
- Current runtime baseline (`00e42c51b1`) passed the core/shared-context, mesh,
  particle geometry, simulation/order, service and ordered blending tests on
  the AMD Radeon RX 9070 XT before candidate comparison.

## Candidate qualification

All automated qualification passed on 2026-09-29. CI Windows, Linux and cross-platform
archive qualification jobs succeeded. Publication was intentionally disabled.
Both downloaded archives independently passed `package_support.py --archives`.

Linux: GLX dependency checks and Xvfb/software-Vulkan Zink smoke test passed,
reporting Mesa `26.3.0-devel (git-4c18bbc637)` and OpenGL 4.6.

Windows: tests used the exact CI archive on AMD Radeon RX 9070 XT. The context
reported Zink, OpenGL 4.6 and the expected Mesa commit. All GPU particle extensions
were available. Results:

- Core-context creation and shared-context texture visibility passed.
- 33,068 resident mesh LOD commands; direct/indirect pixel comparisons, both index
  widths, progressive LOD, 120 shared-avatar commands, skinning, refinement copies,
  batch gather/MDI, conservative visibility and transformed geometry passed.
- 546,816 particle geometry/attribute checks passed.
- 366,482 particle simulation fields, ordering entries and ranges passed.
- GPU birth allocation, admission, recycling, ribbon continuity, dispatch state
  restoration, residency repair and reload passed.
- Ordered particle blending passed for RGBA32F and RGBA16F: 64 blend pairs and
  2/17/257/8192 draws, depth read/write, alpha discard and glow.
- Hidden-window WGL loader/presentation smoke test completed without a GL error.

Harness source: Vulkanstorm `d1f717241b`, under `scripts/perf/`:
`gl_core_probe.py`, `test_gl_compute_mesh.py`, `test_particle_compute.py`,
`test_particle_pipeline.py`, `test_particle_pipeline_service.py`,
`test_particle_ordered_blend.py`, `apitrace_wgl_probe.py`.
All were run with `GALLIUM_DRIVER=zink` and the candidate DLL supplied explicitly;
the blend test was repeated with `--target-format rgba16f`.
Logs remain under local `build/candidate-*.log`. No FPS improvement is claimed.

## Scope limits

Automated GL tests cover rendering mechanisms, not a logged-in Second Life scene,
teleport sequence or performance parity. In-world validation of this new Mesa
runtime remains a distinct qualification step. The viewer dependency pin and
staged viewer DLLs are unchanged. No release assets are overwritten.

## Verified archive SHA-256

- `mesazink-26.3.0-devel-git.4c18bbc637-pkg1-linux64.tar.zst`
  `4d1977305cb90344b3854f5716e2a09ef09494470af272e60ca2139423c3166e`
- `mesazink-26.3.0-devel-git.4c18bbc637-pkg1-windows64.tar.zst`
  `f047f7e53bc86a474084be5ac2f9d1a4821372872bfefb9b0415714426bb7d1c`

## pkg2 shared-dependency integration correction

The first full viewer configure exposed a pkg1 archive collision with SoLoud's
root `VERSION.txt`. Isolated Autobuild installation had not exercised coexistence.
Pkg2 uses `mesazink-version.txt`; Mesa source and patches remain unchanged.

Recipe: `5e64789c55f53a11a38b9a827bc9e4579606af44`.
CI: https://github.com/anne-skydancer/3p-mesazink/actions/runs/36557766634

All 17 package tests, Windows/Linux builds, Linux software-Vulkan smoke and
archive identity checks passed. The actual pkg2 Windows binaries again passed
core/shared-context, mesh, particle geometry, simulation/order, service and
RGBA32F/RGBA16F blending tests on RX 9070 XT. Both archive payloads were explicitly
checked to contain the namespaced version file and omit root VERSION.txt.
Pkg2 is the published replacement; the viewer pins on master and vkstorm-devel
were updated independently. In-world viewer qualification remains pending.

- `mesazink-26.3.0-devel-git.4c18bbc637-pkg2-linux64.tar.zst`
  `76c3ed2a612f0e76a88becfc3effca90462102849bb02e8908fbf2ebc80ead32`
- `mesazink-26.3.0-devel-git.4c18bbc637-pkg2-windows64.tar.zst`
  `30be90eff6b05977de8fae972321ec7c576412430de6e86c3ec01366f2fdceef`

## Upstream version naming correction

The current release is `26.3.0-devel`, with no added Git or packaging suffix. The earlier suffixed releases above are historical and superseded. Mesa source and patches are unchanged; revision identity is recorded in provenance instead of the version.

Recipe: `9d9394f7caf4be8a0d6b9c2079be6784113fe66c`.
CI: https://github.com/anne-skydancer/3p-mesazink/actions/runs/36559328204
Release: https://github.com/anne-skydancer/3p-mesazink/releases/tag/26.3.0-devel

Both platform builds, all 17 package tests, Linux software-Vulkan smoke, and combined archive verification passed. The exact CI archives were published and viewer pins updated independently in master and vkstorm-devel. The shared dependency metadata remains mesazink-version.txt.

- `mesazink-26.3.0-devel-linux64.tar.zst`: `65c5118324210b06a43c452d66f1b6fadcce61f6d2ea6223ebcf79b02e58c144`
- `mesazink-26.3.0-devel-windows64.tar.zst`: `fe92b7df8b266784997b4b28fba9341a37987faa087fd9e5a63ae4f32f071740`
