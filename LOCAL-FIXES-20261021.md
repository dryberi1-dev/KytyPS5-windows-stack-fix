# Experimental fixes for KytyPS5 v20261021

Base: upstream tag `v20261021`, commit `42ca2d82fbfc619f36c7d8385cc687c7916a081a`.
Game observed: Demon's Souls Remake, PPSA01341, 01.007.000.

These are two source patches for today's release. They do not include the game,
save data, game-derived shader caches, or NVIDIA SDK binaries. There is no
prebuilt emulator binary in this patch release.

## 1. Bounded driver-cache budget override

With a static pipeline store present, the upstream driver-cache load cap is
256 MiB. A local learned cache reached about 259 MiB and was discarded at the
next load. A static store does not necessarily contain every pipeline used by
the game.

`KYTY_DRIVER_CACHE_MIB` accepts an integer from 64 to 2048. The default remains
256 MiB when a static store is present; the existing physical-memory ceiling
and overall 2 GiB cap remain. The emulator logs the effective per-cache limit.
For the reported 32 GiB machine, the local profile uses `512`.

PowerShell example, before launching a locally built emulator:

```powershell
$env:KYTY_DRIVER_CACHE_MIB = '512'
```

This setting is a load-size ceiling per cache, not a RAM-use limiter. Raising
it may retain more cache data in RAM. It does not fix every shader hitch.

## 2. Image reads across released sparse texture layers

The reported exit contained `prt_failure=missing-logical-ownership` in
`BufferCache::ObtainBufferForImage`. A synchronous image upload could span a
released logical layer in a registered PRT aperture. The asynchronous image
path already reads a sparse backing snapshot.

`TryReadImageBacking` first uses the existing dense and strict PRT readers.
Only the `missing-logical-ownership` failure, returned after checking the whole
span lies inside a registered aperture, permits the locked sparse snapshot.
Resident bytes are copied; unmapped bytes become zeros. Other failures keep
the existing diagnostic exit. The strict PRT API is unchanged.

The accompanying regression coverage checks distinct resident patterns on
both sides of a released layer, zero-filled holes, strict ownership rejection,
and rejection outside the aperture. Its targeted invocation is:

```text
virtual_memory_allocation_tests --prt-image-read-only
```

## Applying the source patches

Start with a clean checkout of upstream `v20261021`. Apply both attached files:

```text
git apply 01-driver-cache-budget-v20261021.patch
git apply 02-sparse-image-read-v20261021.patch
```

Build using upstream's instructions and dependencies. The branch accompanying
this release also contains the changed C++ sources and regression coverage.

## Evidence and limits

On the earlier local v20261020b-based build, the C++ build and targeted sparse
image regression passed. A repeated warmup reused a 235,667,272-byte driver
cache: 5,753 recipes took 859 ms, versus 236,458 ms on initial preparation.
Other local cache repairs were also present, so that timing does not isolate
the effect of the cache-budget setting.

For the v20261021 port, the relevant upstream paths were inspected and both
patches applied without conflicts. A v20261021 build, regression rerun, and
in-game reproduction have not been completed for this source release. No FPS,
1% low, RAM reduction, BSOD resolution, or complete crash fix is claimed.

## AI assistance

Implementation, porting, documentation, and the earlier automated checks were
performed with Codex at the repository owner's request. No independent human
source review is claimed.
