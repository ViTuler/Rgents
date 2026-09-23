# Initialize local git for an Rgents project (no remote). See init_project.py.
param(
    [string]$Target = "",
    [switch]$EnsureBaseline
)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$argsList = @()
if ($Target) { $argsList += @('--target', $Target) }
if ($EnsureBaseline) { $argsList += '--ensure-baseline' }
& python (Join-Path $scriptDir 'init_project.py') @argsList
exit $LASTEXITCODE
