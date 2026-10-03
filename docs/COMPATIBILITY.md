# Compatibility and recovery

## Executable hashes

Only these supplied originals are supported. The installer checks SHA-256, not just a version label.

| Executable | Original SHA-256 | Patched SHA-256 |
| --- | --- | --- |
| Debug | `233584a414e16f624a5531b10e1491896e4b17a074e585364fec7d11c692d763` | `bff0fbed9a5ec1742641812ee963c7b7f17d08c16e83ec2ec2195fe17e956e81` |
| Normal | `9fd625d451ae534cf877b7850c614677f4d2d6209741bf85035e79f081a796d4` | `c2b16440c0de6dbbe326306374379cfa99fdee0ec18d2b3c5b993a8beef24d64` |

Both outputs include the v0.7.2 preview HP tooltip fix. The user reported the previous installer working in normal mode and earlier debug gameplay working. The new fix awaits in-game confirmation. Both remain 32-bit and retain the original Large Address Aware flag.

The three generated SWFs have the same uncompressed content as the tested debug interface files and are shared by both modes. Their compressed hashes can differ because the installer uses Windows' compression implementation. Exact original compressed bytes are backed up and restored.

## Unknown, conflicting or previously patched files

Installation starts only after all five files match the expected original content. A modified UI, different executable build or mixture of original and manually patched files is refused. The installer does not create original backups from patched files.

A complete manual installation matching all five target hashes is recognized, but cannot be uninstalled without original backups. A debug-only manual v0.6.9 install is a mixed state for this five-file package: restore the original debug EXE and three SWFs first. The already-original normal EXE needs no replacement.

If installer 0.7.1 or 0.7.0 created your backups, use **that version** to **Restore Originals**, then move its entire `AoW3ModBackup` folder outside the game directory and keep it. Install 0.7.2 only after that. The new profile deliberately refuses an older or unrelated backup journal.

## Backup layout

`AoW3ModBackup/state.json` records the profile, exact original and installed hashes, and transaction phase. Backups are numbered in manifest order:

| Backup | Original file |
| --- | --- |
| `original-0.bak` | `AoW3_Debug.exe` |
| `original-1.bak` | `HUD_CombatResults.swf` |
| `original-2.bak` | `HUD_FloatingHeroBackground.swf` |
| `original-3.bak` | `HUD_NameChanger.swf` |
| `original-4.bak` | `AoW3.exe` |

These backups never overwrite different existing originals. Staged files and a process lock are also kept in that folder.

After a normal installation failure the installer attempts to restore all originals. After a process or machine interruption, **Restore Originals** can recover a partial install or restore. It validates every backup and every current target before starting. If another mod changed a file, restoration stops; preserve those changed files and the backups before resolving the conflict.

Windows atomic replacement is used on the same volume. Symbolic links and junctions in managed paths are refused. Select the physical game folder and keep the game and launcher closed during installation and restoration.

## Gameplay limits

- The user reported previous debug and normal gameplay working. The v0.7.2 HP tooltip change has instruction-level verification and needs an in-game check in both modes.
- There is no true 64-bit engine conversion or increase to the executable's existing address-space limit.
- Local single-player only; multiplayer/PBEM synchronization is not implemented.
- Content mods can change without a whitelist. UI replacements and other binary patches can conflict.
- Rewards, resurrection, transformations and other effects applied after accepting battle can affect the final state. The preview uses available simulation snapshots.
- Both modes support clicking the unit name. The older cheat-command rename fallback remains debug-only.
- Telemetry changes affect the game's built-in client, not networking in Steam or other applications.
