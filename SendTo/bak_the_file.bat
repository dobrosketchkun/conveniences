@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Full path of the selected file
set "source=%~f1"

if "%~1"=="" (
  echo Usage: %~nx0 "C:\path\to\file.ext"
  exit /b 64
)
if not exist "%source%" (
  echo File not found: "%source%"
  exit /b 2
)

rem Pieces we need
set "dir=%~dp1"
set "name=%~nx1"
set "baseName=%name%.bak"
set "pattern=%dir%%name%.bak*"

rem Find the highest existing suffix (plain .bak counts as 0)
set "max=-1"
for /f "delims=" %%A in ('dir /b /a:-d "%pattern%" 2^>nul') do (
  set "item=%%A"
  if /I "!item!"=="%baseName%" (
    if !max! LSS 0 set "max=0"
  ) else (
    set "tail=!item:%baseName%=!"
    if defined tail (
      echo(!tail!| findstr /r "^[0-9][0-9]*$" >nul
      if not errorlevel 1 (
        set /a n=tail
        if !n! GTR !max! set "max=!n!"
      )
    )
  )
)

if !max! LSS 0 (
  set "dest=%source%.bak"
) else (
  set /a next=max+1
  set "dest=%source%.bak!next!"
)

copy "%source%" "%dest%" >nul || (
  echo Copy failed.
  exit /b 1
)

echo Created "!dest!"
endlocal


rem @echo off
rem setlocal
rem 
rem rem Get the full path of the selected file
rem set "source=%~1"
rem 
rem rem Check if the source file exists
rem if not exist "%source%" (
rem     echo File not found: %source%
rem     exit /b
rem )
rem 
rem rem Define the destination file name by appending .bak
rem set "destination=%source%.bak"
rem 
rem rem Copy the file
rem copy "%source%" "%destination%"
rem 
rem endlocal
rem THE OLD VERSION