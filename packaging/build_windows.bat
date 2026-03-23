@echo off
REM =============================================================================
REM SeenSlide Desktop - Windows Build Script
REM Creates a standalone Windows executable using PyInstaller
REM =============================================================================

setlocal enabledelayedexpansion

set APP_NAME=SeenSlide
set APP_VERSION=1.0.0

echo ========================================
echo   %APP_NAME% Windows Build v%APP_VERSION%
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    exit /b 1
)

REM Check pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available.
    exit /b 1
)

REM Install dependencies
echo [INFO] Installing dependencies...
pip install -r "%~dp0..\requirements.txt"
pip install pyinstaller

REM Set paths
set PROJECT_DIR=%~dp0..
set BUILD_DIR=%~dp0dist\windows

if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%BUILD_DIR%"

echo [INFO] Building with PyInstaller...

cd /d "%PROJECT_DIR%"

pyinstaller --noconfirm --clean ^
    --name "SeenSlide" ^
    --windowed ^
    --add-data "config;config" ^
    --add-data "gui;gui" ^
    --add-data "core;core" ^
    --add-data "modules;modules" ^
    --hidden-import PyQt5 ^
    --hidden-import PyQt5.QtCore ^
    --hidden-import PyQt5.QtGui ^
    --hidden-import PyQt5.QtWidgets ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import imagehash ^
    --hidden-import mss ^
    --hidden-import mss.windows ^
    --hidden-import fastapi ^
    --hidden-import uvicorn ^
    --hidden-import pydantic ^
    --hidden-import requests ^
    --hidden-import yaml ^
    --hidden-import bcrypt ^
    --distpath "%BUILD_DIR%" ^
    gui\main.py

if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

REM Clean up build artifacts
if exist "%PROJECT_DIR%\build" rmdir /s /q "%PROJECT_DIR%\build"
if exist "%PROJECT_DIR%\SeenSlide.spec" del "%PROJECT_DIR%\SeenSlide.spec"

echo.
echo [INFO] Build complete!
echo Output: %BUILD_DIR%\SeenSlide\
echo.
echo To create an installer, use Inno Setup or NSIS with the output directory.
echo To run directly: %BUILD_DIR%\SeenSlide\SeenSlide.exe

endlocal
