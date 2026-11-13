# Reconstruye el pipeline entero en el orden correcto.
#
# Uso (desde la raiz del repo):
#   .\scripts\run_all.ps1
#
# Existe para que "reconstruir todo" sea un solo comando que no se pueda
# desordenar: las capas quedaron desincronizadas por ejecutarlas sueltas en
# fechas distintas (enrichments de marzo sobre un silver de mayo).
#
# Nota: las etapas se ejecutan como MODULOS (python -m), no como rutas de
# fichero, porque importan de pipelines.shared.

$ErrorActionPreference = "Stop"

# Cada corrida deja su log: sin el, un fallo de anoche no se puede reconstruir.
# No se usa Start-Transcript: en PowerShell 5.1 no recoge la salida de python.
New-Item -ItemType Directory -Force logs | Out-Null
$log = "logs\run_all_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss")
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

function Log([string]$message, $color = "Gray") {
    Write-Host $message -ForegroundColor $color
    Add-Content -Path $script:log -Value $message -Encoding UTF8
}

function Invoke-Python {
    # stderr tambien va al log: ahi salen los tracebacks. Con "Stop", PowerShell
    # 5.1 trata cada linea de stderr como un error fatal, asi que se baja a
    # "Continue" solo dentro de esta funcion; el fallo se decide por $LASTEXITCODE.
    $ErrorActionPreference = "Continue"
    & python @args 2>&1 | ForEach-Object { Log "$_" }
}

$stages = @(
    @{ Name = "Bronze  (landing crudo)";        Module = "pipelines.bronze.ingest" },
    # Registro duradero: sube a auction.raw_lots lo scrapeado. --best-effort
    # porque el pipeline debe poder correr sin red; la carga es idempotente.
    @{ Name = "Supabase (registro duradero)";   Module = "pipelines.bronze.load_raw"; Args = @("--best-effort") },
    @{ Name = "Silver  (normaliza + dedupe)";   Module = "pipelines.silver.build_silver" },
    # Corta la cadena si Silver tiene menos lotes de una casa que la base, que
    # nunca borra: es la senal de que una particion o un output se perdio.
    @{ Name = "Silver  (control de volumen)";   Module = "pipelines.silver.volume_guard" },
    # Va justo despues de build_silver: reescribe lots.jsonl anadiendo identidad
    # de artista, tipo de autoria y pais. Todo lo que viene detras lo da por hecho.
    @{ Name = "Silver  (artistas + paises)";    Module = "pipelines.silver.artist_resolve" },
    # Dimension exhaustiva: combina el maestro curado con todo fold de autor y
    # deja los dudosos en needs_web/ambiguous, sin promover texto crudo.
    @{ Name = "Gold    (maestro de artistas)";  Module = "pipelines.gold.build_artist_master" },
    @{ Name = "Enrich  (moneda -> EUR)";        Module = "pipelines.enrichments.currency_normalize" },
    @{ Name = "Enrich  (artistas)";             Module = "pipelines.enrichments.artist_canonicalize" },
    @{ Name = "Enrich  (categorias)";           Module = "pipelines.enrichments.category_tag" },
    @{ Name = "Gold    (agregados)";            Module = "pipelines.gold.build_gold" },
    @{ Name = "Gold    (artistas/categorias)";  Module = "pipelines.gold.build_insights" },
    @{ Name = "Informe (JSON)";                 Module = "pipelines.analytics.report_gold" },
    # La app (data/gold/app/): carpeta estatica sin CDN, valida como Artifact
    # de Claude y para Vercel. Ver el docstring del modulo.
    @{ Name = "App     (data/gold/app)";        Module = "pipelines.analytics.build_artifact" },
    # Panel de la capa FX: cuanto se desviaba la tasa unica mes a mes. Va al
    # final porque lee agg_house_metrics de Gold.
    @{ Name = "Informe (capa FX)";              Module = "pipelines.analytics.build_fx_report" }
)

$total = $stages.Count
$i = 0
foreach ($stage in $stages) {
    $i++
    Write-Host ""
    Log "[$i/$total] $($stage.Name)" Cyan
    $extra = @()
    if ($stage.Args) { $extra = $stage.Args }
    Invoke-Python -m $stage.Module @extra
    if ($LASTEXITCODE -ne 0) {
        Log "FALLO en $($stage.Module) (codigo $LASTEXITCODE)" Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
# Las casas salen del registro: la lista escrita a mano se quedaba atras al
# anadir una casa. Con --fail-on-violation las puertas SI rompen la corrida
# (las cinco pasan a 2026-11-13); se evaluan todas antes de salir.
Log "Puertas de calidad" Cyan
$failed = @()
foreach ($house in (Get-Content scraping\houses\registry.json -Raw | ConvertFrom-Json).houses.slug) {
    Invoke-Python pipelines/silver/quality_gates.py --house-slug $house --fail-on-violation
    if ($LASTEXITCODE -ne 0) { $failed += $house }
}
if ($failed.Count -gt 0) {
    Log "FALLO en las puertas de calidad: $($failed -join ", ")" Red
    exit 1
}

Write-Host ""
Log "Pipeline completo." Green
Write-Host "Abre la app con:  python -m http.server -d data\gold\app   (y visita http://localhost:8000)" -ForegroundColor Green
