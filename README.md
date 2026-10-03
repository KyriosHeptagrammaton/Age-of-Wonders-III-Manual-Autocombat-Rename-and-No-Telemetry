# Age of Wonders III: manual autocombat, unit renaming and no telemetry

A Windows installer that patches your own Age of Wonders III files and keeps exact original backups for restoration. The public package contains patch data and authored source, without complete game executables or interface assets.

**Version 0.7.2 fixes preview HP tooltips in both normal and debug modes.** The preview health bar already used the battle result, but its hover tooltip could retain pre-battle HP. Both now use the same result values. The user reported v0.7.1 working in normal mode; this new tooltip fix passes instruction-level tests and awaits an in-game check. This is not a 64-bit conversion.

## Download and install

Extract **AoW3-Mod-Installer-v0.7.2-Source.zip** and double-click **Install.cmd**. It compiles the installer with Windows' built-in .NET tools, runs its transaction checks, then opens it. Version 0.7.2 has not been compiled or run on Windows in the development environment; the launcher stops before touching the game if compilation or tests fail.

After the repository's Windows workflow succeeds, a compiled ZIP can be downloaded from [Releases](https://github.com/KyriosHeptagrammaton/Age-of-Wonders-III-Manual-Autocombat-Rename-and-No-Telemetry/releases). Run **AoW3ModInstaller.exe** from that ZIP directly.

1. Close the game and launcher. Select the game folder containing both `AoW3.exe` and `AoW3_Debug.exe`.
2. Click **Check Files**, then **Install Mod**. If Windows denies write access, run the installer as administrator.
3. Launch normally or enable **Run in Debug Mode** in the game launcher. The installer patches both executables together.

Windows 10/11 with .NET Framework 4.8 is the intended installer environment. Players do not need Python, Java, a separate compiler download or an internet connection. The installer is unsigned.

Keep **AoW3ModBackup** inside the game folder. To uninstall, close the game, run this same installer, select the same folder and choose **Restore Originals**. Original backups remain afterwards. Use Restore Originals to recover an interrupted installation before trying again.

**Updating from installer 0.7.1 or 0.7.0:** use your currently installed version's installer to **Restore Originals** first. Then move its entire `AoW3ModBackup` folder outside the game folder and keep it. Run the 0.7.2 installer only after those steps. Each version has a different patch profile and cannot reuse an older backup journal.

**Updating from a manual v0.6.9 install:** restore your original debug executable and three interface files first; keep the original normal executable in place. This installer requires all five supported originals before it can create trustworthy backups.

## Features

- **Preview autocombat:** the ordinary results panel shows both armies, including casualties, health, rank and available simulation snapshots. The health bar and hover HP numbers use the same result. It plays the normal completion sound.
- **Fight Manually** on the left discards the simulated outcome and enters battle with the original setup and seed. There is no autocombat reroll.
- **Accept Result** on the right applies the outcome once and skips the duplicate report window. The report remains in the event history. Enter, Esc or closing the pending results window also accepts it.
- **Click a unit's name to rename it:** the city-style dialog opens with the name selected and the caret at the end. Enter or OK saves; Cancel leaves it unchanged. Names survive saving and loading in the tested debug build.
- **Built-in game telemetry disabled:** initialization and event submission are disabled in both executable patches. This does not control Steam or other separate software.

Renaming is available for your own live units on the strategic map during your active turn. It can change their sorting within an army. These features are for local single-player; multiplayer/PBEM synchronization is not implemented. Both modes use the same authored behavior and shared interface changes.

## Mods and supported files

There is no fixed mod list or unit whitelist. Changing content mods does not require rebuilding this installer. A mod that changes the same executable locations or interface files needs a compatible merge.

| File | Support |
| --- | --- |
| `AoW3_Debug.exe` | Exact supplied original debug build 28623 |
| `Content/Title/Interface/HUD_CombatResults.swf` | Supplied original interface build |
| `Content/Title/Interface/HUD_FloatingHeroBackground.swf` | Supplied original interface build |
| `Content/Title/Interface/HUD_NameChanger.swf` | Supplied original interface build |
| `AoW3.exe` | Exact supplied original normal executable |

All original and generated files are verified before any game file is replaced. Unknown builds are refused even if their version labels match. Different stores or editions may have different binaries. SWFs are compared after decompression, allowing equivalent compression without accepting changed interface content. Exact executable hashes are in [compatibility and recovery](docs/COMPATIBILITY.md).

Restoration verifies every backup and refuses to overwrite files changed since installation. Preserve your backups when resolving a conflict.

## Source and validation

The five patch reconstructions were checked against the supplied originals and intended outputs. Both executables include the new tooltip hook; the interface files are unchanged. Debug instruction tests: 74 passed, one historical comparison skipped. Normal instruction tests: 18 passed. The new regression checks reproduce stale HP in 0.7.1 and verify the fix, result/bar agreement, deaths, health bounds, unrelated tooltips and unchanged unit data at three load addresses. Emulation does not run the whole game.

Windows execution of this update and in-game confirmation of the tooltip fix remain pending. Synthetic transaction tests are required by both `Install.cmd` and the Windows workflow. See [validation](docs/VALIDATION.md), [build instructions](docs/BUILDING.md), and [publishing instructions](docs/PUBLISHING.md).
