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

$stages = @(
    @{ Name = "Bronze  (landing crudo)";        Module = "pipelines.bronze.ingest" },
    @{ Name = "Silver  (normaliza + dedupe)";   Module = "pipelines.silver.build_silver" },
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
    Write-Host "[$i/$total] $($stage.Name)" -ForegroundColor Cyan
    python -m $stage.Module
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FALLO en $($stage.Module) (codigo $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "Puertas de calidad (informativas, no rompen el pipeline)" -ForegroundColor Cyan
foreach ($house in @("bogota_auctions", "duran_subastas", "lefebre_subastas", "zorrilla_subastas", "morton_subastas")) {
    python pipelines/silver/quality_gates.py --house-slug $house
}

Write-Host ""
Write-Host "Pipeline completo." -ForegroundColor Green
Write-Host "Abre la app con:  python -m http.server -d data\gold\app   (y visita http://localhost:8000)" -ForegroundColor Green
