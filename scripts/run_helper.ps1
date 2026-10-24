#Requires -Version 5.0
<#
.SYNOPSIS
    Zhihuiya Patent Assistant (WorkBuddy Edition) - Zero-Touch Python Auto-Bootstrap Launcher
.DESCRIPTION
    1. Automatically detects if a working Python 3.7+ is installed (skipping the 0-byte Windows Store alias).
    2. If Python is missing, silently downloads the official 10MB Python 3.11 Embeddable runtime from
       China high-speed mirror (npmmirror CDN) or python.org, extracts it to LocalAppData (no admin/UAC required),
       enables site-packages/local imports, and registers it in User PATH.
    3. Forwards all CLI arguments to zhihuiya_helper.py with UTF-8 encoding.
#>

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SkillDir  = Split-Path -Parent $ScriptDir
$HelperPy  = Join-Path $ScriptDir "zhihuiya_helper.py"

$SharedPyDir = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311-ZhiHuiYa"
$LocalPyDir  = Join-Path $SkillDir ".runtime\python"

function Test-PythonExecutable {
    param([string]$ExePath, [string[]]$PrefixArgs = @())
    if ([string]::IsNullOrWhiteSpace($ExePath)) { return $false }
    try {
        if ($ExePath -like "*\Microsoft\WindowsApps\python*.exe") {
            $item = Get-Item $ExePath -ErrorAction SilentlyContinue
            if (-not $item -or $item.Length -eq 0) { return $false }
        }
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $null = & $ExePath @PrefixArgs -c "import sys, urllib.request, ssl, json, concurrent.futures; sys.exit(0 if sys.version_info >= (3, 7) else 1)" 2>$null
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        return ($code -eq 0)
    } catch {
        return $false
    }
}

function Find-WorkingPython {
    # 1. Check cached portable Python first (fast & deterministic)
    foreach ($dir in @($SharedPyDir, $LocalPyDir)) {
        $candidate = Join-Path $dir "python.exe"
        if ((Test-Path $candidate) -and (Test-PythonExecutable -ExePath $candidate)) {
            return @{ Exe = $candidate; Prefix = @() }
        }
    }

    # 2. Check python / python3 in PATH
    foreach ($cmdName in @("python", "python3")) {
        $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd -and $cmd.Source) {
            if (Test-PythonExecutable -ExePath $cmd.Source) {
                return @{ Exe = $cmd.Source; Prefix = @() }
            }
        }
    }

    # 3. Check Windows py launcher
    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pyLauncher -and $pyLauncher.Source) {
        if (Test-PythonExecutable -ExePath $pyLauncher.Source -PrefixArgs @("-3")) {
            return @{ Exe = $pyLauncher.Source; Prefix = @("-3") }
        }
    }

    # 4. Scan common installation directories
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "C:\Python3*\python.exe",
        "D:\Python3*\python.exe",
        "D:\python\python.exe",
        "$env:USERPROFILE\miniconda3\python.exe",
        "$env:USERPROFILE\anaconda3\python.exe"
    )
    foreach ($pattern in $commonPaths) {
        $found = Get-Item $pattern -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($found -and (Test-PythonExecutable -ExePath $found.FullName)) {
            return @{ Exe = $found.FullName; Prefix = @() }
        }
    }

    return $null
}

function Install-PortablePython {
    Write-Host "[Auto-Setup] Python 3 not found on this PC. Auto-installing green Python 3.11 (~10MB)..." -ForegroundColor Cyan

    $targetDir = $SharedPyDir
    try {
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
    } catch {
        $targetDir = $LocalPyDir
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
    }

    $zipPath = Join-Path $targetDir "python-embed.zip"
    $arch = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { "win32" }
    $urls = @(
        "https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-embed-$arch.zip",
        "https://cdn.npmmirror.com/binaries/python/3.11.9/python-3.11.9-embed-$arch.zip",
        "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-$arch.zip"
    )

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
    $downloaded = $false

    foreach ($url in $urls) {
        try {
            Write-Host "[Auto-Setup] Downloading from mirror: $url" -ForegroundColor Gray
            $curlCmd = Get-Command "curl.exe" -ErrorAction SilentlyContinue
            if ($curlCmd) {
                & curl.exe -L -s --connect-timeout 10 --max-time 60 -o "$zipPath" "$url"
            } else {
                Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing -TimeoutSec 60
            }
            if ((Test-Path $zipPath) -and ((Get-Item $zipPath).Length -gt 5000000)) {
                $downloaded = $true
                break
            }
        } catch {
            Write-Host "[Auto-Setup] Mirror failed, switching to fallback..." -ForegroundColor Yellow
        }
    }

    if ($downloaded) {
        Write-Host "[Auto-Setup] Extracting portable Python runtime..." -ForegroundColor Cyan
        Expand-Archive -Path $zipPath -DestinationPath $targetDir -Force
        Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

        $pthFile = Join-Path $targetDir "python311._pth"
        if (Test-Path $pthFile) {
            $pthContent = @(
                "python311.zip",
                ".",
                "import site"
            )
            Set-Content -Path $pthFile -Value $pthContent -Encoding Ascii
        }

        try {
            $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if (-not $userPath) { $userPath = "" }
            if ($userPath -notlike "*$targetDir*") {
                $newUserPath = "$targetDir;$userPath"
                [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
            }
        } catch {
            # Ignore User PATH update error if restricted; direct path still works
        }

        $pyExe = Join-Path $targetDir "python.exe"
        if (Test-PythonExecutable -ExePath $pyExe) {
            Write-Host "[Auto-Setup] Portable Python 3.11 ready: $pyExe" -ForegroundColor Green
            return @{ Exe = $pyExe; Prefix = @() }
        }
    }

    $wingetCmd = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($wingetCmd) {
        Write-Host "[Auto-Setup] Trying winget silent install of Python 3.11..." -ForegroundColor Cyan
        & winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
        $foundAfterWinget = Find-WorkingPython
        if ($foundAfterWinget) {
            return $foundAfterWinget
        }
    }

    throw "Failed to auto-install Python 3. Please check your internet connection."
}

$pyInfo = Find-WorkingPython
if (-not $pyInfo -or ($args.Count -ge 1 -and $args[0] -eq "--force-install-portable")) {
    $pyInfo = Install-PortablePython
    if ($args.Count -ge 1 -and $args[0] -eq "--force-install-portable") {
        Write-Output "PORTABLE_PYTHON_OK=$($pyInfo.Exe)"
        exit 0
    }
}

if ($args.Count -eq 1 -and $args[0] -eq "--ensure-only") {
    Write-Output "PYTHON_OK=$($pyInfo.Exe)"
    exit 0
}

$execArgs = @()
if ($pyInfo.Prefix -and $pyInfo.Prefix.Count -gt 0) {
    $execArgs += $pyInfo.Prefix
}
$execArgs += $HelperPy
if ($args.Count -gt 0) {
    $execArgs += $args
}

$ErrorActionPreference = "Continue"
& $pyInfo.Exe @execArgs
exit $LASTEXITCODE
