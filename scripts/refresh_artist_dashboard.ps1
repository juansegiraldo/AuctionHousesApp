# Toma una medicion nueva del maestro de artistas y abre el panel.
#
# Existe porque el boton "Refrescar" de la pagina solo puede RECARGAR el HTML
# que ya hay: una pagina no puede lanzar un proceso. La medicion la genera este
# script, y el HTML es un fichero estatico -- sin esto hay que acordarse de
# ejecutar el modulo a mano y el panel parece congelado.
#
# Uso desde la raiz del repo:
#     .\scripts\refresh_artist_dashboard.ps1
#     .\scripts\refresh_artist_dashboard.ps1 -NoOpen    # solo regenerar

param([switch]$NoOpen)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python -m pipelines.analytics.build_artist_master_report
    if ($LASTEXITCODE -ne 0) { throw "El generador fallo con codigo $LASTEXITCODE" }

    $out = Join-Path $root "data\gold\artist_master_report.html"
    if (-not $NoOpen) { Start-Process $out }
    Write-Host ""
    Write-Host "Panel: $out"
}
finally { Pop-Location }
