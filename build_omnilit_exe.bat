@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_NAME=OmniLit"
set "ENTRY_FILE=omnilit_qt_app.py"
set "OUTPUT_EXE=%CD%\%APP_NAME%.exe"
set "RELEASE_HELPER=sync_release_metadata.py"
set "DEFAULT_KEY_FILE=Workspace\config\secrets\translate\APIKey.enc"
set "PACKAGED_KEY_FILE="
set "KEY_ENCRYPT_HELPER=encrypt_default_key.py"

set "MODE=%~1"
set "SKIP_KEY="
set "REFRESH_KEY="
set "CHECK_ENV_ONLY="
if /I "%MODE%"=="--skip-key" set "SKIP_KEY=1"
if /I "%MODE%"=="--no-key" set "SKIP_KEY=1"
if /I "%MODE%"=="--build-only" set "SKIP_KEY=1"
if /I "%MODE%"=="--refresh-key" set "REFRESH_KEY=1"
if /I "%MODE%"=="--check-env" set "CHECK_ENV_ONLY=1"

if /I "%MODE%"=="--help" goto usage
if /I "%MODE%"=="/h" goto usage
if /I "%MODE%"=="-h" goto usage

echo [1/9] Locating OmniLit Conda environment...
set "OMNILIT_CONDA_PREFIX="
if /I "%CONDA_DEFAULT_ENV%"=="OmniLit" if defined CONDA_PREFIX set "OMNILIT_CONDA_PREFIX=%CONDA_PREFIX%"
if not defined OMNILIT_CONDA_PREFIX (
  where conda >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Conda was not found on PATH.
    echo Open an Anaconda Prompt or initialize Conda in this terminal first.
    pause
    exit /b 1
  )
  for /f "usebackq delims=" %%P in (`conda run -n OmniLit python -c "import sys; print(sys.prefix)" 2^>nul`) do set "OMNILIT_CONDA_PREFIX=%%P"
)
if not defined OMNILIT_CONDA_PREFIX (
  echo ERROR: The OmniLit Conda environment was not found.
  echo Create or update it, then run this script again:
  echo   conda env update -n OmniLit -f environment.yml --prune
  pause
  exit /b 1
)
set "CONDA_PREFIX=%OMNILIT_CONDA_PREFIX%"
set "PYTHON_CMD=%CONDA_PREFIX%\python.exe"
if not exist "%PYTHON_CMD%" (
  echo ERROR: Conda environment Python was not found: %PYTHON_CMD%
  pause
  exit /b 1
)
set "PATH=%CONDA_PREFIX%\Library\bin;%CONDA_PREFIX%\Library\lib\qt6\bin;%PATH%"

echo Using Conda environment: %CONDA_PREFIX%
call "%PYTHON_CMD%" -c "import sys; print('Python', sys.version.split()[0])"
if errorlevel 1 goto fail
if defined CHECK_ENV_ONLY (
  echo OmniLit Conda environment check passed.
  exit /b 0
)

echo [2/9] Checking pip...
call "%PYTHON_CMD%" -m pip --version >nul 2>nul
if errorlevel 1 goto dependency_fail

echo [3/9] Checking PyInstaller...
call "%PYTHON_CMD%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 goto dependency_fail

echo [4/9] Checking runtime dependencies, including Qt WebEngine and cryptography...
call "%PYTHON_CMD%" -c "import PySide6, requests, fitz, openai, reportlab, rapidocr, onnxruntime, tqdm; import PySide6.QtWebChannel, PySide6.QtWebEngineCore, PySide6.QtWebEngineQuick; from cryptography.fernet import Fernet; from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC" >nul 2>nul
if errorlevel 1 goto dependency_fail

echo [5/9] Syncing version metadata from update_manifest.json...
if not exist "%RELEASE_HELPER%" (
  echo ERROR: %RELEASE_HELPER% was not found.
  goto fail
)
for /f "delims=" %%V in ('""%PYTHON_CMD%" "%RELEASE_HELPER%" prebuild"') do set "APP_VERSION=%%V"
if errorlevel 1 goto fail
if not defined APP_VERSION (
  echo ERROR: Could not read version from update_manifest.json.
  goto fail
)
echo Release version: %APP_VERSION%

echo Building authenticated embedded web assets...
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm was not found on PATH.
  goto fail
)
call npm.cmd run web:build
if errorlevel 1 goto fail

echo [6/9] Preparing encrypted default DeepSeek API Key...
if /I "%MODE%"=="--encrypt-default-key" goto encrypt_key_only

