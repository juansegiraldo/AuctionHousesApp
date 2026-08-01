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
    @{ Name = "Enrich  (moneda -> EUR)";        Module = "pipelines.enrichments.currency_normalize" },
    @{ Name = "Enrich  (artistas)";             Module = "pipelines.enrichments.artist_canonicalize" },
    @{ Name = "Enrich  (categorias)";           Module = "pipelines.enrichments.category_tag" },
    @{ Name = "Gold    (agregados)";            Module = "pipelines.gold.build_gold" },
    @{ Name = "Gold    (artistas/categorias)";  Module = "pipelines.gold.build_insights" },
    @{ Name = "Informe (JSON + HTML)";          Module = "pipelines.analytics.report_gold" }
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
foreach ($house in @("bogota_auctions", "duran_subastas")) {
    python pipelines/silver/quality_gates.py --house-slug $house
}

Write-Host ""
Write-Host "Pipeline completo." -ForegroundColor Green
Write-Host "Abre el informe con:  start data\gold\analytics_report.html" -ForegroundColor Green
