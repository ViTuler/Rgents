# Seed a product repository with the Rgents agent team.
#
# Thin wrapper around `.agent/tools/seed_framework.py create`.
# Upgrade an existing product with:
#   python .agent/tools/seed_framework.py upgrade --target <path> --dry-run
#   python .agent/tools/seed_framework.py upgrade --target <path> --yes
#
# Usage:
#   ./.agent/tools/bootstrap-project.ps1 -Target <path-to-new-project> [-WithProductSkeleton]

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    [switch]$WithProductSkeleton
)

$ErrorActionPreference = 'Stop'
$FrameworkRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$SeedPy = Join-Path $PSScriptRoot 'seed_framework.py'
if (-not (Test-Path $SeedPy)) {
    throw "missing seed_framework.py at $SeedPy"
}

$pyArgs = @($SeedPy, 'create', '--target', $Target)
if ($WithProductSkeleton) {
    $pyArgs += '--with-product-skeleton'
}

Write-Output "delegating to seed_framework.py create"
& python @pyArgs
if ($LASTEXITCODE -ne 0) {
    throw "seed_framework.py create failed with exit $LASTEXITCODE"
}
