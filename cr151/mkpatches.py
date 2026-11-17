"""Writes patches 0101 and 0102 against the tree as it is after upstream patches 0001-0052 (run after patch.sh,
before they exist in /opt/cn/patches). Prints both patches; the caller saves them into browser/cr151/patches.
usage: python3 mkpatches.py <repo root> <out dir>
"""
import difflib
import os
import sys

repo, out = sys.argv[1], sys.argv[2]


def patch(name, header, edits):
    text = []
    for rel, old, new in edits:
        with open(os.path.join(repo, rel)) as f:
            a = f.read()
        if old not in a:
            sys.exit(f"{name}: context not found in {rel}")
        b = a.replace(old, new, 1)
        text += difflib.unified_diff(a.splitlines(True), b.splitlines(True), "a/" + rel, "b/" + rel)
    with open(os.path.join(out, name), "w") as f:
        f.write(header + "".join(text))
    print("wrote", name)


patch("0101-arm-cortex-a55-tune-and-fpu.patch",
      "# why: the C1 is a Cortex-A55 running this 32-bit code in AArch32. With arm_version 8 (args), use the ARMv8 FPU\n"
      "# (VFPv4/NEON with the v8 extensions) and A55 scheduling. arm_fpu and arm_tune are not GN args in M151.\n",
      [("src/build/config/compiler_cpu_abi.gn",
        '    if (arm_fpu != "") {\n      cpu_abi_cflags += [ "-mfpu=$arm_fpu" ]\n    }\n',
        '    if (arm_version == 8) {\n'
        '      # viiees: Cortex-A55 (LG C1) in AArch32.\n'
        '      cpu_abi_cflags += [\n'
        '        "-mfpu=neon-fp-armv8",\n'
        '        "-mtune=cortex-a55",\n'
        '      ]\n'
        '    } else if (arm_fpu != "") {\n      cpu_abi_cflags += [ "-mfpu=$arm_fpu" ]\n    }\n')])

ARM = ('  if h[:4] == b"\\x7fELF" and h[4] == 1 and h[18:20] == b"\\x03\\x00":\n'
       '    return ["qemu-i386-static"]\n')
ARM_NEW = ARM + ('  # viiees: on an arm64 build host V8 builds these tools with the 32-bit ARM\n'
                 '  # target toolchain (snapshot_toolchain.gni), and arm64 cannot exec AArch32.\n'
                 '  if h[:4] == b"\\x7fELF" and h[4] == 1 and h[18:20] == b"\\x28\\x00":\n'
                 '    return ["qemu-arm-static", "-L", "/work/sysroot-tv"]\n')
patch("0102-run-arm32-host-tools-under-qemu-arm.patch",
      "# why: on an arm64 build host the V8 snapshot and generator tools are 32-bit ARM binaries of the target\n"
      "# toolchain, which arm64 cannot execute. Run them under qemu-arm-static with the target sysroot.\n",
      [("src/build/gn_run_binary.py", ARM, ARM_NEW), ("src/v8/tools/run.py", ARM, ARM_NEW)])
