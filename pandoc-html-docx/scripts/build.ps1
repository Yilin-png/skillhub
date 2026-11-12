# Markdown → DOCX (Windows helper). 额外参数原样传给 build.py / pandoc。
param(
  [Parameter(Mandatory = $true)][string]$Source,
  [string]$Output = "",
  [switch]$NoHtml,
  [switch]$NoToc,
  [switch]$NoCoverCenter,
  [switch]$Force,
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$py = Join-Path $PSScriptRoot "build.py"
$argv = @($Source)
if ($Output) { $argv += @("-o", $Output) }
if ($NoHtml) { $argv += "--no-html" }
if ($NoToc) { $argv += "--no-toc" }
if ($NoCoverCenter) { $argv += "--no-cover-center" }
if ($Force) { $argv += "--force" }
if ($Rest) { $argv += $Rest }
$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
& $python $py @argv
exit $LASTEXITCODE
