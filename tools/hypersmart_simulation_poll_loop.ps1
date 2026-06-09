param(
    [string]$Root,
    [int]$IntervalSeconds = 60,
    [int]$MaxLeaders = 50,
    [int]$LeadersPerPoll = 10,
    [int]$BackfillDays = 1,
    [int]$FreshWindowMinutes = 15,
    [int]$MaxPages = 1,
    [string]$PublicTradeCoins = "AUTO",
    [int]$PublicTradeMaxCoins = 40,
    [int]$PublicTradeScanSeconds = 8,
    [int]$PublicTradeMaxWallets = 10000,
    [int]$PublicTradeScanEveryPolls = 1,
    [int]$UserFillsMaxLiveAgeMs = 120000,
    [int]$MaxRuns = 5760
)

$ErrorActionPreference = "Continue"
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $PSScriptRoot
}

$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logsToSendDir = Join-Path $logDir ("logs " + [char]0x00E0 + " envoyer")
$logPath = Join-Path $logDir "hypersmart_simulation_live.log"
$lockPath = Join-Path $logDir "hypersmart_simulation_poll_loop.lock"

function Write-LoopLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        Add-Content -LiteralPath $logPath -Value "[$stamp] $Message" -ErrorAction Stop
    } catch {
        Write-Host "[HyperSmart][poller-log-warning] $($_.Exception.Message)"
    }
}

function Write-CommandOutput {
    param(
        [object[]]$Lines,
        [string]$Label
    )
    $suppressedHttpOk = 0
    foreach ($line in $Lines) {
        $text = [string]$line
        if ($text -like '*"logger": "httpx"*' -and $text -like '*HTTP/1.1 200 OK*') {
            $suppressedHttpOk += 1
            continue
        }
        if ([string]::IsNullOrWhiteSpace($text)) {
            continue
        }
        Write-LoopLog $text
    }
    if ($suppressedHttpOk -gt 0) {
        Write-LoopLog "${Label}: suppressed $suppressedHttpOk successful /info HTTP 200 log lines"
    }
}

try {
    $script:PollerLockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch {
    Write-LoopLog "Another simulation poll loop already owns the runtime lock. Exiting without duplicate scanner."
    exit 0
}

Write-LoopLog "Simulation poll loop started. root=$Root interval=$IntervalSeconds pool=$MaxLeaders leadersPerPoll=$LeadersPerPoll maxRuns=$MaxRuns maxLiveFillAgeMs=$UserFillsMaxLiveAgeMs"

for ($i = 1; $i -le $MaxRuns; $i++) {
    $safeLeadersPerPoll = [Math]::Max(1, [Math]::Min($LeadersPerPoll, [Math]::Min($MaxLeaders, 10)))
    $leaderOffset = (($i - 1) * $safeLeadersPerPoll) % [Math]::Max(1, $MaxLeaders)
    Write-LoopLog "poll $i/$MaxRuns starting offset=$leaderOffset batch=$safeLeadersPerPoll pool=$MaxLeaders"
    try {
        Push-Location $Root
        $planOutput = & python -m hl_observer throughput-plan --network-read --ws --requested-wallets $MaxLeaders --max-leaders-per-run $safeLeadersPerPoll --public-trade-wallets $PublicTradeMaxWallets 2>&1
        Write-CommandOutput -Lines $planOutput -Label "throughput-plan"
        $freshPlanOutput = & python -m hl_observer fresh-scan-plan --network-read --requested-wallets 50000 --cycle-seconds $IntervalSeconds --leaders-per-stream $safeLeadersPerPoll --public-trade-wallets $PublicTradeMaxWallets 2>&1
        Write-CommandOutput -Lines $freshPlanOutput -Label "fresh-scan-plan"
        $freshDataOutput = & python -m hl_observer fresh-data-plan --network-read --requested-wallets 50000 --coins $PublicTradeCoins --max-coins $PublicTradeMaxCoins --max-hot-wallets $safeLeadersPerPoll --gap-recovery 2>&1
        Write-CommandOutput -Lines $freshDataOutput -Label "fresh-data-plan"
        $safeScanEvery = [Math]::Max(1, $PublicTradeScanEveryPolls)
        if ($i -eq 1 -or ($i % $safeScanEvery) -eq 0) {
            Write-LoopLog "Running live-public-scan for candidate discovery..."
            $wsOutput = & python -m hl_observer live-public-scan --network-read --store --duration-seconds $PublicTradeScanSeconds --coins $PublicTradeCoins --max-coins $PublicTradeMaxCoins --max-wallets $PublicTradeMaxWallets --promote-top $MaxLeaders --no-report 2>&1
            Write-CommandOutput -Lines $wsOutput -Label "live-public-scan"
        } else {
            Write-LoopLog "Skipping live-public-scan to maximize copying frequency..."
        }
        Write-LoopLog "Running shortlist userFills WebSocket monitor for fresh bounded deltas..."
        $userFillsOutput = & python -m hl_observer live-user-fills-scan --network-read --store --duration-seconds 10 --max-users $safeLeadersPerPoll --leader-offset $leaderOffset --max-live-fill-age-ms $UserFillsMaxLiveAgeMs 2>&1
        Write-CommandOutput -Lines $userFillsOutput -Label "live-user-fills-scan"
        $syncInterval = 20
        $forceNetworkRead = ($i -eq 1) -or (($i % $syncInterval) -eq 0)
        if ($forceNetworkRead) {
            Write-LoopLog "Running copy-run with network-read for gap recovery and sync..."
            $output = & python -m hl_observer copy-run --interval $IntervalSeconds --dry-run --network-read --copy-max-leaders $safeLeadersPerPoll --leader-offset $leaderOffset --backfill-days $BackfillDays --fresh-window-minutes $FreshWindowMinutes --max-pages $MaxPages --no-report 2>&1
        } else {
            Write-LoopLog "Running copy-run with local database only (real-time WebSocket updates)..."
            $output = & python -m hl_observer copy-run --interval $IntervalSeconds --dry-run --copy-max-leaders $safeLeadersPerPoll --leader-offset $leaderOffset --backfill-days $BackfillDays --fresh-window-minutes $FreshWindowMinutes --max-pages $MaxPages --no-report 2>&1
        }
        Write-CommandOutput -Lines $output -Label "copy-run"
        $opportunityOutput = & python -m hl_observer opportunity-report --active-window-seconds 120 --consensus-window-seconds 4 --min-wallets 2 --max-deltas 5000 --max-opportunities 10 2>&1
        Write-CommandOutput -Lines $opportunityOutput -Label "opportunity-report"
        $readinessOutput = & python -m hl_observer simulation-readiness --from-logs "$logsToSendDir" --fresh-window-seconds 120 2>&1
        Write-CommandOutput -Lines $readinessOutput -Label "simulation-readiness"
        $warehouseOutput = & python -m hl_observer warehouse-report --fresh-window-seconds 120 2>&1
        Write-CommandOutput -Lines $warehouseOutput -Label "warehouse-report"
        Pop-Location
    } catch {
        Write-LoopLog "poll failed: $($_.Exception.Message)"
        try { Pop-Location } catch {}
    }
    if ($i -lt $MaxRuns) {
        Start-Sleep -Seconds $IntervalSeconds
    }
}

Write-LoopLog "Simulation poll loop finished."
