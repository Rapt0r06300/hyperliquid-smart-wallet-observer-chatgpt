# Playbook — maximiser la probabilité d'un PnL paper positif

READ-ONLY · PAPER-ONLY · 2026-06-12. **Aucune garantie de profit** : on empile
des petits edges et on élimine les trades perdants par construction. Le PnL d'un
copy-bot = `edge du leader capturé − frais − spread − slippage − latence − dégradation`.
Pour être positif, il faut **augmenter le terme de gauche et réduire chaque coût**.

Statut : ✅ fait · 🟡 dispo, à activer · 🔧 à coder (sur ton feu vert).

---

## 1. Latence — capter l'edge avant qu'il se dégrade (impact ★★★)

| Levier | Pourquoi | Statut |
|--------|----------|--------|
| WebSocket Indexer temps réel (< 1 s) au lieu du polling | Le polling HL livre des fills vieux de 10–120 s → edge déjà parti | ✅ `fast_scanner.py`, activé via `DYDX_FAST_SCANNER=1` |
| Poll événementiel du wallet dès qu'il bouge | Au lieu d'attendre l'intervalle | ✅ `_poll_priority_wallets` |
| Abandonner l'écran HL polled comme référence | Structurellement incapable de copie propre | 🟡 regarder le panneau dYdX, pas le gros chiffre HL |

**Le plus gros levier.** Sans fraîcheur < quelques secondes, le reste ne suffit pas.

---

## 2. Coûts — réduire ce qu'on paie (impact ★★★)

| Levier | Pourquoi | Statut |
|--------|----------|--------|
| Edge net minimum > coût total | Coût aller-retour ~17 bps ; exiger ≥35 bps net | ✅ retune lanceur `MIN_EDGE_BPS=35` ; dYdX `min_edge_bps=30` + `×3` |
| Marchés liquides seulement (BTC/ETH/SOL) | Spread/slippage faibles ; écarte HYPE & synthétiques | ✅ dYdX whitelist BTC/ETH/SOL ; HL `MIN_LIQUIDITY_SCORE=0.5` |
| Fills honnêtes (orderbook, pas au mid) | Ne pas sous-estimer le slippage | ✅ dYdX `use_orderbook_fills` |
| Ne pas churner (cf. §4) | Chaque aller-retour paie 2× les frais | ✅/🔧 |
| Tester la sensibilité aux frais | Voir combien les coûts mangent | ✅ `tools/dydx_pnl_sweep.py` |

---

## 3. Sélection des leaders — copier des gagnants (impact ★★★)

| Levier | Pourquoi | Statut |
|--------|----------|--------|
| Gates qualité : winrate ≥40 %, profit_factor ≥1.2, ≥10 trades | Éliminer le bruit/la chance | ✅ `wallet_harvester.passes_viral_gates`, `scoring.py` |
| **Backtest par wallet** : ne garder que les net-positifs | Si le leader perd sur SES prix, le copier est sans espoir | ✅ `tools/dydx_pnl_sweep.py` → shortlist |
| Consensus multi-wallets (K≥2 même coin/sens) | Accord = signal plus fort qu'un seul wallet | ✅ `consensus.py`, `consensus_min_wallets=2` |
| Découverte massive (max d'adresses) puis filtrage | Plus de candidats = meilleur top après filtres | ✅ harvester + source on-chain Cosmos |
| Éviter les scalpers (hold trop court) | On ne les bat pas sur la latence ; leur edge < nos coûts | 🔧 filtrer par durée de détention médiane du leader |
| Récence : ignorer un leader inactif/en perte récente | La perf décroît | 🟡 score de récence dans le harvester |

---

## 4. Timing entrée/sortie — anti-churn (impact ★★)

| Levier | Pourquoi | Statut |
|--------|----------|--------|
| Entrée seulement sur OPEN frais (pas ADD) | Moins de churn, pas d'entrée tardive | ✅ HL `ALLOW_ADD_AS_ENTRY=0` |
| Ne pas rejouer chaque réduction partielle du leader | Cause des « 1-2 s » et des pertes en escalier | 🔧 ignorer REDUCE, sortir sur CLOSE réel ou exit adaptatif |
| Hold minimum (anti flip-flop) | Empêche ouverture/fermeture en 1-2 s | 🔧 `min_hold_seconds` (dYdX a déjà 5 s avant LEADER_EXIT) |
| Exits adaptatifs ATR (laisser courir / couper) au lieu de mirror | Laisser les gagnants courir, couper vite les perdants | 🟡 `adaptive_exits.py` existe — à brancher en sortie principale |
| Time-stop + funding adverse | Fermer si ça stagne / funding contre nous | 🟡 `max_holding_hours`, `funding_adverse_threshold` dans la config dYdX |

---

## 5. Risque & portefeuille (impact ★★)

| Levier | Pourquoi | Statut |
|--------|----------|--------|
| Taille max par position, exposition totale plafonnée | Limiter la casse d'un mauvais trade | ✅ `max_position_pct=0.10`, `max_total_exposure_pct=0.30` |
| Max positions ouvertes (3) | Concentrer sur les meilleures | ✅ `max_open_paper_trades=3` |
| Coupe-circuit drawdown / pertes consécutives | Stopper après N pertes d'affilée ou −X % jour | 🔧 à ajouter (pause auto) |
| Pause par coin perdant (ex. HYPE) | Le log le recommande lui-même | 🟡 via whitelist/liquidité (déjà écarté) |

---

## 6. Sélectivité de régime — « ne pas trader EST une position » (impact ★★)

| Levier | Pourquoi | Statut |
|--------|----------|--------|
| NO_TRADE par défaut, n'entrer que sur signal frais + consensus + edge net + liquide | Moins de trades, beaucoup plus propres | ✅ deny-by-default partout |
| Ne PAS forcer des entrées | Mieux vaut 0 trade que des trades perdants | ✅ principe du projet |
| Fenêtres horaires / volatilité | Éviter les heures creuses / news | 🔧 optionnel |

---

## 7. Validation data-driven — la SEULE preuve (impact ★★★)

On ne devine pas, on **mesure** sur l'historique :

1. `python tools/dydx_pnl_sweep.py --fills <tes_fills.jsonl>`
   → classe wallets & marchés par PnL net, sort une **shortlist net-positive**.
2. Ne copier en live QUE cette shortlist (cf. §3).
3. Rejouer périodiquement (les leaders se dégradent) et mettre à jour la shortlist.

⚠️ Le backtest utilise les prix du leader (frais seulement) : c'est un filtre
d'**élimination** (jeter les perdants), pas une promesse. En live, latence+spread
+slippage réduisent encore le PnL → d'où l'importance du §1 (temps réel) et du §2.

---

## Ordre d'attaque recommandé

1. **§1 temps réel** (fait — vérifier que `harvested_addresses` monte et `median_age_ms` ~1 s).
2. **§7 backtest** sur tes vrais fills → shortlist net-positive.
3. **§3** ne copier que la shortlist, sur **§2** marchés liquides, **§4** sans churn.
4. **§5** coupe-circuit drawdown pour borner la casse.

**MAJ 2026-06-12** : les 4 leviers 🔧 demandés sont **codés** dans
`risk_policy.py` et câblés derrière `DYDX_RISK_POLICY=1` (activé dans le lanceur) :
anti-churn (min-hold + cooldown), coupe-circuit (pertes consécutives + perte
jour), anti-scalper, et exits ATR (déjà actifs via `_check_exits` :
SL/TP/trailing/time-stop). Voir `docs/migration/DYDX_V4_RISK_POLICY.md`.
