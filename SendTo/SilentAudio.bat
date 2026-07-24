@echo off
setlocal enabledelayedexpansion

set "input_file=%~1"
set "output_file=%~dp1silent_%~n1.mp4"

ffmpeg -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -i "%input_file%" -c:v copy -c:a aac -shortest "%output_file%"

echo Silent audio video created: "%output_file%"
rem pause>nul
endlocal