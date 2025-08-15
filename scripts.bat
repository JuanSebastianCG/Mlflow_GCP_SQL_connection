@echo off
SET TASK=%1

IF "%TASK%"=="" GOTO Help
IF "%TASK%"=="startPoryect" GOTO startPoryect
IF "%TASK%"=="Create-Venv" GOTO CreateVenv
IF "%TASK%"=="Install" GOTO InstallDependencies
IF "%TASK%"=="Clean" GOTO Clean
IF "%TASK%"=="Docker-Build" GOTO DockerBuild
IF "%TASK%"=="Docker-Up" GOTO DockerUp
IF "%TASK%"=="Docker-Down" GOTO DockerDown
GOTO Help

:startPoryect
    REM Verifica si .env ya existe, si no, lo copia
    if not exist .env (
        echo Copying .env.example to .env...
        copy .env.example .env
    ) else (
        echo .env already exists.
    )
    REM Verifica si config.yaml ya existe, si no, lo copia
    if not exist Model\configs\config.yaml (
        echo Copying Model\configs\config.example.yaml to Model\configs\config.yaml...
        copy Model\configs\config.example.yaml Model\configs\config.yaml
    ) else (
        echo config.yaml already exists.
    )
    REM Crear entorno virtual
    GOTO CreateVenv

:CreateVenv
    REM Verifica si el entorno virtual ya existe, si no, lo crea
    if not exist .venv (
        echo Creating virtual environment...
        python.exe -m venv .venv
        echo Virtual environment created.
    ) else (
        echo Virtual environment already exists.
    )
    GOTO InstallDependencies

:InstallDependencies
    echo Activating virtual environment and installing dependencies...
    call .venv\Scripts\activate
    python.exe -m pip install --upgrade pip
    pip install -r requirements.txt
    echo Dependencies installed.
    GOTO End

:Clean
    echo Cleaning up old files and Python cache...
    
    REM Limpiar carpetas __pycache__ en todo el proyecto
    for /d /r %%d in (__pycache__) do (
        echo Removing %%d
        rmdir /S /Q "%%d"
    )

    REM Eliminar el archivo logs
    if exist resources\logs\*.log (
        del /S /Q resources\logs\*.log
        echo Logs cleaned.
    )

    REM Eliminar archivos de notebooks y temporales en ejecución
    if exist execution\notebooks\*.ipynb (
        del /S /Q execution\notebooks\*.ipynb
        echo Jupyter notebooks cleaned.
    )

    echo Clean-up process completed.
    GOTO End

:DockerBuild
    echo Building Docker image...
    docker-compose build
    echo Docker image built.
    GOTO End

:DockerUp
    echo Starting Docker containers...
    docker-compose up -d
    echo Docker containers started.
    GOTO End

:DockerDown
    echo Stopping and removing Docker containers...
    docker-compose down
    echo Docker containers stopped and removed.
    GOTO End

:Help
    echo Available commands:
    echo   startPoryect    - Start the project, setup environment, and dependencies
    echo   Create-Venv     - Create virtual environment
    echo             - Install dependencies
    echo   Clean           - Remove temporary files
    echo   Docker-Build    - Build Docker image
    echo   Docker-Up       - Start Docker containers
    echo   Docker-Down     - Stop Docker containers
    echo   help            - Show this help message
    GOTO End

:End
exit /b 0

# comand to run the script 
# .\scripts.bat Help
# .\scripts.bat Clean
# .\scripts.bat Docker-Build
# .\scripts.bat Docker-Up
# .\scripts.bat Docker-Down
# .\scripts.bat Install
# .\scripts.bat Create-Venv
# .\scripts.bat startPoryect
