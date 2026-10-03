# Publish to the repository

The source package is ready for:

https://github.com/KyriosHeptagrammaton/Age-of-Wonders-III-Manual-Autocombat-Rename-and-No-Telemetry

The connected GitHub integration returned HTTP 403, `Resource not accessible by integration`, when creating the first README. No files were uploaded. The repository owner's write permission does not automatically grant the integration write permission.

## Upload using GitHub

1. Extract the source ZIP. Open the repository and choose **uploading an existing file** (or **Add file → Upload files**).
2. Upload the extracted contents, preserving folders, including `.github/workflows/build.yml`. Do not upload just the ZIP as the repository contents. Do not add your game files, personal logs, saves, or `AoW3ModBackup`.
3. Commit to `main`. Open the **Actions** tab and check **Build and test Windows installer**.
4. If the build succeeds, download the generated installer ZIP from the workflow artifact or the **v0.7.2 — Normal and debug installer** prerelease.

If using Git, run these in the extracted source folder with your own Git identity configured:

```sh
git init -b main
git add .
git commit -m "Add normal and debug community patch installer"
git remote add origin https://github.com/KyriosHeptagrammaton/Age-of-Wonders-III-Manual-Autocombat-Rename-and-No-Telemetry.git
git push -u origin main
```

The workflow compiles the installer and executes synthetic installation, restoration, corruption, lock and rollback tests before packaging. It requests repository contents-write permission only to create the release. Repository policies may prevent release publication; the artifact is uploaded first and remains available when that happens.

This update has not yet been tested on Windows. After automated checks pass, test an installation and restoration on a copied supported game folder, then confirm preview hover HP in both modes. All five patch reconstructions were checked locally. The user reported v0.7.1 working in normal mode; both new executable outputs include the tooltip fix and require an in-game check.

To let the assistant upload later, reconnect or adjust the GitHub integration's repository permissions to allow content writes and workflow-file updates for this repository. Do not send account tokens in chat.

## Release status

Keep 0.7.2 marked as a prerelease until installation/restoration and preview tooltip HP have been checked in both modes. The workflow's synthetic checks do not validate gameplay. Existing installer users must restore with their old installer, then preserve its backup folder outside the game folder before installing this version. See VALIDATION.md and NORMAL_PORT.md for the remaining checks.
