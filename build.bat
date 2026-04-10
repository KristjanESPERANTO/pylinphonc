@echo off
REM Build pylinphonc.exe with PyInstaller
REM
REM The resulting exe is a self-contained drop-in replacement for linphonc.exe:
REM   - bundles Python runtime
REM   - bundles all Linphone SDK DLLs
REM   - bundles share/belr/grammars/ (grammar files)
REM   - no Python or SDK required on the target system
REM   - --dll-dir is not needed when running the bundled exe
REM
REM Requirements:
REM   pip install pyinstaller          (or: pip install pylinphonc[build])
REM   NuGet SDK extracted with content\ renamed to share\
REM
REM Usage:
REM   build.bat                          uses SDK_DIR below
REM   build.bat C:\path\to\sdk           override SDK path
REM
REM Output: dist\pylinphonc.exe  (~200 MB)

if not "%~1" == "" (
    set SDK_DIR=%~1
) else (
    REM Default: adjust this path to your local SDK extraction
    set SDK_DIR=C:\linphone-sdk
)

if not exist "%SDK_DIR%\lib\win\x64\liblinphone.dll" (
    echo ERROR: liblinphone.dll not found in %SDK_DIR%\lib\win\x64\
    echo        Set SDK_DIR or pass the SDK path as first argument.
    exit /b 1
)

if not exist "%SDK_DIR%\share\belr\grammars" (
    echo ERROR: share\belr\grammars\ not found in %SDK_DIR%\
    echo        Rename content\ to share\ after extracting the NuGet package.
    exit /b 1
)

echo SDK : %SDK_DIR%
echo.

python -m PyInstaller ^
    --onefile ^
    --name pylinphonc ^
    --add-binary "%SDK_DIR%\lib\win\x64\*.dll;." ^
    --add-data  "%SDK_DIR%\share;share" ^
    --hidden-import win32service ^
    --hidden-import win32serviceutil ^
    --hidden-import win32event ^
    --hidden-import servicemanager ^
    src\pylinphonc\__main__.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Build successful: dist\pylinphonc.exe
    echo.
    echo Usage on target system:
    echo   pylinphonc.exe -a -c linphonerc -d 1
) else (
    echo Build failed.
    exit /b 1
)
