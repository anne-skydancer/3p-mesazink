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
