<#
.SYNOPSIS
  Helper script to Pype Settings UI

.DESCRIPTION
  This script will run Pype and open Settings UI.

.EXAMPLE

PS> .\run_settings.ps1

#>

$script_dir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$pype_root = (Get-Item $script_dir).parent.FullName

& poetry run python "$($pype_root)\start.py" settings --dev
