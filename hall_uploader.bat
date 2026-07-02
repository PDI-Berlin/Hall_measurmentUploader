@echo off
REM Hall PC -> NOMAD Uploader - Windows Batch Interface
REM Interactive UI for Hall measurement uploader script
REM Created with a GUI-like appearance for best user experience

REM Set window appearance
TITLE Hall PC -> NOMAD Uploader - Interactive Interface
Color 1F
cls

REM Function to clear screen with header
FUNCTION_ClearScreen()
(
    cls
    echo ==============================================================================
    echo  Hall PC -> NOMAD Uploader - Interactive Interface
    echo ------------------------------------------------------------------------------
    exit /b
)

REM Function to print a pause message
FUNCTION_PromptKeyToContinue()
(
    echo.
    echo     Press any key to continue...
    pause >nul
    exit /b
)

REM Function to display error messages
FUNCTION_ShowError()
(
    echo.
    echo     ERROR: %1
    pause >nul
    exit /b
)

REM Function to display a header
FUNCTION_PrintHeader()
(
    echo ==============================================================================
    echo  %1
    echo ------------------------------------------------------------------------------
    exit /b
)

REM Function to display a subheader
FUNCTION_PrintSubheader()
(
    echo.
    echo     %1
    exit /b
)

REM Main UI
REM Check for admin privileges (helps with Python path issues)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo     Note: Some features require administrator permissions
    echo     Please run as Administrator if you encounter issues
)

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    FUNCTION_PrintHeader("Python Installation Check")
    FUNCTION_PrintSubheader("Python is not installed or not in PATH")
    FUNCTION_PrintSubheader("Please install Python 3.8+ and try again")
    pause
    exit /b 1
)

REM Check if required Python modules are available
python -c "import requests, yaml" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    FUNCTION_PrintHeader("Dependencies Check")
    FUNCTION_PrintSubheader("Required Python modules not found")
    FUNCTION_PrintSubheader("Attempting to install dependencies...")
    
    pip install -q requests pyyaml >nul 2>&1
    if %errorlevel% neq 0 (
        FUNCTION_PrintSubheader("ERROR: Failed to install dependencies")
        FUNCTION_PrintSubheader("Please run: pip install requests pyyaml")
        pause
        exit /b 1
    ) else (
        FUNCTION_PrintSubheader("Dependencies installed successfully")
    )
)

REM Main Menu Loop
:MAIN_MENU
FUNCTION_ClearScreen()

FUNCTION_PrintHeader("Main Menu - Hall PC -> NOMAD Uploader")
echo.
FUNCTION_PrintSubheader("Options:")
echo.
FUNCTION_PrintSubheader("  1. Interactive Mode (Recommended - GUI-like experience)")
echo.
FUNCTION_PrintSubheader("  2. Command Line Mode (Process specific folder)")
echo.
FUNCTION_PrintSubheader("  3. Configure Settings")
echo.
FUNCTION_PrintSubheader("  4. View Current Configuration")
echo.
FUNCTION_PrintSubheader("  5. Exit")
echo.

FUNCTION_PrintHeader("Please select an option (1-5):")

set /p choice="     ">

if "%choice%"=="1" goto INTERACTIVE_MODE
if "%choice%"=="2" goto CLI_MODE
if "%choice%"=="3" goto CONFIG_MODE
if "%choice%"=="4" goto VIEW_CONFIG
if "%choice%"=="5" goto EXIT

FUNCTION_PrintSubheader("Invalid choice. Please select 1-5.")
goto MAIN_MENU

REM Interactive Mode - Main functionality
:INTERACTIVE_MODE
FUNCTION_ClearScreen()

REM Check if config exists
if not exist "config.yml" (
    call :CONFIG_MODE
)

REM Load and display current configuration
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Configuration Check")

REM Load configuration and display in a cleaner way
python -c "
import sys
from pathlib import Path
try:
    import yaml
    HAS_YAML = True
except:
    HAS_YAML = False

CONFIG_PATH = Path('config.yml')
if HAS_YAML and CONFIG_PATH.exists():
    with open(CONFIG_PATH, 'r') as f:
        cfg = yaml.safe_load(f) or {}
else:
    cfg = {}

print('=== CURRENT CONFIGURATION ===')
print('  Instrument   :', cfg.get('instrument', 'PDI_Hall_Setup'))
print('  Last Folder  :', cfg.get('last_folder', 'Not set'))
print('  Last User     :', cfg.get('last_user', 'Not set'))
print()
print('  Users:')
for user in cfg.get('users', {}).keys():
    user_cfg = cfg['users'].get(user, {})
    print('    ', user)
    print('        Server    :', user_cfg.get('base_url', 'Not set'))
    print('        Upload ID :', user_cfg.get('upload_id', 'Not set'))
print()
" > temp_config.txt

< temp_config.txt (
    echo.
    FUNCTION_PrintSubheader("Current Configuration:")
    %ERRORLEVEL%
    echo.
    del temp_config.txt
) > nul

call :FUNCTION_PromptKeyToContinue

REM Run the actual uploader script
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Starting Interactive Upload")
echo.
FUNCTION_PrintSubheader("Running the main uploader script...")
echo.

python hall_uploader.py

if %errorlevel% neq 0 (
    echo.
    FUNCTION_PrintSubheader("Upload failed!")
    pause
) else (
    echo.
    FUNCTION_PrintSubheader("Upload completed successfully!")
    pause
)

goto MAIN_MENU

