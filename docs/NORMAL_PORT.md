# Normal executable port

Version 0.7.1 added a separate runtime for the exact normal executable listed in COMPATIBILITY.md. The user subsequently reported it working. Version 0.7.2 corrects pre-battle HP remaining in preview hover tooltips in both modes. The normal runtime reuses the debug version's authored combat/rename logic and shared SWF changes. It does not substitute the debug executable for normal mode.

## Engine differences

The normal build has different object layouts, custom register calling conventions and inline constructors. `native/normal/src/profile.json` records the checked engine RVAs and original hook bytes. `engine.S` adapts the normal calling conventions; `engine.h` constructs the UI command objects; `hooks.S` preserves surrounding native state and replays displaced instructions.

The builder checks the original SHA-256, expected bytes at every hook, section/header space and relocation overlap. Payload references are position independent. Code and writable state use separate PE sections. No entry-point or license-check bypass is made.

Preview keeps the simulation pending until a choice. Accept commits once; manual discards the simulation and changes the existing battle setup to manual without generating a new seed. The original completion notification provides the sound. The report hook changes only the matched participant report's automatic-open flag while committing accepted preview results, preserving event history.

Unit names use the native persistent name fields and are resolved again by unit identity when submitted. The normal build supports clicking the unit name, including selected text and caret placement. The legacy cheat-command fallback remains debug-only.

## Verification and boundaries

The normal suite currently passes 18 groups. It executes the patched normal PE, native close-autocombat cleanup, state transitions, string assignment and UI serialization. It checks alternate load bases, choices/timeout/fallback, no second autocombat, participant/single-player guards, both UI button paths, report scoping, result routing, HP/rank/conversion/XP serialization, name entry/exit, invalid rename contexts, stable unit identity and telemetry stack cleanup.

The tooltip's native formatter reads live pre-battle UnitData. The new hook replaces only its current/max HP arguments while the pending preview is being populated, using the same result lookup and health bounds as the bar. All other tooltip formatting still uses the live unit and its valid resource context. It never passes a detached result snapshot to the full formatter or mutates unit/result data. Normal hook RVA: `0x4c6774`; debug hook RVA: `0x60ce77`.

New regression checks fail against released 0.7.1, then pass against 0.7.2. They compare the actual HP arguments entering the native string formatter with bar values for survivors, ordinary deaths, resurrection candidates and bounded/fallback HP. They also check inactive/unrelated tooltips, preserved native registers/flags and unchanged unit/snapshot memory at three image bases.

Windows APIs, rendering/resource calls and the campaign's final result-application service are mocked. Consequently these checks cannot establish that the game launches successfully, that the full renderer displays everything correctly, or that all post-battle effects match in a live campaign.

## In-game check for this update

Use a backed-up save and the supported original game files. Install the package, leave Run in Debug Mode off, and check:

1. The game starts and loads the save with the usual content mods.
2. Clicking an owned unit's name opens the dialog; typing replaces the selected name; Cancel, OK and save/reload behave correctly.
3. Autocombat shows both armies, health/casualty/rank information and the completion sound. Hover units that took damage: current/max HP must agree with their preview bar. Check both armies and casualties, then check ordinary unit tooltips outside the preview.
4. Accept applies once, leaves history accessible and avoids a duplicate popup; compare preview XP with final XP.
5. Fight Manually enters the same encounter with pre-battle armies. No new autocombat option appears.
6. A battle fought manually from the start retains its ordinary results/report behavior.
7. Restore Originals returns the original hashes for both EXEs and the exact original SWF bytes.

Debug mode should then be checked with the same installation. Report which launch mode was used and preserve any crash/error logs.