if defined SKIP_KEY (
  echo Skipping encrypted default key generation and packaging by command-line option.
  goto after_key
)

if not exist "%KEY_ENCRYPT_HELPER%" (
  echo WARNING: %KEY_ENCRYPT_HELPER% was not found. Cannot create encrypted default key.
  goto after_key
)

if defined REFRESH_KEY (
  echo Refreshing encrypted default key before packaging...
  goto encrypt_key
)

if exist "%DEFAULT_KEY_FILE%" (
  set "PACKAGED_KEY_FILE=%DEFAULT_KEY_FILE%"
  echo Found encrypted default key: %DEFAULT_KEY_FILE%
  echo It will be packaged automatically.
  goto after_key
)

echo Encrypted default key was not found. Creating it now before packaging...
goto encrypt_key

:encrypt_key
call "%PYTHON_CMD%" "%KEY_ENCRYPT_HELPER%" --output "%DEFAULT_KEY_FILE%"
if errorlevel 1 goto fail
echo Encrypted key saved to: %DEFAULT_KEY_FILE%
set "PACKAGED_KEY_FILE=%DEFAULT_KEY_FILE%"
goto after_key

:encrypt_key_only
if not exist "%KEY_ENCRYPT_HELPER%" (
  echo ERROR: %KEY_ENCRYPT_HELPER% was not found.
  goto fail
)
call "%PYTHON_CMD%" "%KEY_ENCRYPT_HELPER%" --output "%DEFAULT_KEY_FILE%"
if errorlevel 1 goto fail
echo Encrypted key saved to: %DEFAULT_KEY_FILE%
pause
exit /b 0

:after_key
echo [7/9] Cleaning old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"

set "EXTRA_KEY_ARGS="
if not defined SKIP_KEY if defined PACKAGED_KEY_FILE set EXTRA_KEY_ARGS=--add-data "%PACKAGED_KEY_FILE%;Translate"

echo [8/9] Building one-file desktop app...
call "%PYTHON_CMD%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "%APP_NAME%" ^
  --icon "assets\omnilit_logo.ico" ^
  --version-file "version_info.txt" ^
  --hidden-import requests ^
  --hidden-import urllib3 ^
  --hidden-import fitz ^
  --collect-all rapidocr ^
  --collect-all onnxruntime ^
  --hidden-import openai ^
  --hidden-import reportlab ^
  --hidden-import reportlab.pdfgen ^
  --hidden-import reportlab.pdfgen.canvas ^
  --hidden-import reportlab.pdfbase ^
  --hidden-import reportlab.pdfbase.pdfmetrics ^
  --hidden-import reportlab.pdfbase.cidfonts ^
  --hidden-import reportlab.pdfbase.ttfonts ^
  --hidden-import reportlab.lib.utils ^
  --collect-submodules reportlab ^
  --collect-data reportlab ^
  --hidden-import tqdm ^
  --hidden-import cryptography ^
  --hidden-import cryptography.fernet ^
  --hidden-import cryptography.hazmat ^
  --hidden-import cryptography.hazmat.primitives ^
  --hidden-import cryptography.hazmat.primitives.hashes ^
  --hidden-import cryptography.hazmat.primitives.kdf.pbkdf2 ^
  --hidden-import cryptography.hazmat.bindings._rust ^
  --collect-submodules cryptography ^
  --collect-data cryptography ^
  --collect-binaries cryptography ^
  --hidden-import PySide6.QtCore ^
  --hidden-import PySide6.QtGui ^
  --hidden-import PySide6.QtQml ^
  --hidden-import PySide6.QtQuick ^
  --hidden-import PySide6.QtWidgets ^
  --hidden-import PySide6.QtWebChannel ^
  --hidden-import PySide6.QtWebEngineCore ^
  --hidden-import PySide6.QtWebEngineQuick ^
  --add-binary "%CONDA_PREFIX%\Library\bin\Qt6*.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\icu*78.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\double-conversion.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\freetype.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\jpeg8.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\libpng16.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\pcre2-16.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\zlib.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\zstd.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\brotlicommon.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\brotlidec.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\opengl32sw.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\pyside6.cp312-win_amd64.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\pyside6qml.cp312-win_amd64.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\shiboken6.cp312-win_amd64.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\libssl-3-x64.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\libcrypto-3-x64.dll;." ^
  --hidden-import Download.literature_download_core ^
  --hidden-import Download.journal_metrics ^
  --hidden-import Download.journal_registry ^
  --hidden-import Download.pack_builder ^
  --hidden-import Download.topic_packs ^
  --hidden-import Translate.literature_translate_core ^
  --hidden-import Update.update_core ^
  --add-data "assets\omnilit_logo.png;assets" ^
  --add-data "assets\omnilit_logo_164.png;assets" ^
  --add-data "assets\omnilit_logo.ico;assets" ^
  --add-data "ui\qml;ui\qml" ^
  --add-data "apps\web\dist;apps\web\dist" ^
  --add-data "update_manifest.json;." ^
  --add-data "Download\__init__.py;Download" ^
  --add-data "Download\literature_download_core.py;Download" ^
  --add-data "Download\journal_metrics.py;Download" ^
  --add-data "Update\__init__.py;Update" ^
  --add-data "Update\update_core.py;Update" ^
  --add-data "Translate\__init__.py;Translate" ^
  --add-data "Translate\literature_translate_core.py;Translate" ^
  --add-data "Workspace\config\glossary\00_general_academic.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\01_ai_ml_data_science.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\02_catalysis_chemistry_materials.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\03_biology_medicine_pharmaceuticals.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\04_energy_environment_chemical_engineering.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\05_physics_electronics_mechanical_engineering.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\06_computer_science_software.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\07_economics_management_finance.csv;Translate\glossary" ^
  --add-data "Workspace\config\glossary\08_social_science_education_psychology.csv;Translate\glossary" ^
  %EXTRA_KEY_ARGS% ^
  "%ENTRY_FILE%"
