<#
.SYNOPSIS
    Builds Attendance Manager into a Windows installer:  dist\installer\Attendance Manager Setup.exe

.DESCRIPTION
    1. Creates/updates an isolated build virtual environment (.venv-build)
    2. Installs the pinned dependencies
    3. Runs the test suite (skip with -SkipTests)
    4. Generates the icon assets
    5. Freezes the app with PyInstaller  ->  dist\AttendanceManager\AttendanceManager.exe
    6. Runs the frozen executable's self-test
    7. Compiles the Inno Setup installer (installs Inno Setup 6 via winget if missing)

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build.ps1
    powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -SkipTests
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$NoInstallTools,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`nBUILD FAILED: $text" -ForegroundColor Red; exit 1 }
function Invoke-Checked([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Fail "$exe $($arguments -join ' ') (exit code $LASTEXITCODE)" }
}

# ---------------------------------------------------------------- Python
Step "Locating Python 3.10+"
$candidates = @()
if ($Python) { $candidates += ,@($Python) }
$candidates += ,@("py", "-3")
$candidates += ,@("python")
$pythonCmd = $null
foreach ($c in $candidates) {
    try {
        $v = & $c[0] @($c | Select-Object -Skip 1) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { $pythonCmd = $c; break }
    } catch { }
}
if (-not $pythonCmd) { Fail "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/" }
Write-Host "Using: $($pythonCmd -join ' ') ($v)"

# ---------------------------------------------------------------- venv
$venv = Join-Path $Root ".venv-build"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    Step "Creating build environment (.venv-build)"
    Invoke-Checked $pythonCmd[0] (@($pythonCmd | Select-Object -Skip 1) + @("-m", "venv", $venv))
}
Step "Installing dependencies"
Invoke-Checked $py @("-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip")
Invoke-Checked $py @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "requirements-dev.txt")

# ---------------------------------------------------------------- tests
if (-not $SkipTests) {
    Step "Running tests"
    $env:QT_QPA_PLATFORM = "offscreen"
    Invoke-Checked $py @("-m", "pytest", "-q", "-p", "no:cacheprovider")
    Remove-Item Env:QT_QPA_PLATFORM
}

# ---------------------------------------------------------------- icon
Step "Generating icon assets"
Invoke-Checked $py @("packaging\make_icon.py")

# ---------------------------------------------------------------- freeze
Step "Freezing application with PyInstaller"
if (Test-Path "dist\AttendanceManager") { Remove-Item -Recurse -Force "dist\AttendanceManager" }
Invoke-Checked $py @("-m", "PyInstaller", "packaging\attendance_manager.spec", "--noconfirm", "--clean",
                     "--distpath", "dist", "--workpath", "build\pyinstaller")
$exe = Join-Path $Root "dist\AttendanceManager\AttendanceManager.exe"
if (-not (Test-Path $exe)) { Fail "PyInstaller did not produce $exe" }

Step "Self-testing the frozen executable"
$result = Join-Path $env:TEMP "attendance-manager-selftest.txt"
Remove-Item $result -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $exe -ArgumentList @("--self-test", "`"$result`"") -Wait -PassThru
$text = if (Test-Path $result) { Get-Content $result -Raw } else { "(no output)" }
Write-Host $text
if ($proc.ExitCode -ne 0) { Fail "Self-test of the frozen executable failed." }

# ---------------------------------------------------------------- installer
Step "Locating Inno Setup compiler (ISCC.exe)"
function Find-Iscc {
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}
$iscc = Find-Iscc
if (-not $iscc -and -not $NoInstallTools) {
    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Inno Setup 6 not found - installing it with winget (current user)..."
        & winget install --id JRSoftware.InnoSetup -e --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
        $iscc = Find-Iscc
    }
}
if (-not $iscc) { Fail "Inno Setup 6 is required. Install it from https://jrsoftware.org/isdl.php and re-run." }
Write-Host "Using: $iscc"

$version = & $py -c "import sys; sys.path.insert(0, 'src'); import attendance_manager as m; print(m.__version__)"
Step "Compiling installer (version $version)"
Invoke-Checked $iscc @("/Q", "/DAppVersion=$version", "packaging\installer.iss")
$setup = Join-Path $Root "dist\installer\Attendance Manager Setup.exe"
if (-not (Test-Path $setup)) { Fail "Installer was not produced." }

$size = "{0:N1} MB" -f ((Get-Item $setup).Length / 1MB)
Write-Host "`nBUILD SUCCEEDED" -ForegroundColor Green
Write-Host "Installer: $setup ($size)"
