<#
  start-dev.ps1 — sobe as ferramentas do Customer Intelligence Lab, cada uma na sua janela.

  Uso (a partir da raiz do repo ou de qualquer lugar):
    .\scripts\start-dev.ps1              # sobe o HUB: API (8000) + Frontend (5173)
    .\scripts\start-dev.ps1 -All         # sobe tudo: API + Frontend + Dagster (3000)
    .\scripts\start-dev.ps1 -Dagster     # sobe só o Dagster (3000)
    .\scripts\start-dev.ps1 -Api         # sobe só a API (8000)
    .\scripts\start-dev.ps1 -Front       # sobe só o Frontend (5173)

  Cada serviço abre numa janela PowerShell separada (não bloqueia este terminal).
  Para parar: feche a janela correspondente (ou Ctrl+C dentro dela).
  Nenhum serviço pede senha — tudo é local.
#>
param(
  [switch]$All,
  [switch]$Api,
  [switch]$Front,
  [switch]$Dagster
)

# Raiz do repo = pasta-mãe deste script
$Root = Split-Path -Parent $PSScriptRoot
$Api_    = Join-Path $Root 'backend'
$Front_  = Join-Path $Root 'frontend'
$Pipes_  = Join-Path $Root 'pipelines'

function Start-Service($title, $workdir, $command) {
  Write-Host "→ subindo $title ..." -ForegroundColor Cyan
  Start-Process powershell -ArgumentList @(
    '-NoExit','-Command',
    "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location '$workdir'; $command"
  )
}

# Se nenhum flag específico, o padrão é o HUB (API + Frontend)
$runApi   = $Api   -or $All -or (-not ($Api -or $Front -or $Dagster))
$runFront = $Front -or $All -or (-not ($Api -or $Front -or $Dagster))
$runDag   = $Dagster -or $All

if ($runApi) {
  Start-Service 'CIL · API :8000' $Api_ '.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000'
}
if ($runFront) {
  Start-Service 'CIL · Frontend :5173' $Front_ 'npm run dev'
}
if ($runDag) {
  Start-Service 'CIL · Dagster :3000' $Pipes_ '.\.venv\Scripts\dagster.exe dev -m crm_pipelines'
}

Write-Host ""
Write-Host "Pronto. Acesse:" -ForegroundColor Green
if ($runFront) { Write-Host "  Hub (app)   http://localhost:5173" }
if ($runApi)   { Write-Host "  API / docs  http://localhost:8000/docs" }
if ($runDag)   { Write-Host "  Dagster UI  http://localhost:3000" }
Write-Host "Nenhum deles pede senha (ambiente local)." -ForegroundColor DarkGray
