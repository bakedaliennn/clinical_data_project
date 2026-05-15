<#
.SYNOPSIS
    Prepara el entorno local de SaludMX Analytics Pipeline.

.DESCRIPTION
    Automatiza lo que se puede repetir sin riesgo:
    - verifica Docker y Conda;
    - crea .env desde .env.example si falta;
    - crea el entorno Conda 'saludmx' si no existe;
    - instala requirements.txt en el entorno;
    - levanta PostgreSQL + PgAdmin + Dagster con docker compose;
    - aplica migraciones Alembic;
    - corre un smoke test mínimo.

    No borra datos ni ejecuta `docker compose down -v`.

.EXAMPLE
    .\prepare_local.ps1

.EXAMPLE
    .\prepare_local.ps1 -RunTests

.EXAMPLE
    .\prepare_local.ps1 -SkipDeps -SkipDocker
#>

param(
    [string]$CondaEnv = "saludmx",
    [switch]$SkipDeps,
    [switch]$SkipDocker,
    [switch]$SkipMigrations,
    [switch]$SkipSmoke,
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$ComposeFile = Join-Path $Repo "platform\orchestration\docker-compose.yml"
$EnvFile = Join-Path $Repo ".env"
$EnvExample = Join-Path $Repo ".env.example"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-CommandPath {
    param(
        [string]$Name,
        [string[]]$Candidates
    )

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    foreach ($candidate in $Candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "No encontre '$Name'. Instala la herramienta o agregala al PATH."
}

function Invoke-CondaRun {
    param(
        [string]$CondaExe,
        [string]$EnvName,
        [string[]]$CommandArgs
    )

    & $CondaExe run -n $EnvName --no-capture-output $CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo comando en Conda env '$EnvName': $($CommandArgs -join ' ')"
    }
}

Set-Location -LiteralPath $Repo

Write-Step "Validando archivos base"
if (-not (Test-Path -LiteralPath $EnvFile)) {
    if (-not (Test-Path -LiteralPath $EnvExample)) {
        throw "No existe .env ni .env.example en $Repo."
    }
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host "Cree .env desde .env.example. Revisa rutas antes de correr pipelines reales." -ForegroundColor Yellow
} else {
    Write-Host ".env encontrado."
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "No encontre docker-compose.yml en $ComposeFile."
}

Write-Step "Validando Conda"
$CondaExe = Resolve-CommandPath -Name "conda" -Candidates @(
    "C:\ProgramData\miniconda3\Scripts\conda.exe",
    "C:\ProgramData\miniconda3\condabin\conda.bat",
    "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
    "$env:USERPROFILE\anaconda3\Scripts\conda.exe"
)
Write-Host "Conda: $CondaExe"

$envInfoRaw = & $CondaExe env list --json
if ($LASTEXITCODE -ne 0) {
    throw "No pude listar entornos Conda."
}
$envInfo = ($envInfoRaw | Out-String | ConvertFrom-Json)
$envExists = $false
foreach ($envPath in $envInfo.envs) {
    if ((Split-Path $envPath -Leaf) -eq $CondaEnv) {
        $envExists = $true
        break
    }
}

if (-not $envExists) {
    Write-Host "El entorno '$CondaEnv' no existe. Creandolo desde environment.yml..." -ForegroundColor Yellow
    & $CondaExe env create -f (Join-Path $Repo "environment.yml")
    if ($LASTEXITCODE -ne 0) {
        throw "No pude crear el entorno Conda '$CondaEnv'."
    }
} else {
    Write-Host "Entorno Conda '$CondaEnv' encontrado."
}

if (-not $SkipDeps) {
    Write-Step "Instalando dependencias pip"
    Invoke-CondaRun -CondaExe $CondaExe -EnvName $CondaEnv -CommandArgs @(
        "python", "-m", "pip", "install", "-r", (Join-Path $Repo "requirements.txt")
    )
}

if (-not $SkipDocker) {
    Write-Step "Validando Docker"
    $DockerExe = Resolve-CommandPath -Name "docker" -Candidates @(
        "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    )
    & $DockerExe info | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker no responde. Abre Docker Desktop, espera a que arranque y vuelve a correr este script."
    }

    Write-Step "Levantando PostgreSQL + PgAdmin + Dagster"
    & $DockerExe compose --env-file $EnvFile -f $ComposeFile up -d --build
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo docker compose up."
    }
}

if (-not $SkipMigrations) {
    Write-Step "Aplicando migraciones Alembic (schema Star Schema)"
    Invoke-CondaRun -CondaExe $CondaExe -EnvName $CondaEnv -CommandArgs @("alembic", "upgrade", "head")
}

if (-not $SkipSmoke) {
    Write-Step "Corriendo smoke test de conectividad"
    Invoke-CondaRun -CondaExe $CondaExe -EnvName $CondaEnv -CommandArgs @(
        "python", "-c",
        "import duckdb; import pandas; import dagster; print('Smoke test OK: duckdb', duckdb.__version__, '| pandas', pandas.__version__, '| dagster', dagster.__version__)"
    )
}

if ($RunTests) {
    Write-Step "Corriendo pytest"
    Invoke-CondaRun -CondaExe $CondaExe -EnvName $CondaEnv -CommandArgs @("pytest", "tests")
}

Write-Host ""
Write-Host "Listo. Servicios locales preparados para SaludMX Analytics Pipeline." -ForegroundColor Green
Write-Host "Dagster UI : http://localhost:3000"
Write-Host "PgAdmin 4  : http://localhost:5050  (admin@saludmx.org / adminpass)"
Write-Host "PostgreSQL : localhost:5432  DB=saludmx_dw"
