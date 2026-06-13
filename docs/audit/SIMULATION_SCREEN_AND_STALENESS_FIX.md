# Audit — Écran de simulation qui saute + pertes paper (latence)

Date : 2026-06-12 · READ-ONLY · PAPER-ONLY · 0 ordre réel.

Deux symptômes signalés par l'utilisateur :
1. « l'écran de simulation bug, ça saute d'une fenêtre à une autre » ;
2. « on perd de l'argent » en simulation.

---

## A. Bug d'écran : la page saute entre les panneaux

### Cause racine (confirmée dans le code UI)

La page (`src/hl_observer/ui/templates/index.html`) est **une seule page longue**
avec des panneaux ancrés (`#simulationPanel`, `#copyPanel`, `#dataWatchPanel`,
`#activityPanel`, `#expertPanel`) via `<nav class="quick-tabs">`.

`src/hl_observer/ui/static/app.js` rafraîchissait de façon trop agressive :

| Source | Cadence | Effet |
|--------|---------|-------|
| `setInterval(refreshSimulationOverview, 1000)` | **1 s** | réécrit l'`innerHTML` de ~12 feeds + **redimensionne le canvas** |
| `setInterval(loadSimpleHome, 10000)` | **10 s** | reconstruit **toute** la page |
| WebSocket `onmessage` | par message | refresh supplémentaire non coordonné |
| Script inline `refreshDydx` (index.html) | **3 s** | réécrit `#simulationSummary`, **le même nœud** qu'app.js |

Chaque réécriture change la **hauteur** de la page. Quand l'utilisateur est
scrollé sur un panneau, la hauteur qui bouge déplace le viewport → la vue
« saute » vers un autre panneau. Le canvas réassigné (`canvas.width = …`) à
chaque frame ajoutait un scintillement. Deux boucles écrivant `#simulationSummary`
ajoutaient un effet de clignotement.

### Correctifs appliqués (`app.js` + `index.html`)

1. **Préservation du scroll** : `preserveScroll()` capture `scrollX/Y` (+ focus)
   et les restaure autour de chaque re-render → la vue ne bouge plus.
2. **Cadences raisonnables** : simulation `1 s → 4 s`, home complet `10 s → 20 s`
   (toujours temps réel pour du paper, mais sans thrash).
3. **Debounce WebSocket** : une rafale de messages ne déclenche qu'**un** refresh
   (au plus toutes les 1,5 s).
4. **Canvas** : redimensionné **seulement** si la taille change réellement
   (plus de vidage/reflow par frame).
5. **Panneau dYdX inline** : même préservation de scroll appliquée.

Tout reste 100 % lecture : aucun de ces changements n'envoie d'ordre.

---

## B. Pertes paper : signaux trop vieux (latence du scan)

### Preuves (logs `simulation_resume_pour_chatgpt.md`)

- Capital 1000 USDT fictif → equity **999,16** (PnL session **-0,84 USDC**, soit -0,08 %).
- `age_ms` des dernières décisions : **8 000 à 58 766 ms**.
- `Ratio signaux en retard : 0.46`.
- Gates les plus fréquentes : `COPY_DEGRADATION_TOO_HIGH` 2034, `EDGE_REMAINING_TOO_LOW`
  2020, `STALE_SIGNAL` 1916, `NO_MATCHING_PAPER_POSITION_FOR_CLOSE` 1906,
  `SINGLE_WALLET_EDGE_TOO_LOW` 1753, `LIQUIDITY_TOO_LOW` 890.
- **4 entrées** reproduites sur 5000 deltas ; 4126 refus locaux.
- Coin le plus perdant : **HYPE -0,41 USDC** (reduces rejouées en retard).
- Journal décisions cumulé : **-106 USDC sur 2 078 010 événements** — historique
  contaminé (multi-runs/replays), **séparé** de la session fraîche dans l'UI.

### Cause racine

`DydxLiveObserver._poll_shortlist_live()` interroge chaque wallet **en REST,
séquentiellement, sur un intervalle**, et détecte les CLOSE par diff de snapshot
au cycle **suivant**. → latence 8–58 s. Quand le bot reçoit enfin le signal :
- soit il est trop vieux → `STALE_SIGNAL` (refus) ;
- soit il l'a déjà manqué et ne voit que la fermeture → `NO_MATCHING_PAPER_POSITION_FOR_CLOSE` ;
- soit il copie une reduce tardive à un prix dégradé → perte (HYPE).

Aggravant côté lanceur : `LANCER_HYPERSMART.cmd` force
`HYPERSMART_SIMULATION_MAX_SIGNAL_AGE_MS=120000` (**120 s**), ce qui laisse passer
des reduces très tardives qui se soldent en perte.

### Correctif structurel

Le vrai remède est la **fraîcheur des données**, pas un changement de seuils :
voir `docs/migration/DYDX_V4_FAST_SCANNER.md`. Le nouveau module
`fast_scanner.py` passe la latence fill→signal de 8–58 s à **< 1 s** via le
WebSocket Indexer. Avec des signaux frais, les gates consensus/edge peuvent enfin
accepter de **bons** trades au lieu de tout refuser.

### Réglages recommandés (à valider, non forcés)

- Aligner le lanceur sur la fenêtre fraîche : `MAX_SIGNAL_AGE_MS` 120000 → **8000**
  (cohérent avec `hard_max_signal_age_ms`). Effet attendu : moins de trades, mais
  plus propres (objectif quant « less but cleaner »).
- Garder `consensus_min_wallets ≥ 2` et l'edge net après coûts (déjà en place).
- Ne **pas** augmenter la taille tant que le PnL session est négatif.

> Aucune de ces mesures ne promet un PnL positif. Elles réduisent les erreurs de
> simulation (entrées tardives, orphan-closes) et augmentent la probabilité d'un
> PnL paper réaliste.

---

## C. Vérification sécurité

- UI : lecture seule, aucun endpoint d'exécution touché.
- `fast_scanner.py` : aucune méthode d'ordre/signature/dépôt (test dédié).
- 0 clé privée, 0 seed, 0 mnemonic, 0 signature, 0 dépôt/retrait, 0 ordre réel.
