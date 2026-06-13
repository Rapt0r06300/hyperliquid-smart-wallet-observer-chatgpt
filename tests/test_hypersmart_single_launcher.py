from pathlib import Path


def test_single_hypersmart_launcher_exists_and_forces_simulation_mode():
    launcher = Path("LANCER_HYPERSMART.cmd")
    text = launcher.read_text(encoding="utf-8")

    assert launcher.exists()
    assert "start_hypersmart_simulation.ps1" in text
    assert "HL_ENV=paper" in text
    assert "HL_ENABLE_MAINNET_EXECUTION=0" in text
    assert "HL_ENABLE_TESTNET_EXECUTION=0" in text
    assert "SIMULATION_ONLY_UNTIL_MANUAL_REVIEW" in text
    assert "HYPERSMART_SIMULATION_MAX_SIGNAL_AGE_MS=6000" in text
    assert "HYPERSMART_SIMULATION_ALLOW_ADD_AS_ENTRY=0" in text
    assert "HYPERSMART_SIMULATION_MIN_EDGE_BPS=35" in text
    assert "-Port 8794" in text
    assert "-IntervalSeconds 15" in text
    assert "-MaxLeaders 50" in text
    assert "-Interactive" in text
    assert "WindowStyle Hidden" not in text


def test_legacy_program_launchers_removed_to_keep_one_entrypoint():
    assert not Path("LANCER_HYPERSMART_SIMULATION.cmd").exists()
    assert not Path("DEMARRER_SIMULATION_LIVE_1000_USDT.cmd").exists()
    assert not Path("Ouvrir_Command_Center.bat").exists()


def test_runtime_session_database_is_ignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "runtime/" in gitignore
    assert "*.sqlite3" in gitignore


def test_start_script_initializes_everything_without_execution():
    text = Path("tools/start_hypersmart_simulation.ps1").read_text(encoding="utf-8")
    poll_loop_text = Path("tools/hypersmart_simulation_poll_loop.ps1").read_text(encoding="utf-8")

    assert "[int]$Port = 8794" in text
    assert "python -m hl_observer init-db" in text
    assert "python -m hl_observer reset-simulation-state --starting-equity 1000" in text
    assert "python -m hl_observer discover-markets --store --max-coins 80" in text
    assert "Nouvelle session simulation" in text
    assert "HL_ENABLE_MAINNET_EXECUTION" in text
    assert "HL_ENABLE_TESTNET_EXECUTION" in text
    assert "HL_DATABASE_URL" in text
    assert "runtime\\data" in text
    assert "hypersmart_simulation_session.sqlite3" in text
    assert "DB session simulation" in text
    assert "HL_LOG_LEVEL" in text
    assert 'HYPERSMART_SIMULATION_MIN_EDGE_BPS = "35"' in text
    assert "simulation-readiness --from-logs" in text
    assert "hypersmart_simulation_poll_loop.ps1" in text
    assert "hl_observer live-user-fills-scan" in text
    assert "RestartExisting" in text
    assert "Arret ancien processus HyperSmart" in text
    assert "Waiting for old HyperSmart runtime processes to exit" in text
    assert "FreshWindowMinutes" in text
    assert "MaxRuns = 5760" in poll_loop_text
    assert "hypersmart_simulation_poll_loop.lock" in poll_loop_text
    assert "LeadersPerPoll" in text
    assert '"-LeadersPerPoll", "10"' in text
    assert "--leader-offset $leaderOffset" in poll_loop_text
    assert '"-PublicTradeScanEveryPolls", "1"' in text
    assert '"-PublicTradeCoins", "AUTO"' in text
    assert '"-PublicTradeMaxCoins", "40"' in text
    assert '"-PublicTradeMaxWallets", "10000"' in text
    assert '"-UserFillsMaxLiveAgeMs", "120000"' in text
    assert "UserFillsMaxLiveAgeMs" in poll_loop_text
    assert "--max-live-fill-age-ms $UserFillsMaxLiveAgeMs" in poll_loop_text
    assert "throughput-plan" in poll_loop_text
    assert "fresh-scan-plan --network-read" in poll_loop_text
    assert "fresh-data-plan --network-read" in poll_loop_text
    assert "opportunity-report --active-window-seconds 120" in poll_loop_text
    assert "warehouse-report --fresh-window-seconds 120" in poll_loop_text
    assert "$logsToSendDir" in poll_loop_text
    assert "simulation-readiness --from-logs" in poll_loop_text
    assert "[Math]::Min($MaxLeaders, 10)" in poll_loop_text
    assert "Commande [R=status, Q=stop]" in text
    assert "Stop-HyperSmartRuntime" in text
    assert "Start-Process -NoNewWindow" in text
    assert "RedirectStandardOutput" in text
    assert "RedirectStandardError" in text
    assert "Start-Process -WindowStyle Hidden" not in text
    assert "/static/simulation_v2.html" in text
    assert "/exchange" not in text


def test_poll_loop_runs_public_trades_discovery_before_copy_run():
    text = Path("tools/hypersmart_simulation_poll_loop.ps1").read_text(encoding="utf-8")

    assert "live-public-scan" in text
    assert "--max-coins $PublicTradeMaxCoins" in text
    assert "--network-read" in text
    assert "--store" in text
    assert "copy-run" in text
    assert "Write-CommandOutput" in text
    assert "suppressed $suppressedHttpOk successful /info HTTP 200 log lines" in text
    assert text.index("live-public-scan") < text.index("copy-run")
    assert "/exchange" not in text
