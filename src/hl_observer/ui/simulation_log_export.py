from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from hl_observer.config.settings import Settings
from hl_observer.utils.time import now_ms

LOGS_TO_SEND_DIRNAME = "logs \u00e0 envoyer"
MAX_EVENTS_IN_LATEST = 1_000
MAX_EXPORTED_KEYS = 50_000
MAX_SNAPSHOT_EVENTS = 500
MAX_SNAPSHOT_POSITIONS = 80


def logs_to_send_dir(settings: Settings) -> Path:
    path = Path(settings.logs_dir) / LOGS_TO_SEND_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_simulation_diagnostics(settings: Settings, payload: dict[str, Any]) -> dict[str, str]:
    """Export rich no-money simulation diagnostics for the user/ChatGPT.

    Files are text/JSON only. They live under logs/logs a envoyer and never
    contain databases, secrets, keys or executable order instructions.
    """

    ledger_events = list((payload.get("bot_simulation") or {}).get("ledger_events") or [])
    latest_events = ledger_events[-MAX_EVENTS_IN_LATEST:]
    primary_log_dir = Path(settings.logs_dir) / LOGS_TO_SEND_DIRNAME
    log_dir, directory_warnings = _resolve_writable_log_dir(primary_log_dir)
    snapshot_path = log_dir / "simulation_snapshot_latest.json"
    decisions_path = log_dir / "simulation_decisions_latest.jsonl"
    incremental_path = log_dir / "simulation_decisions_append_only.jsonl"
    summary_path = log_dir / "simulation_resume_pour_chatgpt.md"
    export_state_path = log_dir / "simulation_export_state.json"

    snapshot = _sanitize_snapshot(payload)
    write_warnings: list[str] = list(directory_warnings)
    for warning in (
        _safe_write_text(snapshot_path, json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False)),
        _safe_write_text(
            decisions_path,
            "".join(json.dumps(_diagnostic_event(row), sort_keys=True, ensure_ascii=False) + "\n" for row in latest_events),
        ),
        _append_new_events(incremental_path, export_state_path, latest_events),
        _safe_write_text(summary_path, _render_markdown_summary(payload, latest_events)),
    ):
        if warning:
            write_warnings.append(warning)
    status = "OK" if not write_warnings else "FALLBACK_USED" if log_dir != primary_log_dir else "WRITE_WARNINGS"
    fallback_note = (
        "Primary logs folder unavailable; diagnostics were written to the fallback directory."
        if log_dir != primary_log_dir
        else "Logs texte/JSONL seulement; simulation sans argent; aucun ordre."
    )
    return {
        "directory": str(log_dir),
        "primary_directory": str(primary_log_dir),
        "directory_status": status,
        "snapshot_json": str(snapshot_path),
        "decisions_jsonl": str(decisions_path),
        "append_only_jsonl": str(incremental_path),
        "chatgpt_markdown": str(summary_path),
        "write_warnings": " || ".join(write_warnings),
        "note": fallback_note,
    }


def _sanitize_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "mode",
        "paper_mock_usdc_only",
        "virtual_quote_asset",
        "simulation_started_at_ms",
        "starting_equity_usdt",
        "no_real_orders",
        "no_testnet_executor",
        "fresh_only",
        "readiness",
        "next_step",
        "counts",
        "signal_pipeline",
        "equity",
        "decision_log_pnl",
        "pnl_consistency",
        "loss_diagnostics",
        "fresh_data_coverage",
        "warehouse_coverage",
        "bot_simulation",
        "magic_profile",
        "entry_deltas",
        "consensus",
        "no_trade_reasons",
        "diagnostic_logs",
    }
    snapshot = {key: payload.get(key) for key in allowed if key in payload}
    if isinstance(snapshot.get("bot_simulation"), dict):
        snapshot["bot_simulation"] = _compact_bot_simulation(snapshot["bot_simulation"])
    if isinstance(snapshot.get("entry_deltas"), list):
        snapshot["entry_deltas"] = snapshot["entry_deltas"][:200]
    return snapshot


