"""Compile and execute the actual patched helper against poisoned output storage.

Usage: python tests/check_wgl_loader_init.py <patched-mesa-source> [clang]
Requires a Windows-targeting Clang compiler and Windows runtime. The helper and
Kopper storage declarations are extracted verbatim; framebuffer/device wrappers
contain only fields used by this helper. This is not a WGL integration test.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve()
compiler = sys.argv[2] if len(sys.argv) > 2 else "clang"
implementation = (source / "src/gallium/frontends/wgl/stw_st.c").read_text()
header = (source / "include/kopper_interface.h").read_text()
helper = re.search(
    r"static void\s+stw_st_fill_private_loader_data\([^}]+\n}", implementation
).group()
declarations = "\n".join(
    re.search(r"struct " + name + r" \{.*?\n};", header, re.S).group()
    for name in ("kopper_vk_surface_create_storage", "kopper_loader_info")
)
test = r'''
#define VK_USE_PLATFORM_WIN32_KHR
#include <windows.h>
#include <vulkan/vulkan.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
DECLARATIONS
struct stw_framebuffer { HWND hWnd; int swap_interval; };
struct stw_st_framebuffer { struct stw_framebuffer *fb; };
struct device { int swap_interval; };
static struct device device_state;
static struct device *stw_dev = &device_state;
HELPER
int main(void) {
   struct stw_framebuffer fb = { (HWND)(uintptr_t)0x1234, 0 };
   struct stw_st_framebuffer stwfb = { &fb };
   const int intervals[] = { -1, 0, 1, 2 };
   const unsigned char poisons[] = { 0x00, 0x55, 0xaa, 0xff };
   for (int default_interval = 0; default_interval <= 1; ++default_interval) {
      stw_dev->swap_interval = default_interval;
      for (unsigned i = 0; i < 4; ++i) {
         fb.swap_interval = intervals[i];
         for (unsigned p = 0; p < 4; ++p) {
            struct kopper_loader_info out, expected;
            memset(&out, poisons[p], sizeof(out));
            memset(&expected, 0, sizeof(expected));
            VkWin32SurfaceCreateInfoKHR *win32 = (void *)&expected.bos;
            win32->sType = VK_STRUCTURE_TYPE_WIN32_SURFACE_CREATE_INFO_KHR;
            win32->hinstance = GetModuleHandle(NULL);
            win32->hwnd = fb.hWnd;
            expected.has_alpha = true;
            expected.initial_swap_interval = intervals[i] == -1
               ? default_interval : intervals[i];
            stw_st_fill_private_loader_data(&stwfb, &out);
            assert(out.present_opaque == false);
            assert(out.compression == 0);
            assert(memcmp(&out, &expected, sizeof(out)) == 0);
         }
      }
   }
   return 0;
}
'''.replace("DECLARATIONS", declarations).replace("HELPER", helper)
with tempfile.TemporaryDirectory(prefix="wgl-loader-test-") as folder:
    test_source = Path(folder) / "check.c"
    executable = Path(folder) / "check.exe"
    test_source.write_text(test)
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(source / "include"), str(test_source),
                    "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: 32 poisoned-output cases; surface fields and metadata match")
