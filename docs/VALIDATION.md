# Validation at source-package preparation

Date: 2026-10-03. Installer package and both runtimes: 0.7.2. This update addresses the user's report that normal-mode preview bars appeared correct while hover tooltips retained pre-battle HP.

## Completed locally

- Reconstructed all five targets from the supplied originals and the public copy/insert manifest.
- Compared both reconstructed EXEs byte-for-byte with their intended builds; compared every reconstructed SWF's entire uncompressed content with the working debug interface files.
- Rebuilt both EXEs using the native source included in this package. Outputs exactly match the SHA-256 values in COMPATIBILITY.md.
- Ran the debug instruction suite: **74 passed, 1 historical comparison skipped** (75 total).
- Ran the normal instruction suite: **18 passed**. It covers original and relocated load addresses, preview/accept/manual paths, no second autocombat, timeout/fallback, guards, report scoping, native state transitions and serialization, result snapshots, rename entry/submission/exit and telemetry calling conventions.
- Reproduced the HP tooltip mismatch against the released 0.7.1 EXEs in both modes: all 18 damaged/dead/bounded-health cases per mode retained live HP instead of matching the result bar. The same checks pass with 0.7.2.
- Executed both actual patched tooltip instruction paths to the native string-formatting call and compared its HP arguments with the bar's serialized result. Cases include survivors, ordinary dead-unit IDs, resurrection candidates, negative/excess HP and max-HP fallback at three load addresses. Checked ordinary/unmatched/detached-unit guards, preserved native registers/flags and unchanged live-unit/result memory.
- Verified all source ranges, relative manifest paths, hashes and lengths. Checked five game-free synthetic fixtures, Python syntax and workflow YAML syntax.
- Checked that the public source package excludes complete game EXEs, SWFs, BPLs, decompiled interface dumps, personal logs and saves.
- The user confirmed earlier debug gameplay and reported the 0.7.1 installer working in normal mode. The three shared interface files remain unchanged in this update. Both EXEs change to include the tooltip fix.

## Pending Windows execution

The development environment has no Windows or .NET Framework runtime/compiler. The GitHub integration rejected the attempted repository upload with HTTP 403, so its Windows workflow could not run. No precompiled installer is included.

`Install.cmd` compiles the installer and requires its C# tests to pass before opening the UI. Those tests cover Python/.NET SWF compression, both executable targets, installation, exact uninstall, reinstall, repeated installation, an unsupported normal EXE, injected write failures including the fifth file, interruption recovery, changed files, corrupt backups, manual/mixed installations, concurrency, paths, checksums and target hashes.

The C# tests have been written but **not executed here**. The user reported the previous installer working. Version 0.7.2 retains its transaction implementation, with updated patch data, expected output hashes and explanatory text. Its Windows compilation and installation/restoration remain unverified here. The GitHub workflow requires these tests before publishing a compiled prerelease.

## Pending in-game confirmation

Normal mode is a separate port of the authored hooks, not a relabeled debug executable. Instruction emulation is limited to selected native paths with platform/resource boundaries and final campaign result application mocked. It does not run the complete renderer or campaign.

Use the in-game checks in NORMAL_PORT.md. In particular, hover damaged and dead units in both armies and compare current/max HP with the preview bars, then check ordinary tooltips outside the preview. Test both launch modes. Version 0.7.2's new tooltip hook has not yet been tested in a live game. Post-acceptance campaign effects remain governed by the existing game behavior.

Other executable hashes and store builds are unsupported. No 64-bit conversion is included.
