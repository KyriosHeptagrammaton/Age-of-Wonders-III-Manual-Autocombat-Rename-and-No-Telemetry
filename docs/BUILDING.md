# Build and test

## Windows installer

On Windows with .NET Framework 4.8, double-click `Build.cmd`, or run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Build-Installer.ps1 -RunTests
```

The execution-policy option applies only to that process. The script compiles local C# source with the Framework compiler, runs synthetic transaction tests and writes `dist/AoW3ModInstaller.exe`. Patch data is embedded, making the resulting installer a single executable. No game data is downloaded. `Install.cmd` also starts the installer after those checks.

The GitHub Actions workflow runs on Windows, uploads a ZIP and publishes a prerelease after tests pass. Its token is limited to repository contents. Existing releases are not overwritten by later pushes with the same version.

## Patch data

`patches/patches.json` is a format-1 copy/insert manifest. Every entry records a relative path, encoding, original/target SHA-256, lengths and copy/insert operations. Raw EXEs are patched directly. CWS SWFs are decompressed to canonical FWS, patched, verified and recompressed with zlib framing.

To regenerate the data locally, provide your five original files and a modified game directory containing both patched executables and the three modified SWFs:

```sh
python3 tools/build_patches.py /path/to/originals /path/to/modified/game patches/patches.json
```

The originals directory can use game paths or contain the five files in one flat directory. Source hashes and all reconstructed outputs are checked. Do not commit original or patched game files, personal logs, backups or saved games.

`tests/make_fixture.py` generates the small game-free C# fixture using Python's zlib. It exercises both executable targets and the three compressed interface targets.

## Native hook sources

Use Linux/WSL with Python 3.8+, GCC supporting 32-bit code generation and GNU binutils. Each builder verifies its own exact input hash and refuses to overwrite an existing output.

```sh
# Debug runtime: v0.7.2 tooltip fix
python3 native/src/build.py /path/to/original/AoW3_Debug.exe native/game
# Separate normal runtime: v0.7.2 tooltip fix
python3 native/normal/src/build.py /path/to/original/AoW3.exe native/normal/game
```

Both remain 32-bit. `--telemetry-default` produces a diagnostic variant retaining original telemetry; the installer uses the telemetry-disabled variants.

The UI is distributed as deltas. Full decompiled game interface sources are not included. Rebuilding an EXE does not regenerate the UI.

For the instruction tests, install `unicorn==2.1.4`. Build the outputs into the directories above; also build the debug `--telemetry-default` variant into `native/telemetry-default/`. Then run:

```sh
python3 -m unittest discover -s native/src -p 'test_*.py' -v
python3 -m unittest discover -s native/normal/src -p 'test_normal.py' -v
```

Some debug tests need the original investigation's uploads or historical checkpoints and skip if absent. The normal suite loads the built normal EXE and mocks Windows/graphics/resource boundaries. Neither suite runs a campaign or replaces an in-game test. See [normal port notes](NORMAL_PORT.md).
