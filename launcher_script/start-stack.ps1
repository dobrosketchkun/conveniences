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

# Temporary CMD launchers are stored here.
$generatedDirectory = Join-Path $env:TEMP 'StartStack-CmdLaunchers'

New-Item `
    -ItemType Directory `
    -Path $generatedDirectory `
    -Force | Out-Null

foreach ($jobName in $jobs.Keys) {
    $job = $jobs[$jobName]

    if (-not (Test-Path -LiteralPath $job.WorkDir -PathType Container)) {
        Write-Warning (
            'Skipping "{0}" because its directory does not exist: {1}' -f `
            $job.Title,
            $job.WorkDir
        )

        continue
    }

    $safeJobName = $jobName -replace '[^A-Za-z0-9_-]', '_'
    $cmdFile = Join-Path $generatedDirectory "$safeJobName.cmd"

    $lines = [System.Collections.Generic.List[string]]::new()

    $lines.Add('@echo off')
    $lines.Add('title ' + $job.Title)
    $lines.Add('')
    $lines.Add('cd /d "' + $job.WorkDir + '"')
    $lines.Add('')

    $lines.Add('if errorlevel 1 (')
    $lines.Add('    echo.')
    $lines.Add('    echo Could not open the configured directory:')
    $lines.Add('    echo ' + $job.WorkDir)
    $lines.Add('    echo.')
    $lines.Add('    echo This Command Prompt will remain open.')
    $lines.Add('    cmd.exe /K')
    $lines.Add('    exit /b 1')
    $lines.Add(')')

    foreach ($setupCommand in $job.Setup) {
        $lines.Add('')
        $lines.Add($setupCommand)
        $lines.Add('')

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

    $lines.Add('')
    $lines.Add('cls')
    $lines.Add('echo ============================================================')
    $lines.Add('echo  ' + $job.Title)
    $lines.Add('echo ============================================================')
    $lines.Add('echo.')
    $lines.Add('echo Directory:')
    $lines.Add('echo %CD%')
    $lines.Add('echo.')
    $lines.Add('echo Press Ctrl+C to stop the application.')
    $lines.Add('echo The Command Prompt will remain open afterward.')
    $lines.Add('echo.')
    $lines.Add('echo ============================================================')
    $lines.Add('echo.')

    # Start a persistent CMD session.
    #
    # The application runs inside this CMD session. When it stops,
    # the user is returned to a normal CMD prompt in the same folder.
    $lines.Add('cmd.exe /K ' + $job.Command)

    [System.IO.File]::WriteAllLines(
        $cmdFile,
        $lines,
        [System.Text.Encoding]::Default
    )

    $terminalArguments = @(
        '-w'
        'new'
        'new-tab'
        '--title'
        ('"' + $job.Title + '"')
        '--suppressApplicationTitle'
        'cmd.exe'
        '/C'
        'call'
        ('"' + $cmdFile + '"')
    )

    Start-Process `
        -FilePath 'wt.exe' `
        -ArgumentList $terminalArguments

    Start-Sleep -Milliseconds 200
}