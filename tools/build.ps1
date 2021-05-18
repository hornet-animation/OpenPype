<#
.SYNOPSIS
  Helper script to build OpenPype.

.DESCRIPTION
  This script will detect Python installation, and build OpenPype to `build`
  directory using existing virtual environment created by Poetry (or
  by running `/tools/create_venv.ps1`). It will then shuffle dependencies in
  build folder to optimize for different Python versions (2/3) in Python host.

.EXAMPLE

PS> .\build.ps1

#>

function Start-Progress {
    param([ScriptBlock]$code)
    $scroll = "/-\|/-\|"
    $idx = 0
    $job = Invoke-Command -ComputerName $env:ComputerName -ScriptBlock { $code } -AsJob

    $origpos = $host.UI.RawUI.CursorPosition

    # $origpos.Y -= 1

    while (($job.State -eq "Running") -and ($job.State -ne "NotStarted"))
    {
        $host.UI.RawUI.CursorPosition = $origpos
        Write-Host $scroll[$idx] -NoNewline
        $idx++
        if ($idx -ge $scroll.Length)
        {
            $idx = 0
        }
        Start-Sleep -Milliseconds 100
    }
    # It's over - clear the activity indicator.
    $host.UI.RawUI.CursorPosition = $origpos
    Write-Host ' '
  <#
  .SYNOPSIS
  Display spinner for running job
  .PARAMETER code
  Job to display spinner for
  #>
}


function Exit-WithCode($exitcode) {
   # Only exit this host process if it's a child of another PowerShell parent process...
   $parentPID = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$PID" | Select-Object -Property ParentProcessId).ParentProcessId
   $parentProcName = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$parentPID" | Select-Object -Property Name).Name
   if ('powershell.exe' -eq $parentProcName) { $host.SetShouldExit($exitcode) }

   exit $exitcode
}

function Show-PSWarning() {
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        Write-Host "!!! " -NoNewline -ForegroundColor Red
        Write-Host "You are using old version of PowerShell. $($PSVersionTable.PSVersion.Major).$($PSVersionTable.PSVersion.Minor)"
        Write-Host "Please update to at least 7.0 - " -NoNewline -ForegroundColor Gray
        Write-Host "https://github.com/PowerShell/PowerShell/releases" -ForegroundColor White
        Exit-WithCode 1
    }
}

function Install-Poetry() {
    Write-Host ">>> " -NoNewline -ForegroundColor Green
    Write-Host "Installing Poetry ... "
    (Invoke-WebRequest -Uri https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py -UseBasicParsing).Content | python -
}

$art = @"

             . .   ..     .    ..
        _oOOP3OPP3Op_. .
     .PPpo~·   ··   ~2p.  ··  ····  ·  ·
    ·Ppo · .pPO3Op.· · O:· · · ·
   .3Pp · oP3'· 'P33· · 4 ··   ·  ·   · ·· ·  ·  ·
  ·~OP    3PO·  .Op3    : · ··  _____  _____  _____
  ·P3O  · oP3oP3O3P' · · ·   · /    /·/    /·/    /
   O3:·   O3p~ ·       ·:· · ·/____/·/____/ /____/
   'P ·   3p3·  oP3~· ·.P:· ·  · ··  ·   · ·· ·  ·  ·
  · ':  · Po'  ·Opo'· .3O· .  o[ by Pype Club ]]]==- - - ·  ·
    · '_ ..  ·    . _OP3··  ·  ·https://openpype.io·· ·
         ~P3·OPPPO3OP~ · ··  ·
           ·  ' '· ·  ·· · · · ··  ·

"@

Write-Host $art -ForegroundColor DarkGreen

# Enable if PS 7.x is needed.
# Show-PSWarning

$current_dir = Get-Location
$script_dir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$openpype_root = (Get-Item $script_dir).parent.FullName

$env:_INSIDE_OPENPYPE_TOOL = "1"