if errorlevel 1 goto fail

copy /y "dist\%APP_NAME%.exe" "%OUTPUT_EXE%" >nul
if errorlevel 1 goto fail

echo [9/9] Verifying platform signature and updating signed release metadata...
if not defined OMNILIT_WINDOWS_TIMESTAMP_URL set "OMNILIT_WINDOWS_TIMESTAMP_URL=http://timestamp.digicert.com"
if defined OMNILIT_WINDOWS_SIGN_CERT_SHA1 (
  where signtool.exe >nul 2>nul
  if errorlevel 1 (
    echo ERROR: signtool.exe is required when OMNILIT_WINDOWS_SIGN_CERT_SHA1 is configured.
    goto fail
  )
  signtool.exe sign /sha1 "%OMNILIT_WINDOWS_SIGN_CERT_SHA1%" /fd SHA256 /td SHA256 /tr "%OMNILIT_WINDOWS_TIMESTAMP_URL%" "%OUTPUT_EXE%"
  if errorlevel 1 goto fail
  signtool.exe verify /pa /all /v "%OUTPUT_EXE%"
  if errorlevel 1 goto fail
) else (
  if /I "%OMNILIT_FORMAL_RELEASE%"=="1" (
    echo ERROR: Formal releases require OMNILIT_WINDOWS_SIGN_CERT_SHA1 and Authenticode verification.
    goto fail
  )
  echo WARNING: Built an unsigned Windows development artifact. It must not be distributed as a formal release.
)
call "%PYTHON_CMD%" "%RELEASE_HELPER%" postbuild --exe "%OUTPUT_EXE%"
if errorlevel 1 goto fail

echo Cleaning temporary build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"

echo Done: %OUTPUT_EXE%
echo Release file: %OUTPUT_EXE%
echo update_manifest.json has been updated with version %APP_VERSION%, the release SHA-256, and its Ed25519 signature.
if not defined SKIP_KEY if defined PACKAGED_KEY_FILE echo Encrypted default key included in the packaged resources from: %PACKAGED_KEY_FILE%
pause
exit /b 0

:usage
echo Usage:
echo   build_omnilit_exe.bat                 Package Workspace\config\secrets\translate\APIKey.enc if present; create it with the CLI if missing.
echo   build_omnilit_exe.bat --refresh-key   Recreate Workspace\config\secrets\translate\APIKey.enc, then build EXE.
echo   build_omnilit_exe.bat --encrypt-default-key   Only create Workspace\config\secrets\translate\APIKey.enc.
echo   build_omnilit_exe.bat --skip-key      Build EXE without default key.
echo   build_omnilit_exe.bat --check-env     Verify Conda environment discovery only.
pause
exit /b 0

:dependency_fail
echo ERROR: The OmniLit Conda environment is missing a required dependency.
echo Update the environment, reactivate it, and run this BAT again:
echo   conda env update -n OmniLit -f environment.yml --prune
echo   conda activate OmniLit
pause
exit /b 1

:fail
echo Build failed.
pause
exit /b 1