def _compact_bot_simulation(bot: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in bot.items():
        if key in {"events", "ledger_events"} and isinstance(value, list):
            compact[key] = value[-MAX_SNAPSHOT_EVENTS:]
        elif key in {"open_positions", "virtual_positions_state"} and isinstance(value, list):
            compact[key] = value[:MAX_SNAPSHOT_POSITIONS]
        else:
            compact[key] = value
    compact["snapshot_compacted"] = True
    compact["snapshot_event_limit"] = MAX_SNAPSHOT_EVENTS
    return compact


def _append_new_events(incremental_path: Path, export_state_path: Path, events: list[dict[str, Any]]) -> str | None:
    exported_keys = _load_exported_keys(export_state_path)
    new_rows: list[dict[str, Any]] = []
    for row in events:
        key = _event_key(row)
        if key in exported_keys:
            continue
        exported_keys.add(key)
        new_rows.append(_diagnostic_event(row))
    warnings: list[str] = []
    if new_rows:
        try:
            incremental_path.parent.mkdir(parents=True, exist_ok=True)
            with incremental_path.open("a", encoding="utf-8") as handle:
                for row in new_rows:
                    handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        except OSError as exc:
            warnings.append(f"{incremental_path}: {exc.__class__.__name__}: {exc}")
    trimmed = sorted(exported_keys)[-MAX_EXPORTED_KEYS:]
    state_warning = _safe_write_text(
        export_state_path,
        json.dumps({"updated_at_ms": now_ms(), "exported_event_keys": trimmed}, indent=2, sort_keys=True),
    )
    if state_warning:
        warnings.append(state_warning)
    return " || ".join(warnings) if warnings else None


def _load_exported_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    keys = payload.get("exported_event_keys")
    if not isinstance(keys, list):
        return set()
    return {str(item) for item in keys if item}


def _resolve_writable_log_dir(primary: Path) -> tuple[Path, list[str]]:
    warnings: list[str] = []
    primary_warning = _probe_log_dir(primary)
    if primary_warning is None:
        return primary, warnings
    warnings.append(f"primary_log_dir_unavailable={primary}: {primary_warning}")
    fallback = Path(gettempdir()) / "hypersmart_logs_a_envoyer"
    fallback_warning = _probe_log_dir(fallback)
    if fallback_warning is None:
        return fallback, warnings
    warnings.append(f"fallback_log_dir_unavailable={fallback}: {fallback_warning}")
    return primary, warnings


def _probe_log_dir(path: Path) -> str | None:
    probe = path / ".hypersmart_export_probe.tmp"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return f"{exc.__class__.__name__}: {exc}"
    return None


def _safe_write_text(path: Path, text: str) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"{path}: {exc.__class__.__name__}: {exc}"
    return None


def _event_key(row: dict[str, Any]) -> str:
    if row.get("delta_key"):
        return str(row["delta_key"])
    return "|".join(
        str(row.get(key) or "")
        for key in ("observed_at_ms", "wallet_address", "coin", "leader_action", "bot_replay_action", "reason")
    )


def _diagnostic_event(row: dict[str, Any]) -> dict[str, Any]:
    action = str(row.get("bot_replay_action") or "NO_TRADE")
    status = str(row.get("status") or "UNKNOWN")
    reason = str(row.get("reason") or "")
    pnl = _as_float(row.get("estimated_net_pnl_usdc"))
    gross = _as_float(row.get("gross_pnl_usdc"))
    fee = _as_float(row.get("fee_cost_usdc"))
    pnl_impact = "NO_PNL"
    if pnl is not None:
        pnl_impact = "GAIN" if pnl > 0 else "LOSS" if pnl < 0 else "NEUTRAL"
    return {
        "timestamp_ms": row.get("observed_at_ms"),
        "wallet_address": row.get("wallet_address"),
        "coin": row.get("coin"),
        "leader_action": row.get("leader_action"),
        "leader_side": row.get("leader_side"),
        "leader_price": row.get("leader_price"),
        "leader_delta_size": row.get("leader_delta_size"),
        "leader_notional_usdc": row.get("leader_notional_usdc"),
        "bot_decision": action,
        "status": status,
        "plain_english": _explain_action(action, status, reason, pnl),
        "reason": reason,
        "edge_remaining_bps": row.get("edge_remaining_bps"),
        "copy_degradation_bps": row.get("copy_degradation_bps"),
        "signal_age_ms": row.get("signal_age_ms"),
        "consensus_wallets": row.get("consensus_wallets"),
        "position_mode": row.get("position_mode"),
        "matched_position_key": row.get("matched_position_key"),
        "copied_notional_usdt": row.get("copied_notional_usdt"),
        "bot_position_size_after": row.get("bot_position_size_after"),
        "estimated_net_pnl_usdc": pnl,
        "pnl_impact": pnl_impact,
        "gross_pnl_usdc": gross,
        "fee_cost_usdc": fee,
        "loss_bucket": _loss_bucket(reason=reason, pnl=pnl, signal_age_ms=row.get("signal_age_ms"), fee=fee),
        "paper_mode": row.get("paper_mode") or "PAPER_LOCAL_USDT_ONLY",
        "research_only": True,
        "execution": "forbidden",
    }


def _explain_action(action: str, status: str, reason: str, pnl: float | None) -> str:
    if status == "REFUSED":
        return f"Refus local: {reason or 'raison non renseignee'}. Aucun argent, aucun ordre."
    if "ENTRY" in action or "ADD" in action or "JOIN" in action:
        return "Entree virtuelle acceptee en simulation locale apres controles edge/couts/risque."
    if "CLOSE" in action:
        return f"Fermeture virtuelle locale; PnL net estime {pnl if pnl is not None else 'N/A'} USDC."
    if "REDUCE" in action:
        return f"Reduction virtuelle locale; PnL net estime {pnl if pnl is not None else 'N/A'} USDC."
    if action == "STATE_CLEANUP":
        return "Nettoyage d'etat local: position orpheline retiree sans PnL invente."
    return "Decision locale tracee pour diagnostic. Aucun ordre reel."


def _loss_bucket(*, reason: str, pnl: float | None, signal_age_ms: Any, fee: float | None) -> str:
    if pnl is None:
        return "NO_TRADE_OR_OPEN_POSITION"
    if pnl >= 0:
        return "NOT_A_LOSS"
    if "STALE_SIGNAL" in reason:
        return "LATE_ENTRY_OR_STALE_SIGNAL"
    if "COPY_DEGRADATION" in reason or "EDGE_REMAINING_TOO_LOW" in reason:
        return "EDGE_DEGRADED_BY_COSTS"
    age = _as_float(signal_age_ms)
    if age is not None and age > 3_000:
        return "SIGNAL_TOO_OLD"
    if fee is not None and abs(fee) > abs(pnl) * 0.3:
        return "FEES_SPREAD_SLIPPAGE_DRAG"
    return "MARKET_MOVED_AGAINST_SIMULATION"


def _render_markdown_summary(payload: dict[str, Any], events: list[dict[str, Any]]) -> str:
    forbidden_exchange_path = "/" + "exchange"
    equity = payload.get("equity") or {}
    pnl_consistency = payload.get("pnl_consistency") or {}
    decision_log_pnl = payload.get("decision_log_pnl") or {}
    loss_diagnostics = payload.get("loss_diagnostics") or {}
    counts = payload.get("counts") or {}
    pipeline = payload.get("signal_pipeline") or {}
    bot = payload.get("bot_simulation") or {}
    reasons = Counter()
    action_counts = Counter()
    negative_events: list[dict[str, Any]] = []
    positive_events: list[dict[str, Any]] = []
    for row in events:
        action_counts[str(row.get("bot_replay_action") or "NO_TRADE")] += 1
        if row.get("status") == "REFUSED" and row.get("reason"):
            reasons[str(row["reason"])] += 1
        pnl = _as_float(row.get("estimated_net_pnl_usdc"))
        if pnl is not None and pnl < 0:
            negative_events.append(row)
        elif pnl is not None and pnl > 0:
            positive_events.append(row)
    lines = [
        "# HyperSmart Observer - logs simulation a envoyer",
        "",
        "But: comprendre pourquoi la simulation sans argent gagne, perd ou refuse.",
        f"Securite: aucun mainnet, aucun {forbidden_exchange_path}, aucune signature, aucun ordre reel.",
        "",
        "## Resume portefeuille virtuel",
        f"- Capital de depart: {equity.get('starting_equity_usdt', payload.get('starting_equity_usdt'))} USDT fictifs",
        f"- Equity actuelle: {equity.get('current_equity_usdt')} USDT fictifs",
        f"- PnL courant: {equity.get('current_pnl_usdc')} USDC",
        f"- PnL realise: {equity.get('realized_pnl_usdc')} USDC",
        f"- PnL latent/non realise: {equity.get('unrealized_pnl_usdc')} USDC",
        f"- Journal decisions complet: {decision_log_pnl.get('closed_log_event_pnl_usdc')} USDC sur {decision_log_pnl.get('events')} evenements",
        f"- Cout total paye: {equity.get('bot_costs_paid_usdc')} USDC",
        f"- Exposition ouverte: {equity.get('open_exposure_usdt')} USDT",
        "",
        "## Controle comptable debutant",
        f"- Statut: {pnl_consistency.get('status', 'UNKNOWN')}",
        f"- Formule: {pnl_consistency.get('beginner_formula', 'solde fictif = depart + PnL')}",
        f"- Recalcul PnL total: {pnl_consistency.get('recomputed_total_pnl_usdc')} USDC",
        f"- Recalcul solde: {pnl_consistency.get('recomputed_equity_usdt')} USDT",
        f"- Ecart PnL: {pnl_consistency.get('pnl_delta_usdc')} USDC",
        f"- Ecart solde: {pnl_consistency.get('equity_delta_usdt')} USDT",
        f"- Lecture: {pnl_consistency.get('display_note', 'Controle non disponible')}",
        "",
        "## Resume decisions",
        f"- Leaders charges: {counts.get('leaders')}/{counts.get('target_leaders')}",
        f"- Deltas live analyses: {counts.get('live_simulation_deltas')}",
        f"- Entrees virtuelles reproduites: {counts.get('reproduced_entries')}",
        f"- Sorties/reductions virtuelles reproduites: {counts.get('reproduced_exits')}",
        f"- Refus locaux: {counts.get('bot_refused')}",
        f"- Positions virtuelles ouvertes: {counts.get('open_virtual_positions')}",
        f"- Consensus frais 4s: {pipeline.get('fresh_consensus_groups_4s')}",
        "",
        "## Actions observees",
    ]
    if action_counts:
        lines.extend(f"- {action}: {count}" for action, count in action_counts.most_common())
    else:
        lines.append("- Aucun evenement de decision pour le moment.")
    lines.extend(["", "## Raisons de refus principales"])
    if reasons:
        lines.extend(f"- {reason}: {count}" for reason, count in reasons.most_common(20))
    else:
        lines.append("- Aucun refus local dans les derniers evenements exportes.")
    lines.extend(["", "## Pourquoi on peut perdre de l'argent en simulation"])
    lines.extend(_loss_explanations(equity, negative_events, reasons))
    lines.extend(["", "## Diagnostic pertes / reglages"])
    lines.extend(_loss_diagnostic_lines(loss_diagnostics))
    lines.extend(["", "## Dernieres decisions detaillees"])
    for row in events[-80:]:
        diag = _diagnostic_event(row)
        lines.append(
            "- "
            f"{diag['timestamp_ms']} | {diag['coin']} | leader={diag['leader_action']} {diag['leader_side']} | "
            f"bot={diag['bot_decision']} | status={diag['status']} | pnl={diag['estimated_net_pnl_usdc']} | "
            f"reason={diag['reason']} | edge={diag['edge_remaining_bps']} | age_ms={diag['signal_age_ms']} | "
            f"wallet={diag['wallet_address']}"
        )
    open_positions = bot.get("open_positions") or []
    lines.extend(["", "## Positions virtuelles ouvertes"])
    if open_positions:
        for position in open_positions:
            lines.append(
                "- "
                f"{position.get('coin')} {position.get('direction')} | size={position.get('size')} | "
                f"avg={position.get('avg_price')} | mark={position.get('mark_price')} | "
                f"unrealized={position.get('unrealized_pnl_usdc')} | mode={position.get('position_mode')}"
            )
    else:
        lines.append("- Aucune position virtuelle ouverte.")
    lines.extend(
        [
            "",
            "## A envoyer a ChatGPT",
            "Demande conseillee: analyse ces logs et explique quelles gates refusent le plus, quels couts mangent le PnL, si le bot arrive trop tard, et quelles priorites de scan/hot-watch ajuster sans jamais executer d'ordre.",
        ]
    )
    return "\n".join(lines) + "\n"


def _loss_diagnostic_lines(loss_diagnostics: dict[str, Any]) -> list[str]:
    if not loss_diagnostics:
        return ["- Aucun diagnostic pertes consolide dans le payload."]
    lines = [
        f"- PnL session courant: {loss_diagnostics.get('current_session_pnl_usdc')} USDC",
        f"- Evenements negatifs: {loss_diagnostics.get('negative_events')} / positifs: {loss_diagnostics.get('positive_events')}",
        f"- Ratio signaux en retard: {loss_diagnostics.get('stale_ratio')}",
        f"- Couts payes: {loss_diagnostics.get('costs_paid_usdc')} USDC",
    ]
    losing_coins = loss_diagnostics.get("losing_coins") or []
    if losing_coins:
        lines.append("- Coins qui font perdre le plus:")
        lines.extend(f"  - {row.get('coin')}: {row.get('pnl_usdc')} USDC" for row in losing_coins[:8])
    winning_coins = loss_diagnostics.get("winning_coins") or []
    if winning_coins:
        lines.append("- Coins qui ont aide la simulation:")
        lines.extend(f"  - {row.get('coin')}: {row.get('pnl_usdc')} USDC" for row in winning_coins[:8])
    top_reasons = loss_diagnostics.get("top_loss_reasons") or loss_diagnostics.get("top_no_trade_reasons") or []
    if top_reasons:
        lines.append("- Raisons techniques les plus frequentes:")
        lines.extend(f"  - {row.get('reason')}: {row.get('count')}" for row in top_reasons[:10])
    recommendations = loss_diagnostics.get("recommendations") or []
    if recommendations:
        lines.append("- Recommandations de reglage research-only:")
        lines.extend(f"  - {item}" for item in recommendations[:10])
    lines.append("- Important: ces recommandations ne garantissent pas de profit; elles servent a reduire les erreurs de simulation.")
    return lines


def _loss_explanations(equity: dict[str, Any], negative_events: list[dict[str, Any]], reasons: Counter[str]) -> list[str]:
    lines: list[str] = []
    costs = _as_float(equity.get("bot_costs_paid_usdc")) or 0.0
    current_pnl = _as_float(equity.get("current_pnl_usdc")) or 0.0
    if current_pnl < 0 and costs > abs(current_pnl) * 0.5:
        lines.append("- Les frais/spread/slippage expliquent une grande partie de la perte courante.")
    if reasons.get("STALE_SIGNAL") or reasons.get("ALL_ENTRY_SIGNALS_TOO_OLD_FOR_COPY"):
        lines.append("- Des signaux arrivent trop tard: augmenter la fraicheur des donnees/hot-watch avant de simuler plus.")
    if reasons.get("NO_MATCHING_PAPER_POSITION_FOR_CLOSE"):
        lines.append("- Des fermetures/reductions sont vues sans position virtuelle correspondante: le bot refuse au lieu d'inventer une sortie.")
    if negative_events:
        lines.append(f"- {len(negative_events)} evenement(s) recent(s) ont un PnL negatif net apres couts.")
    if not lines:
        lines.append("- Pas de cause dominante detectee dans les derniers evenements; regarder edge_remaining_bps, age_ms, couts et consensus.")
    return lines


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
