# dYdX v4 — Scanner rapide multi-wallets (fraîcheur < 4 s)

> READ-ONLY · PAPER-ONLY · DENY-BY-DEFAULT · un signal n'est jamais un ordre.

## 1. Problème résolu

Les logs de simulation (`logs/logs à envoyer/simulation_resume_pour_chatgpt.md`)
montrent la vraie cause des pertes paper :

- `age_ms` des deltas leaders : **8 000 à 58 766 ms** (8 à 58 secondes) ;
- `Ratio signaux en retard : 0.46` (46 % des signaux arrivent trop tard) ;
- gate `STALE_SIGNAL` déclenchée 1 916 fois, `NO_MATCHING_PAPER_POSITION_FOR_CLOSE`
  1 906 fois (le bot voit des fermetures de positions qu'il n'a jamais ouvertes,
  parce qu'il a refusé l'entrée — trop vieille).

Cause technique : l'ancien `_poll_shortlist_live()` interroge **chaque wallet en
REST, séquentiellement, sur un intervalle** (15 s côté lanceur, 300 s côté
Hyperliquid). Les CLOSE ne sont vus qu'au cycle de polling **suivant**. D'où une
latence structurelle de plusieurs dizaines de secondes — fatale pour du
copy-trading où la fenêtre utile est de ~4 s.

## 2. Principe du scanner

Remplacer le polling REST lent par le **flux temps réel** de l'Indexer dYdX :

```
Indexer WS  v4_subaccounts:{address}/{sub}
        │  (fills poussés en < 1 s)
        ▼
FastScanner.handle_ws_message()
        │  parse → dedupe (fill_id) → fenêtre fraîcheur → file
        ▼
ScannedFill frais (age_ms réel, source=WS)
        │
        ▼
Lifecycle / Consensus / Paper  (inchangés)
```

Pour « scanner des milliers de wallets » sans saturer le WebSocket :

| Couche | Rôle | Borne |
|--------|------|-------|
| `HotWalletSet(capacity=N)` | abonnés WS temps réel = les N meilleurs/plus actifs | défaut 500 |
| `rest_fast_sweep()` | balayage REST **concurrent borné** pour le reste | `max_workers` |
| `FillDeduper(maxlen)` | anti-doublon WS↔REST↔reconnect, mémoire bornée | défaut 200 000 |

Quand un wallet plus chaud entre, le hot-set évince automatiquement le plus
faible (score, puis ancienneté) et renvoie `(added, removed)` pour piloter les
souscriptions. On suit donc des milliers de candidats tout en gardant une
empreinte WS constante.

## 3. Module `hyper_smart_observer/dydx_v4/fast_scanner.py`

Composants (logique pure, testable hors réseau) :

- `parse_iso_to_ms()` — `createdAt` ISO8601 / ms / s → epoch ms (None si illisible).
- `parse_subaccount_fills()` — extrait/normalise les fills d'un message
  `v4_subaccounts`, calcule `age_ms`, ignore tout fill incomplet (jamais inventé).
- `ScannedFill` — fill normalisé + `age_ms` + `source` (WS|REST) + `is_fresh()`.
- `FillDeduper` — dédup FIFO bornée par `fill_id`.
- `HotWalletSet` — ensemble borné classé par score, éviction + `evict_stale()`.
- `ThroughputMeter` — fills/s glissants + médiane d'âge.
- `FastScanner` — orchestration : WS temps réel + sweep REST injectable, dédup,
  fenêtre de fraîcheur (`max_age_ms`, défaut 4 000 ms), file + callback, `stats()`.

### Sécurité (vérifiée par test)

`FastScanner` **n'expose aucune** méthode contenant `order`, `sign`, `submit`,
`place`, `withdraw`, `deposit`, `private_key`, `mnemonic`, `seed`, `transfer`
(`test_scanner_has_no_execution_methods`). Le module lit, parse, déduplique,
range. Rien d'autre.

## 4. Intégration (prochaine étape, non encore branchée par défaut)

```python
from hyper_smart_observer.dydx_v4.fast_scanner import FastScanner
from hyper_smart_observer.dydx_v4.ws_client import DydxIndexerWsClient

scanner = FastScanner(max_age_ms=cfg.max_signal_age_ms, hot_capacity=500)
ws = DydxIndexerWsClient(cfg.indexer_ws_url, on_message=scanner.handle_ws_message)
ws.start()
scanner.track_wallets((w.address, w.score) for w in shortlist)  # abonne les chauds

# Boucle de consommation (remplace _poll_shortlist_live) :
while running:
    fill = scanner.get_fresh(timeout_s=0.5)
    if fill is None:
        continue
    lifecycle.process_fill(fill)   # OPEN/ADD/REDUCE/CLOSE — paper only
```

**Statut : branché (2026-06-12) derrière le flag `DYDX_FAST_SCANNER`.**

- `config.py` : `fast_scanner_enabled` (défaut **False**) + `fast_scanner_hot_capacity`.
- `fast_scan_integration.py` : relie harvester + scanner, expose
  `track_shortlist()`, `wallets_that_just_moved()`, `stats()`.
- `live_observer.py` : si le flag est activé, l'observer abonne les wallets en WS
  et, à chaque tick, poll **immédiatement** ceux qui viennent de trader
  (`_poll_priority_wallets` → `_poll_one_wallet`). Tout est gardé par try/except.
- Flag **OFF par défaut** ⇒ le chemin REST historique est **strictement inchangé**
  (fallback préservé, règle « ne rien supprimer brutalement »).
- Activation : `set DYDX_FAST_SCANNER=1` (ou via env) avant de lancer.

## 5. Cibles de débit

- latence fill→signal : **< 1 s** (vs 8–58 s aujourd'hui) ;
- wallets candidats suivis : milliers (hot-set WS borné + sweep REST) ;
- doublons : 0 retraitement grâce au `FillDeduper` ;
- mémoire : bornée (dedupe FIFO + hot-set à capacité fixe).

## 6. Ce que ça ne fait pas (honnêteté)

- Ne garantit **aucun** PnL positif. Un flux frais permet seulement aux gates
  (consensus, edge net après coûts, liquidité) d'accepter de **bons** trades au
  lieu de tout refuser pour cause de signal trop vieux.
- Ne contourne aucune restriction : c'est l'Indexer **public** dYdX, pas du
  scraping de frontend. Aucune clé, aucune auth.