# make sure Poetry is in PATH
if (-not (Test-Path 'env:POETRY_HOME')) {
    $env:POETRY_HOME = "$openpype_root\.poetry"
}
$env:PATH = "$($env:PATH);$($env:POETRY_HOME)\bin"

Set-Location -Path $openpype_root

$version_file = Get-Content -Path "$($openpype_root)\openpype\version.py"
$result = [regex]::Matches($version_file, '__version__ = "(?<version>\d+\.\d+.\d+.*)"')
$openpype_version = $result[0].Groups['version'].Value
if (-not $openpype_version) {
  Write-Host "!!! " -ForegroundColor yellow -NoNewline
  Write-Host "Cannot determine OpenPype version."
  Exit-WithCode 1
}

# Create build directory if not exist
if (-not (Test-Path -PathType Container -Path "$($openpype_root)\build")) {
    New-Item -ItemType Directory -Force -Path "$($openpype_root)\build"
}

Write-Host "--- " -NoNewline -ForegroundColor yellow
Write-Host "Cleaning build directory ..."
try {
    Remove-Item -Recurse -Force "$($openpype_root)\build\*"
}
catch {
    Write-Host "!!! " -NoNewline -ForegroundColor Red
    Write-Host "Cannot clean build directory, possibly because process is using it."
    Write-Host $_.Exception.Message
    Exit-WithCode 1
}

Write-Host ">>> " -NoNewLine -ForegroundColor green
Write-Host "Making sure submodules are up-to-date ..."
git submodule update --init --recursive

Write-Host ">>> " -NoNewline -ForegroundColor green
Write-Host "OpenPype [ " -NoNewline -ForegroundColor white
Write-host $openpype_version  -NoNewline -ForegroundColor green
Write-Host " ]" -ForegroundColor white

Write-Host ">>> " -NoNewline -ForegroundColor Green
Write-Host "Reading Poetry ... " -NoNewline
if (-not (Test-Path -PathType Container -Path "$openpype_root\.poetry\bin")) {
    Write-Host "NOT FOUND" -ForegroundColor Yellow
    Write-Host "*** " -NoNewline -ForegroundColor Yellow
    Write-Host "We need to install Poetry create virtual env first ..."
    & "$openpype_root\tools\create_env.ps1"
} else {
    Write-Host "OK" -ForegroundColor Green
}

Write-Host ">>> " -NoNewline -ForegroundColor green
Write-Host "Cleaning cache files ... " -NoNewline
Get-ChildItem $openpype_root -Filter "*.pyc" -Force -Recurse | Remove-Item -Force
Get-ChildItem $openpype_root -Filter "*.pyo" -Force -Recurse | Remove-Item -Force
Get-ChildItem $openpype_root -Filter "__pycache__" -Force -Recurse | Remove-Item -Force -Recurse
Write-Host "OK" -ForegroundColor green

Write-Host ">>> " -NoNewline -ForegroundColor green
Write-Host "Building OpenPype ..."
$startTime = [int][double]::Parse((Get-Date -UFormat %s))

$out = & poetry run python setup.py build 2>&1
if ($LASTEXITCODE -ne 0)
{
    Set-Content -Path "$($openpype_root)\build\build.log" -Value $out
    Write-Host "!!! " -NoNewLine -ForegroundColor Red
    Write-Host "Build failed. Check the log: " -NoNewline
    Write-Host ".\build\build.log" -ForegroundColor Yellow
    Exit-WithCode $LASTEXITCODE
}

Set-Content -Path "$($openpype_root)\build\build.log" -Value $out
& poetry run python "$($openpype_root)\tools\build_dependencies.py"

Write-Host ">>> " -NoNewline -ForegroundColor green
Write-Host "restoring current directory"
Set-Location -Path $current_dir

$endTime = [int][double]::Parse((Get-Date -UFormat %s))
Write-Host "*** " -NoNewline -ForegroundColor Cyan
Write-Host "All done in $($endTime - $startTime) secs. You will find OpenPype and build log in " -NoNewLine
Write-Host "'.\build'" -NoNewline -ForegroundColor Green
Write-Host " directory."
