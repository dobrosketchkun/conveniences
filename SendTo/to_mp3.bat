@echo off
setlocal enabledelayedexpansion

set "input_file=%~1"
set "output_file=%~n1.mp3"

ffmpeg -i "%input_file%" "%output_file%"

echo mp3 version created: "%output_file%"
rem pause>nul
endlocal