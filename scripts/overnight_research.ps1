# Deja la investigacion corriendo toda la noche, con reanudacion automatica.
#
# El investigador termina cuando agota su entrada, pero tambien puede morir por
# un corte de red: ya paso: 'URLError: getaddrinfo failed' tras 4 intentos. Sin
# supervision, la maquina se queda encendida sin hacer nada hasta la manana.
#
# Este script:
#   1. Comprueba que NO haya ya otro investigador vivo. Dos procesos escribiendo
#      el mismo JSONL corrompieron el diario (linea 394 partida) y dispararon el
#      rate limiting de Wikidata. Es la regla que mas veces se ha roto.
#   2. Mantiene el equipo despierto mientras dura (SetThreadExecutionState), sin
#      cambiar la configuracion de energia del usuario: al terminar se revierte
#      solo. Un powercfg global quedaria aplicado para siempre.
#   3. Reanuda tras un fallo, con espera creciente para no insistir contra una
#      API que nos esta frenando.
#   4. Deja un parte en data/enrichments/_overnight.log.
#
# Uso desde la raiz del repo:
#     .\scripts\overnight_research.ps1
#     .\scripts\overnight_research.ps1 -MaxHours 8 -Sleep 0.5

param(
    [double]$MaxHours = 10,
    [double]$Sleep = 0.5,
    [string]$Input = "data/enrichments/artist_research_priority.jsonl"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$log = Join-Path $root "data\enrichments\_overnight.log"
function Say($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

# --- 1. Un solo investigador -------------------------------------------
$vivos = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
           Where-Object { $_.CommandLine -like '*artist_master_web_research*' })
if ($vivos.Count -gt 0) {
    Say "ABORTA: ya hay $($vivos.Count) investigador(es) vivo(s): $($vivos.ProcessId -join ', ')"
    Say "Dos procesos escribiendo el mismo JSONL lo corrompen. Para el otro primero."
    exit 1
}

# --- 2. Mantener el equipo despierto -----------------------------------
# ES_CONTINUOUS(0x80000000) | ES_SYSTEM_REQUIRED(0x1). Sin ES_DISPLAY_REQUIRED:
# la pantalla puede apagarse, que no detiene nada y ahorra energia.
$sig = @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
$pwr = Add-Type -MemberDefinition $sig -Name Power -Namespace Win32 -PassThru
$null = $pwr::SetThreadExecutionState([uint32]"0x80000001")
Say "Equipo mantenido despierto (se revierte al salir)."

# --- 3. Bucle de reanudacion -------------------------------------------
$deadline = (Get-Date).AddHours($MaxHours)
$intento = 0
$espera = 60
try {
    while ((Get-Date) -lt $deadline) {
        $intento++
        Say "Arranque #$intento (sleep=$Sleep)"
        $p = Start-Process -FilePath "python" -PassThru -NoNewWindow -ArgumentList @(
            "scripts/artist_master_web_research.py",
            "--input", $Input,
            "--sleep", $Sleep
        )
        $p.WaitForExit()
        $code = $p.ExitCode

        $filas = 0
        $diario = Join-Path $root "data\enrichments\artist_web_research.jsonl"
        if (Test-Path $diario) { $filas = (Get-Content $diario | Measure-Object -Line).Lines }

        if ($code -eq 0) {
            Say "Terminado limpiamente. Filas en el diario: $filas"
            break
        }
        Say "Salio con codigo $code. Filas: $filas. Reintento en ${espera}s."
        Start-Sleep -Seconds $espera
        # Espera creciente hasta 15 min: si la API nos frena, insistir empeora.
        $espera = [Math]::Min($espera * 2, 900)
    }
    if ((Get-Date) -ge $deadline) { Say "Alcanzado el limite de $MaxHours h." }
}
finally {
    # ES_CONTINUOUS solo: libera el bloqueo y devuelve la politica normal.
    $null = $pwr::SetThreadExecutionState([uint32]"0x80000000")
    Say "Bloqueo de suspension liberado. Fin."
}
