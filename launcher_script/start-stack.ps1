$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------
# Configure all programs here.
#
# Setup:
#   Commands that run before the main application.
#   Leave it as @() when no setup is required.
#
# Command:
#   The application or script to run.
#
# Every application runs inside CMD, not PowerShell.
# --------------------------------------------------------------------

$jobs = [ordered]@{
    api = @{
        Title   = 'API Server'
        WorkDir = 'C:\dev\my-api'

        Setup = @(
            'call conda activate api-env'
        )

        Command = 'python -m uvicorn app:app --reload'
    }

    worker = @{
        Title   = 'Background Worker'
        WorkDir = 'C:\dev\my-api'

        Setup = @(
            'call conda activate worker-env'
        )

        Command = 'python worker.py'
    }

    frontend = @{
        Title   = 'Frontend'
        WorkDir = 'C:\dev\my-frontend'

        Setup = @()

        Command = 'npm run dev'
    }

    database = @{
        Title   = 'Database'
        WorkDir = 'C:\dev\database'

        Setup = @()

        Command = 'docker compose up'
    }
}

# Temporary CMD launchers and info files are stored here.
$generatedDirectory = Join-Path $env:TEMP 'StartStack-CmdLaunchers'
 
New-Item -ItemType Directory -Path $generatedDirectory -Force | Out-Null
 
# doskey treats "$" as special ($T, $1, ...), so a literal "$" must be "$$".
function ConvertTo-DoskeyText([string]$Text) {
    return $Text -replace '\$', '$$$$'
}
 
$separator = '=' * 60
 
foreach ($jobName in $jobs.Keys) {
    $job = $jobs[$jobName]
 
    if (-not (Test-Path -LiteralPath $job.WorkDir -PathType Container)) {
        Write-Warning (
            'Skipping "{0}" because its directory does not exist: {1}' -f `
            $job.Title, $job.WorkDir
        )
        continue
    }
 
    # Ignore empty setup entries such as @('').
    $setupCommands = @($job.Setup | Where-Object { $_ -and $_.Trim() })
 
    $safeJobName = $jobName -replace '[^A-Za-z0-9_-]', '_'
    $cmdFile     = Join-Path $generatedDirectory "$safeJobName.cmd"
    $infoFile    = Join-Path $generatedDirectory "$safeJobName.info.txt"
 
    # ---------------- Header / info file ----------------
    $info = [System.Collections.Generic.List[string]]::new()
    $info.Add($separator)
    $info.Add(' ' + $job.Title)
    $info.Add($separator)
    $info.Add('')
    $info.Add('WorkDir:')
    $info.Add('  ' + $job.WorkDir)
    $info.Add('')
    $info.Add('Setup:')
    if ($setupCommands.Count -gt 0) {
        foreach ($s in $setupCommands) { $info.Add('  ' + $s) }
    }
    else {
        $info.Add('  (none)')
    }
    $info.Add('')
    $info.Add('Command:')
    $info.Add('  ' + $job.Command)
    $info.Add('')
    $info.Add('Press Ctrl+C to stop the application.')
    $info.Add('Afterwards, type:')
    $info.Add('  run   - start the command again')
    $info.Add('  info  - show this header again')
    $info.Add('')
    $info.Add($separator)
    $info.Add('')
 
    [System.IO.File]::WriteAllLines($infoFile, $info, [System.Text.Encoding]::Default)
 
    # ---------------- CMD launcher ----------------
    $lines = [System.Collections.Generic.List[string]]::new()
 
    $lines.Add('@echo off')
    $lines.Add('title ' + $job.Title)
    $lines.Add('')
    $lines.Add('cd /d "' + $job.WorkDir + '"')
    $lines.Add('if errorlevel 1 (')
    $lines.Add('    echo.')
    $lines.Add('    echo Could not open the configured directory:')
    $lines.Add('    echo ' + $job.WorkDir)
    $lines.Add('    echo.')
    $lines.Add('    echo This Command Prompt will remain open.')
    $lines.Add('    cmd.exe /K')
    $lines.Add('    exit /b 1')
    $lines.Add(')')
 
    foreach ($setupCommand in $setupCommands) {
        $lines.Add('')
        $lines.Add($setupCommand)
        $lines.Add('if errorlevel 1 (')
        $lines.Add('    echo.')
        $lines.Add('    echo A setup command failed:')
        $lines.Add('    echo ' + $setupCommand)
        $lines.Add('    echo.')
        $lines.Add('    echo This Command Prompt will remain open.')
        $lines.Add('    cmd.exe /K')
        $lines.Add('    exit /b 1')
        $lines.Add(')')
    }
 
    # Macros live in this console, so the child "cmd /K" below sees them.
    $lines.Add('')
    $lines.Add('doskey run=' + (ConvertTo-DoskeyText $job.Command))
    $lines.Add('doskey info=type "' + $infoFile + '"')
 
    $lines.Add('')
    $lines.Add('cls')
    $lines.Add('type "' + $infoFile + '"')
 
    # The application runs inside this CMD session. When it stops,
    # the user is returned to a normal CMD prompt in the same folder.
    $lines.Add('cmd.exe /K ' + $job.Command)
 
    [System.IO.File]::WriteAllLines($cmdFile, $lines, [System.Text.Encoding]::Default)
 
    # ---------------- Launch in Windows Terminal ----------------
    $terminalArguments = @(
        '-w', 'new'
        'new-tab'
        '--title', ('"' + $job.Title + '"')
        '--suppressApplicationTitle'
        '-d', ('"' + $job.WorkDir + '"')
        'cmd.exe', '/C', 'call', ('"' + $cmdFile + '"')
    )
 
    # WorkingDirectory makes new tabs in this window open in WorkDir.
    Start-Process `
        -FilePath 'wt.exe' `
        -ArgumentList $terminalArguments `
        -WorkingDirectory $job.WorkDir
 
    Start-Sleep -Milliseconds 200
}
