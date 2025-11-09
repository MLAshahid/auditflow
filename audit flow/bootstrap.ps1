# bootstrap.ps1 — fixed to D:\site_audit
# Creates folders/files, writes base configs, and prints next steps.

$ErrorActionPreference = 'Stop'

# 0) Lock to project root
$ProjectRoot = 'D:\site_audit'
if (-not (Test-Path $ProjectRoot)) {
  New-Item -ItemType Directory -Path $ProjectRoot | Out-Null
}
Set-Location -Path $ProjectRoot

# 1) Folders
$dirs = @('site_audit', 'config', 'tests', 'tests\data')
foreach ($d in $dirs) {
  New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $d) | Out-Null
}

# 2) Empty stubs (you'll paste code later)
$files = @(
  'site_audit\cli.py',
  'site_audit\crawl.py',
  'site_audit\lighthouse_runner.py',
  'site_audit\parse.py',
  'site_audit\severity.py',
  'site_audit\write_out.py',
  'tests\test_parse.py',
  'tests\data\sample_lhr.json',
  'README.md'
)
foreach ($f in $files) {
  New-Item -ItemType File -Force -Path (Join-Path $ProjectRoot $f) | Out-Null
}

# 3) Prefill essentials
@'
pandas
pyyaml
requests
beautifulsoup4
pytest
'@ | Set-Content (Join-Path $ProjectRoot 'requirements.txt') -Encoding UTF8

@'
rules:
  largest-contentful-paint: {crit: ">=4000", med: ">=2500"}   # ms
  cumulative-layout-shift:  {crit: ">=0.25", med: ">=0.10"}
  color-contrast:           {crit: true}
  image-alt:                {med: true}
  meta-description:         {med: true}
  document-title:           {med: true}
defaults: low
'@ | Set-Content (Join-Path $ProjectRoot 'config\rules.yaml') -Encoding UTF8

@'
__all__ = []
'@ | Set-Content (Join-Path $ProjectRoot 'site_audit\__init__.py') -Encoding UTF8

# 4) Status + quick checks
Write-Host "Scaffold ready at $ProjectRoot" -ForegroundColor Green
Write-Host "Next steps (run in this shell):"
Write-Host "  1) python -m venv .venv"
Write-Host "  2) .\.venv\Scripts\Activate.ps1"
Write-Host "     (If blocked: Set-ExecutionPolicy -Scope Process RemoteSigned)"
Write-Host "  3) pip install -r requirements.txt"
Write-Host "  4) npm i -g lighthouse   (requires Node.js LTS)"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Warning "Python not found on PATH."
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Warning "Node.js not found. Install Node LTS (winget install OpenJS.NodeJS.LTS), then reopen PowerShell."
}
if (-not (Get-Command lighthouse -ErrorAction SilentlyContinue)) {
  Write-Warning "Lighthouse CLI not found. After installing Node, run: npm i -g lighthouse"
}
