# Seed a product repository with the Rgents agent team.
#
# Scope: the FRAMEWORK half of a bootstrap. Copies the governance surfaces, scaffolds the
# knowledge files from `.agent/templates/knowledge/`, and creates empty task lanes. It
# deliberately does NOT write product code: the stack, layer layout and dependencies are a
# product decision, not a framework one. A product skeleton is optional and lives separately
# (see `.agent/tools/bootstrap-product-skeleton.ps1`).
#
# Why the templates are copied from the framework rather than left as they are: this repository
# IS the framework, and it accumulates its own facts as it is used. Copying `docs/knowledge/`
# wholesale ships those facts into the new project. That mistake was made twice -- framework
# known issues landing in a product repository, then one product's known issues landing in the
# framework's template slot -- which is why the scaffolding step exists.
#
# Deliberately does NOT create the first commit or add a remote. Local `git init` is performed
# via `.agent/tools/init_project.py` at the end of this script (C7). The human still owns the
# first commit and any remote.
#
# Usage:
#   ./.agent/tools/bootstrap-project.ps1 -Target <path-to-new-project> [-WithProductSkeleton]
#
# The framework root is derived from this script's own location, so it works from any cwd and
# carries no machine-specific path.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    # Also run the optional product skeleton seeder. Off by default: a product's stack is a
    # product decision, and seeding one implies a choice the framework should not make silently.
    [switch]$WithProductSkeleton
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$FrameworkRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

if (Test-Path $Target) {
    $existing = Get-ChildItem -Force $Target -ErrorAction SilentlyContinue
    if ($existing) {
        throw "target exists and is not empty: $Target. Refusing to seed into a directory with content."
    }
} else {
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
}
$Target = (Resolve-Path $Target).Path
Write-Output "framework root : $FrameworkRoot"
Write-Output "target         : $Target"

# Surfaces adopted from the framework, and the reasoning for each exclusion.
$FrameworkSurfaces = @(
    'AGENTS.md',
    '.cursor',
    '.agent',
    'docs/agents',
    'docs/knowledge',
    'docs/architecture'
)
# Not copied, and why:
#   refers/                     reference reading for the framework's authors, inert at runtime
#   README.md                   the product repository writes its own
#   tasks/**                    the previous project's task history
#   .agent/tools/bootstrap-*.ps1  framework provisioning tools; they act ON a project, they do not
#                               belong IN one, and once seeded the target has no use for them

Write-Output ''
Write-Output '== 1. framework surfaces'
foreach ($surface in $FrameworkSurfaces) {
    $from = Join-Path $FrameworkRoot $surface
    if (-not (Test-Path $from)) { throw "framework source missing: $from" }
    $to = Join-Path $Target $surface
    $toDir = Split-Path -Parent $to
    if ($toDir -and -not (Test-Path $toDir)) { New-Item -ItemType Directory -Force -Path $toDir | Out-Null }
    Copy-Item -Recurse -Force -Path $from -Destination $to -Exclude '__pycache__'
    Write-Output "  copied $surface"
}

foreach ($lane in @('active', 'completed', 'archive')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Target "tasks/$lane") | Out-Null
}
Write-Output '  created empty tasks/{active,completed,archive}'

# The provisioning tools must not survive in the product repository.
$seededTools = Join-Path $Target '.agent\tools'
foreach ($name in @('bootstrap-project.ps1', 'bootstrap-product-skeleton.ps1')) {
    $path = Join-Path $seededTools $name
    if (Test-Path $path) { Remove-Item $path -Force; Write-Output "  removed .agent/tools/$name from the target" }
}

Write-Output ''
Write-Output '== 2. knowledge files scaffolded from the framework templates'
$TemplateDir = Join-Path $FrameworkRoot '.agent\templates\knowledge'
foreach ($pair in @(
    @{ tpl = 'known-issues.md';   dst = 'docs\knowledge\known-issues.md' },
    @{ tpl = 'project-memory.md'; dst = 'docs\knowledge\project-memory.md' }
)) {
    $src = Join-Path $TemplateDir $pair.tpl
    $dst = Join-Path $Target $pair.dst
    if (-not (Test-Path $src)) {
        throw "framework template missing: $src. Without it the target would inherit whatever facts this repository happens to be carrying."
    }
    Copy-Item $src $dst -Force
    Write-Output "  $($pair.dst)"
}

# The framework's own project-baseline.yaml is framework_meta. A product must start from the
# empty template, not inherit the framework's stack.
$BaselineTpl = Join-Path $FrameworkRoot '.agent\templates\project-baseline.yaml'
$BaselineDst = Join-Path $Target '.agent\project-baseline.yaml'
if (-not (Test-Path $BaselineTpl)) {
    throw "framework template missing: $BaselineTpl"
}
Copy-Item $BaselineTpl $BaselineDst -Force
Write-Output '  .agent/project-baseline.yaml (from template; status: template)'

if ($WithProductSkeleton) {
    Write-Output ''
    Write-Output '== 3. optional product skeleton'
    $skeleton = Join-Path $FrameworkRoot '.agent\tools\bootstrap-product-skeleton.ps1'
    if (Test-Path $skeleton) {
        & $skeleton -Target $Target
    } else {
        Write-Output '  skipped: .agent/tools/bootstrap-product-skeleton.ps1 not present'
    }
} else {
    Write-Output ''
    Write-Output '== 3. product skeleton skipped (pass -WithProductSkeleton to seed one) =='
}

Write-Output ''
Write-Output '== 4. local git init (no remote) =='
$InitPy = Join-Path $FrameworkRoot '.agent\tools\init_project.py'
if (Test-Path $InitPy) {
    & python $InitPy --target $Target
} else {
    Write-Output '  skipped: init_project.py not present; run it from the seeded project later'
}

Write-Output ''
Write-Output '== done =='
Write-Output 'Next, and not done by this script:'
Write-Output '  1. Create the first commit yourself when ready (init does not commit).'
Write-Output '  2. Project-level spec/design: human + product + tech-lead fill'
Write-Output '     .agent/project-baseline.yaml and set status: established.'
Write-Output '     docs/knowledge/project-memory.md may summarise it; it is not the source of truth.'
Write-Output '  3. Confirm the environment against that baseline, then run:'
Write-Output '     python .agent/tools/validate.py --check-setup'
Write-Output '     python .agent/tools/validate.py --selftest'
