# Windows guest-stack workaround, revision 2

Experimental workaround for the **Windows x64 v20261017 release** of
[chenxiao07/KytyPS5](https://github.com/chenxiao07/KytyPS5/releases/tag/v20261017),
source commit `30f04f7b05baff3c3c1e8d844c6bdd62f4b3735b`.
Published 18 October 2026. The original executable is preserved.

## What was observed

The emulator repeatedly ended during early frame setup with `0xC0000409`.
Dump analysis on the reporting Windows 11 PC found fast-fail subcode 13
(`FAST_FAIL_INVALID_SET_OF_CONTEXT`) in `ntdll!RtlRestoreContext`. The resumed
guest RSP was outside the current thread's NT_TIB stack bounds, which
`RunOnGuestStack` deliberately zeros. Guest fibers can also move to a different
stack before any fault occurs on the destination stack.

This is one diagnosed cause of that exit code. Other failures can produce the
same code, including those discussed in
[upstream issue #56](https://github.com/chenxiao07/KytyPS5/issues/56).
This workaround has not been verified on that issue reporter's computer.

## Apply

Use Python 3 on Windows and the **original** v20261017 release, extracted normally.
From the repository root:

```powershell
python -m pip install -r windows-stack-fix-requirements.txt
python apply-windows-stack-fix.py 'D:\KytyPS5\kyty_emulator.exe'
```

The patcher creates `D:\KytyPS5\local-stack-fix-v2\kyty_emulator.exe` and copies
the neighboring runtime DLLs to that new folder. To choose another output folder:

```powershell
python apply-windows-stack-fix.py 'D:\KytyPS5\kyty_emulator.exe' --output-dir 'D:\KytyPS5\stack-fix-v2'
```

Point the upstream runner at the patched copy. Keep **red-zone protection on**
(omit `-NoRedZone`), as in the working local setup:

```powershell
& 'D:\KytyPS5\run-windows.ps1' -Game 'D:\MyGameDump' -Exe 'D:\KytyPS5\local-stack-fix-v2\kyty_emulator.exe' -Set 'KYTY_FPS_HUD=0' -Follow
```

Frame generation settings can be kept separately; the workaround does not
require or supply NVIDIA Streamline files. The local reporting session also used
3x DLSS frame generation (`-FrameGen 2` in this runner) and 1920x1080 rendering.

To undo, point the runner back to the original executable.

## Changes made to the executable

The patcher adds a read/execute `.stkfix` PE section and redirects three entries
using relative jumps. It does not modify Windows DLLs or system settings.

1. Before the original exception filter, a wrapper checks the saved RSP. For
   guest-stack addresses in the release's 8–32 GiB range, it registers stack
   bounds if the RSP is outside the current bounds. `VirtualQuery` must report
   committed memory. The lower bound is `AllocationBase`, and the upper bound
   is the end of the returned region.
2. At `FiberRestoreContext`, another wrapper queries and registers the destination
   stack before switching to it. This prevents native runtime stack probes from
   using a previous fiber's stack limit.
3. A wrapper around the executable's `__chkstk` preserves its original guest-stack
   probe suppression. Native stacks continue to use the original probe routine.

The assembly and PE transformations are contained in `apply-windows-stack-fix.py`.
The input SHA-256 must match before patching. The result SHA-256 must match the
known local revision before anything is written. Different releases, community
builds and previously modified executables are rejected.

| File | SHA-256 |
| --- | --- |
| Original v20261017 EXE | `88f2545f5e261f2a4f085c1a8e487a2f2a94ffe7a3ad02fc098752919e9a0764` |
| Patched revision 2 EXE | `4912aa46d0a89dd07086fe9b4f96ded5e2b72b8eeb84fb0ebeefa9331460bb87` |

## Evidence and limits

The local revision 2 binary reached the menu and gameplay on an Intel Core Ultra
7 265KF / RTX 5070 Ti PC. The player reported that the previously failing route
was working without a crash at that point. Red-zone protection was also enabled
for that run, so the result does not isolate its effect from the stack changes.

An earlier revision without the fiber-switch hook showed both native runtime
stack-probe failures and guest null-pointer faults during gameplay. The current
revision has **not** established that all guest faults are fixed. No long-session
or cross-machine stability claim is made.

The C++ source tree is kept at the upstream release commit; a normal source build
does not yet contain these hooks. This is a reproducible patch of the released
binary, not a completed upstream source integration. The added wrappers also do
not add Windows unwind metadata, which remains a limitation for exceptions that
would unwind through a wrapper. A production source integration should account
for unwind behavior, stack ownership, probing and cleanup across all switch paths.

Diagnosis, assembly wrappers and packaging were prepared with OpenAI Codex.
The human reporting the problem verified menus and brief gameplay on their PC;
they have not claimed a source review or broader validation. This fork is a
record of the experimental local workaround, not an upstream pull request.

Only emulator patch tooling and documentation belong in this repository.
No game content, save data, dumps, private logs or NVIDIA libraries are included.
The repository's GPL version 2 license applies.
