# Find-ResolveModules.ps1
# Helper to locate the DaVinci Resolve Python scripting module on Windows.
# Run this in PowerShell:
#   .\video_system\tools\resolve\find_resolve_modules.ps1

Write-Host "=== DaVinci Resolve Python Scripting Module Finder ===" -ForegroundColor Cyan
Write-Host "This will search common locations and your entire C: drive for DaVinciResolveScript.py"
Write-Host "Resolve must be installed for this to find anything."
Write-Host ""

$found = $false

# Search common Blackmagic locations first (fast)
$commonRoots = @(
    "C:\Program Files\Blackmagic Design",
    "C:\Program Files (x86)\Blackmagic Design",
    "C:\ProgramData\Blackmagic Design",
    "$env:LOCALAPPDATA\Blackmagic Design",
    "C:\Users\$env:USERNAME\AppData\Local\Blackmagic Design"
)

foreach ($root in $commonRoots) {
    if (Test-Path $root) {
        Write-Host "Searching $root ..." -ForegroundColor Yellow
        $scripts = Get-ChildItem -Path $root -Recurse -Filter "DaVinciResolveScript.py" -ErrorAction SilentlyContinue
        foreach ($s in $scripts) {
            $folder = $s.Directory.FullName
            Write-Host "  FOUND: $($s.FullName)" -ForegroundColor Green
            Write-Host "  --> Set this as your RESOLVE_PYTHON_API:" -ForegroundColor Green
            Write-Host "  `$env:RESOLVE_PYTHON_API = `"$folder`"" -ForegroundColor White
            $found = $true
        }
    }
}

if (-not $found) {
    Write-Host "No luck in common locations. Doing a broader search (this can take 30-90 seconds)..." -ForegroundColor Yellow
    Write-Host "Searching from C:\ for DaVinciResolveScript.py (limited depth to avoid taking forever)..."
    
    # Limited depth search to keep it reasonable
    $scripts = Get-ChildItem -Path C:\ -Recurse -Filter "DaVinciResolveScript.py" -ErrorAction SilentlyContinue -Depth 8
    foreach ($s in $scripts) {
        $folder = $s.Directory.FullName
        Write-Host "  FOUND: $($s.FullName)" -ForegroundColor Green
        Write-Host "  --> Use this path:" -ForegroundColor Green
        Write-Host "  `$env:RESOLVE_PYTHON_API = `"$folder`"" -ForegroundColor White
        $found = $true
    }
}

Write-Host ""
if ($found) {
    Write-Host "SUCCESS: Copy one of the `$env: lines above, paste it in your PowerShell, then run:" -ForegroundColor Green
    Write-Host "  python video_system\tools\resolve\test_connection.py" -ForegroundColor White
    Write-Host ""
    Write-Host "IMPORTANT: DaVinci Resolve **must be running** (launched, with a project open) before the test will succeed." -ForegroundColor Yellow
    Write-Host "Also run the test in the same PowerShell session where you set the env var."
} else {
    Write-Host "No DaVinciResolveScript.py found." -ForegroundColor Red
    Write-Host "This usually means:"
    Write-Host "  - DaVinci Resolve Studio is not installed on this machine, or"
    Write-Host "  - It is installed but scripting support was not included (rare), or"
    Write-Host "  - Installed in a very custom location."
    Write-Host ""
    Write-Host "Next steps for you:"
    Write-Host "1. Make sure you have DaVinci Resolve Studio installed and **launched**."
    Write-Host "2. In File Explorer, press Win+E, go to C:\ , type 'DaVinciResolveScript.py' in the search box (top right), and wait."
    Write-Host "3. When it finds the file, right-click the file -> Properties, and note the folder path."
    Write-Host "4. Come back here and tell me the full path to the *folder* (the one containing the .py file)."
    Write-Host "5. We will set the env var correctly and test again."
}

Write-Host ""
Write-Host "Also checking if any Resolve process is currently running..." -ForegroundColor Cyan
$resolveProcs = Get-Process -Name "*Resolve*", "*DaVinci*" -ErrorAction SilentlyContinue
if ($resolveProcs) {
    $resolveProcs | Select Name, Id, Path | Format-Table -AutoSize
} else {
    Write-Host "No Resolve process detected. You must launch DaVinci Resolve before the API can connect." -ForegroundColor Red
}
