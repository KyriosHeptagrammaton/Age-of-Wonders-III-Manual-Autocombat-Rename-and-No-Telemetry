param([switch]$RunTests, [switch]$StartInstaller)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$out = Join-Path $root 'dist'
New-Item -ItemType Directory -Force $out | Out-Null
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
if (!(Test-Path $compiler)) { throw 'Windows .NET Framework 4.x C# compiler was not found.' }
$common = @('/nologo', '/codepage:65001', '/optimize+', '/warnaserror+', '/r:System.Web.Extensions.dll', '/r:System.Core.dll')
& $compiler @common '/target:winexe' '/platform:anycpu' "/out:$out\AoW3ModInstaller.exe" `
  '/r:System.Windows.Forms.dll' '/r:System.Drawing.dll' "/resource:$root\patches\patches.json,patches.json" `
  "$root\installer\Core.cs" "$root\installer\Program.cs"
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
if ($RunTests) {
  & $compiler @common '/target:exe' "/out:$out\InstallerTests.exe" "$root\installer\Core.cs" "$root\tests\InstallerTests.cs"
  if ($LASTEXITCODE -ne 0) { throw 'Test compilation failed.' }
  & "$out\InstallerTests.exe" "$root\tests\fixture.json" "$root\patches\patches.json"
  if ($LASTEXITCODE -ne 0) { throw 'Installer tests failed.' }
}
Write-Output "Built $out\AoW3ModInstaller.exe"
if ($StartInstaller) { Start-Process -FilePath "$out\AoW3ModInstaller.exe" }
