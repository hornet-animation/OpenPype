<#
.SYNOPSIS
  Helper script create virtual environment using Poetry.

.DESCRIPTION
  This script will detect Python installation, create venv with Poetry
  and install all necessary packages from `poetry.lock` or `pyproject.toml`
  needed by OpenPype to be included during application freeze on Windows.

.EXAMPLE

PS> .\create_env.ps1

.EXAMPLE

Print verbose information from Poetry:
PS> .\create_env.ps1 --verbose

#>

$arguments=$ARGS
$poetry_verbosity=""
if($arguments -eq "--verbose") {
    $poetry_verbosity="-vvv"
}

$current_dir = Get-Location
$script_dir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$openpype_root = (Get-Item $script_dir).parent.FullName

# Install PSWriteColor to support colorized output to terminal
$env:PSModulePath = $env:PSModulePath + ";$($openpype_root)\vendor\powershell"

function Exit-WithCode($exitcode) {
   # Only exit this host process if it's a child of another PowerShell parent process...
   $parentPID = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$PID" | Select-Object -Property ParentProcessId).ParentProcessId
   $parentProcName = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$parentPID" | Select-Object -Property Name).Name
   if ('powershell.exe' -eq $parentProcName) { $host.SetShouldExit($exitcode) }

   exit $exitcode
}


function Show-PSWarning() {
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        Write-Color -Text "!!! ", "You are using old version of PowerShell - ",  "$($PSVersionTable.PSVersion.Major).$($PSVersionTable.PSVersion.Minor)" -Color Red, Yellow, White
        Write-Color -Text "    Please update to at least 7.0 - ", "https://github.com/PowerShell/PowerShell/releases" -Color Yellow, White
        Exit-WithCode 1
    }
}


function Install-Poetry() {
    Write-Color -Text ">>> ", "Installing Poetry ... " -Color Green, Gray
    $env:POETRY_HOME="$openpype_root\.poetry"
    (Invoke-WebRequest -Uri https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py -UseBasicParsing).Content | python -
}


function Test-Python() {
    Write-Color -Text ">>> ", "Detecting host Python ... " -Color Green, Gray -NoNewline
    if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
        Write-Color -Text "!!! ",  "Python not detected" -Color Red, Yellow
        Set-Location -Path $current_dir
        Exit-WithCode 1
    }
    $version_command = @'
import sys
print('{0}.{1}'.format(sys.version_info[0], sys.version_info[1]))
'@

    $p = & python -c $version_command
    $env:PYTHON_VERSION = $p
    $m = $p -match '(\d+)\.(\d+)'
    if(-not $m) {
        Write-Color -Text "FAILED " -Color Red
        Write-Color -Text "!!! ", "Cannot determine version" -Color Red, Yellow
        Set-Location -Path $current_dir
        Exit-WithCode 1
    }
    # We are supporting python 3.7 only
    if (($matches[1] -lt 3) -or ($matches[2] -lt 7)) {
      Write-Color -Text "FAILED ", "Version ", "[", $p ,"]",  "is old and unsupported" -Color Red, Yellow, Cyan, White, Cyan, Yellow
      Set-Location -Path $current_dir
      Exit-WithCode 1
    } elseif (($matches[1] -eq 3) -and ($matches[2] -gt 7)) {
        Write-Color -Text "WARNING Version ", "[",  $p, "]",  " is unsupported, use at your own risk." -Color Yellow, Cyan, White, Cyan, Yellow
        Write-Color -Text "*** ", "OpenPype supports only Python 3.7" -Color Yellow, White
    } else {
        Write-Color "OK ", "[",  $p, "]" -Color Green, Cyan, White, Cyan
    }
}

if (-not (Test-Path 'env:POETRY_HOME')) {
    $env:POETRY_HOME = "$openpype_root\.poetry"
}


Set-Location -Path $openpype_root

$art = @"


             . .   ..     .    ..
        _oOOP3OPP3Op_. .
     .PPpo~.   ..   ~2p.  ..  ....  .  .
    .Ppo . .pPO3Op.. . O:. . . .
   .3Pp . oP3'. 'P33. . 4 ..   .  .   . .. .  .  .
  .~OP    3PO.  .Op3    : . ..  _____  _____  _____
  .P3O  . oP3oP3O3P' . . .   . /    /./    /./    /
   O3:.   O3p~ .       .:. . ./____/./____/ /____/
   'P .   3p3.  oP3~. ..P:. .  . ..  .   . .. .  .  .
  . ':  . Po'  .Opo'. .3O. .  o[ by Pype Club ]]]==- - - .  .
    . '_ ..  .    . _OP3..  .  .https://openpype.io.. .
         ~P3.OPPPO3OP~ . ..  .
           .  ' '. .  .. . . . ..  .


"@
if (-not (Test-Path 'env:_INSIDE_OPENPYPE_TOOL')) {
    Write-Host $art -ForegroundColor DarkGreen
}

# Enable if PS 7.x is needed.
# Show-PSWarning

$version_file = Get-Content -Path "$($openpype_root)\openpype\version.py"
$result = [regex]::Matches($version_file, '__version__ = "(?<version>\d+\.\d+.\d+.*)"')
$openpype_version = $result[0].Groups['version'].Value
if (-not $openpype_version) {
  Write-Color -Text "!!! ", "Cannot determine OpenPype version." -Color Red, Yellow
  Set-Location -Path $current_dir
  Exit-WithCode 1
}
Write-Color -Text ">>> ", "Found OpenPype version ", "[ ", $($openpype_version), " ]" -Color Green, Gray, Cyan, White, Cyan

Test-Python

Write-Color -Text ">>> ", "Reading Poetry ... " -Color Green, Gray -NoNewline
if (-not (Test-Path -PathType Container -Path "$($env:POETRY_HOME)\bin")) {
    Write-Color -Text "NOT FOUND" -Color Yellow
    Install-Poetry
    Write-Color -Text "INSTALLED" -Color Cyan
} else {
    Write-Color -Text "OK" -Color Green
}

if (-not (Test-Path -PathType Leaf -Path "$($openpype_root)\poetry.lock")) {
    Write-Color -Text ">>> ", "Installing virtual environment and creating lock." -Color Green, Gray
} else {
    Write-Color -Text ">>> ", "Installing virtual environment from lock." -Color Green, Gray
}
& "$env:POETRY_HOME\bin\poetry" install --no-root $poetry_verbosity --ansi
if ($LASTEXITCODE -ne 0) {
    Write-Color -Text "!!! ", "Poetry command failed." -Color Red, Yellow
    Set-Location -Path $current_dir
    Exit-WithCode 1
}
Set-Location -Path $current_dir

New-BurntToastNotification -AppLogo "$openpype_root/openpype/resources/icons/openpype_icon.png" -Text "OpenPype", "Virtual environment created."

Write-Color -Text ">>> ", "Virtual environment created." -Color Green, White