REM Command Line Mode
:CLI_MODE
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Command Line Mode")
echo.
FUNCTION_PrintSubheader("Usage:")
echo.
FUNCTION_PrintSubheader("  hall_uploader.bat process <folder-path> [--dry-run]")
echo.
FUNCTION_PrintSubheader("  hall_uploader.bat --help    (show help)")
echo.
FUNCTION_PrintSubheader("  hall_uploader.bat --version   (show version)")
echo.

REM Parse command line arguments
if "%1"=="" goto CLI_HELP
if "%1"=="--help" goto CLI_HELP
if "%1"=="--version" goto CLI_VERSION
if NOT "%1"=="process" goto CLI_INVALID_CMD

if "%2"=="" goto CLI_NO_PATH

REM Process command with specified folder
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Processing Folder")
echo.
FUNCTION_PrintSubheader("Folder: %2")
echo.

REM Check if folder exists
if not exist "%2\" (
    FUNCTION_PrintSubheader("ERROR: Folder does not exist: %2")
    pause
    goto CLI_MODE
)

REM Determine if dry run
if "%3"=="--dry-run" (
    FUNCTION_PrintSubheader("Mode: Dry Run (will not upload)")
    python hall_uploader.py "%2" --dry-run
) else (
    FUNCTION_PrintSubheader("Mode: Process and Upload")
    python hall_uploader.py "%2"
)

if %errorlevel% neq 0 (
    FUNCTION_PrintSubheader("Command failed with error!")
) else (
    FUNCTION_PrintSubheader("Command completed successfully!")
)

pause
goto MAIN_MENU

:CLI_HELP
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Help - Command Line Options")
echo.
FUNCTION_PrintSubheader("hall_uploader.bat [options]")
echo.
FUNCTION_PrintSubheader("Options:")
echo.
FUNCTION_PrintSubheader("  --help           Show this help message")
echo.
FUNCTION_PrintSubheader("  --version        Show version information")
echo.
FUNCTION_PrintSubheader("  process <folder> Process a specific folder and upload to NOMAD")
echo.
FUNCTION_PrintSubheader("  --dry-run        Build files only, skip upload (for testing)")
echo.
FUNCTION_PrintSubheader("  --instrument <id> Override the instrument name")
echo.
pause
goto CLI_MODE

:CLI_VERSION
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Version Information")
echo.
FUNCTION_PrintSubheader("Hall PC -> NOMAD Uploader")
echo.
FUNCTION_PrintSubheader("Version: 1.0.0")
echo.
FUNCTION_PrintSubheader("Python script: hall_uploader.py")
echo.
FUNCTION_PrintSubheader("Author: PDI-Berlin")
echo.
FUNCTION_PrintSubheader("")
echo.
FUNCTION_PrintSubheader("Integrated with Windows Batch Interface")
echo.
pause
goto CLI_MODE

:CLI_INVALID_CMD
FUNCTION_PrintSubheader("Invalid command. Use --help for usage information.")
pause
goto CLI_MODE

:CLI_NO_PATH
FUNCTION_PrintSubheader("ERROR: Please specify a folder path.")
FUNCTION_PrintSubheader("Usage: hall_uploader.bat process <folder-path>")
pause
goto CLI_MODE

REM Configuration Mode
:CONFIG_MODE
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Configuration Setup")
echo.
FUNCTION_PrintSubheader("This will help you set up your configuration for the uploader.")
echo.
FUNCTION_PrintSubheader("Note: Configuration file is 'config.yml'")
echo.
FUNCTION_PrintSubheader("You should edit it in a text editor to match your NOMAD setup.")
echo.
FUNCTION_PrintSubheader("")
echo.
FUNCTION_PrintSubheader("Recommended settings for config.yml:")
echo.
FUNCTION_PrintSubheader("")
echo.
FUNCTION_PrintSubheader("- folder_path: C:\\path\\to\\your\\measurement\\folders")
echo.
FUNCTION_PrintSubheader("- instrument: PDI_Hall_Setup")
echo.
FUNCTION_PrintSubheader("- users:")
echo.
FUNCTION_PrintSubheader("   username:")
echo.
FUNCTION_PrintSubheader("     base_url: http://your-server.com/nomad-oasis/api/v1")
echo.
FUNCTION_PrintSubheader("     upload_id: your-upload-id-here")
echo.
FUNCTION_PrintSubheader("")
echo.
FUNCTION_PrintSubheader("Please configure these settings in config.yml manually using any text editor:")
echo.
FUNCTION_PrintSubheader("  1. Open config.yml in Notepad or your preferred editor")
echo.
FUNCTION_PrintSubheader("  2. Replace placeholder values with your actual settings")
echo.
FUNCTION_PrintSubheader("  3. Save the file")
echo.

call :FUNCTION_PromptKeyToContinue

if exist "config.yml" (
    echo.
    FUNCTION_PrintSubheader("Current config.yml content:")
echo.
    type config.yml
    pause
)

goto MAIN_MENU

REM View Configuration Mode
:VIEW_CONFIG
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Current Configuration")
echo.

REM Run Python script to show current configuration
python hall_uploader.py --help

pause
goto MAIN_MENU

REM Exit gracefully
:EXIT
FUNCTION_ClearScreen()
FUNCTION_PrintHeader("Exiting")
echo.
FUNCTION_PrintSubheader("Thank you for using Hall PC -> NOMAD Uploader!")
echo.
FUNCTION_PrintSubheader("Have a great day!")
echo.
exit /b 0