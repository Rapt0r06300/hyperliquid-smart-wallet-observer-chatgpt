# Audit — PnL négatif persistant + retune sélectif (2026-06-12)

READ-ONLY · PAPER-ONLY · 0 ordre réel. Captures + logs live à l'appui.

## Diagnostic (logs live `simulation_resume_pour_chatgpt.md`)

- PnL session **-0,65 USDC**, equity 999,35.
- **18 événements négatifs / 0 positif** → aucun trade gagnant, jamais.
- **2 entrées / 16 sorties-réductions** → churn : on rejoue chaque réduction du
  leader à perte (HYPE -0,18 réalisé, -0,47 latent).
- `age_ms` jusqu'à **1 406 503 ms (~23 min)** sur les refus ; ratio retard 0,48.
- Coût payé 0,13 USDC pour 0 gain.

## Cause racine n°1 — edge minimum SOUS le coût

Le moteur de décision (`src/hl_observer/ui/routes.py`, lit `HYPERSMART_SIMULATION_*`)
avait des défauts corrects, mais **le lanceur les dégradait** :

| Réglage | Défaut code | Lanceur (avant) | Effet |
|---------|-------------|-----------------|-------|
| `MIN_EDGE_BPS` | 25 | **8** | edge net min 8 bps < coût aller-retour ~17 bps → **perte par construction** |
| `MAX_SIGNAL_AGE_MS` | — | **120000** (120 s) | entrées sur signaux vieux de 2 min |
| `ALLOW_ADD_AS_ENTRY` | 0 | **1** | entrées sur les ADD (scale-in) → churn, entrées tardives |

Coût aller-retour estimé : fee 5 bps ×2 + spread 2 + slippage 5 = **~17 bps**, plus
dégradation de copie. Avec un seuil d'edge à 8 bps, **chaque trade perd** en moyenne.

## Cause racine n°2 — pipeline HL = polling (pas temps réel)

Le pipeline Hyperliquid collecte les fills par **polling** (`UserFillsMaxLiveAgeMs=120000`,
poll loop périodique). La donnée la plus fraîche disponible a déjà des dizaines de
secondes. Un copy-trading propre exige du **temps réel** ; le polling ne le permet pas.

## Correctif appliqué — retune SÉLECTIF (config only, réversible)

`LANCER_HYPERSMART.cmd` **et** `tools/start_hypersmart_simulation.ps1` (le PS1
ré-impose les valeurs, donc les deux sont corrigés) :

| Réglage | Avant | Après | But |
|---------|-------|-------|-----|
| `MIN_EDGE_BPS` | 8 | **35** | edge net > coût + marge (anti-perte) |
| `MAX_SIGNAL_AGE_MS` | 120000 | **6000** | fraîcheur stricte (≈ fenêtre consensus 4 s) |
| `ALLOW_ADD_AS_ENTRY` | 1 | **0** | entrées seulement sur OPEN frais (anti-churn) |
| `MIN_LIQUIDITY_SCORE` | (0.35) | **0.5** | marchés liquides seulement (écarte HYPE & co) |
| `MAX_COPY_DEGRADATION_BPS` | (18) | **12** | copiabilité plus stricte |

Tests du lanceur (`tests/test_hypersmart_single_launcher.py`) mis à jour en cohérence.

## Effet attendu (honnête)

- Le moteur HL va trader **beaucoup moins** — voire presque plus, car sa donnée
  polled passe rarement la fenêtre 6 s. Objectif **réaliste : arrêter la saignée**
  (passer de « -X qui descend » à « ~plat »), PAS imprimer du vert.
- **Le PnL n'est pas garanti positif.** On supprime les trades perdants par
  construction (edge < coût) ; s'il n'existe pas de trade à edge net positif frais,
  le bon comportement est de **ne pas trader**.

## Où chercher un PnL réaliste positif

Pas sur l'écran HL (polled). Sur le **moteur dYdX temps réel** activé via
`DYDX_FAST_SCANNER=1` : WebSocket Indexer (< 1 s) + découverte on-chain Cosmos,
avec des gates déjà sélectives (`min_edge_bps=30`, `edge_safety_multiplier=3`,
fenêtre 8 s). C'est là que la fraîcheur permet des entrées réellement à edge positif.
Voir `docs/migration/DYDX_V4_FAST_SCANNER.md`.
