@echo off
chcp 65001 >nul
setlocal
echo ============================================================
echo    Ton PC peut-il faire tourner un node dYdX 24/7 ?
echo ============================================================
echo.
echo Exigences dYdX (full node) :
echo    - CPU  : 16 coeurs recommandes
echo    - RAM  : 128 Go recommandes
echo    - Disque libre : ~500 Go (SSD NVMe rapide)
echo.
echo Voici TON PC :
echo.

powershell -NoProfile -Command ^
  "$cs=Get-CimInstance Win32_ComputerSystem;" ^
  "$ram=[math]::Round($cs.TotalPhysicalMemory/1GB);" ^
  "$cores=(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum;" ^
  "$disk=[math]::Round((Get-PSDrive C).Free/1GB);" ^
  "function V($ok){ if($ok){'  [OK]'}else{'  [INSUFFISANT]'} };" ^
  "Write-Host ('   CPU (coeurs logiques) : ' + $cores + (V($cores -ge 16)));" ^
  "Write-Host ('   RAM (Go)              : ' + $ram + (V($ram -ge 64)));" ^
  "Write-Host ('   Disque C libre (Go)   : ' + $disk + (V($disk -ge 500)));" ^
  "Write-Host '';" ^
  "if(($ram -ge 64) -and ($cores -ge 12) -and ($disk -ge 500)){" ^
  "  Write-Host '   VERDICT : ton PC PEUT probablement tenir (via WSL2/Docker).' -ForegroundColor Green;" ^
  "  Write-Host '   Dis-le moi et je te guide pour l installation Linux dans Windows.';" ^
  "} else {" ^
  "  Write-Host '   VERDICT : ton PC est en-dessous des besoins d un node 24/7.' -ForegroundColor Yellow;" ^
  "  Write-Host '   -> Mieux vaut un serveur loue dans le cloud, OU rester sans node';" ^
  "  Write-Host '      (le bot fonctionne deja sans, c est juste un turbo en moins).';" ^
  "}"

echo.
echo ------------------------------------------------------------
echo Rappel : tu n'as PAS besoin du node pour que le bot marche.
echo Le node = uniquement le "firehose" (turbo de scan). Sans lui,
echo le bot prend quand meme des decisions via LANCER_HYPERSMART.cmd.
echo ------------------------------------------------------------
echo.
pause
endlocal
