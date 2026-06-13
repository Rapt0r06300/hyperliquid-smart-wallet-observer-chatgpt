# dYdX v4 — Moteur de découverte multi-sources de wallets

> READ-ONLY · PAPER-ONLY · aucun ordre · aucune clé. Module : `hyper_smart_observer/dydx_v4/wallet_harvester.py`

## But

Avoir **le maximum de wallets candidats**, vite — la brique « find wallets, improve
with each found wallet » du bot viral (cf.
`docs/research/MAGIC_BOT_VIRAL_METHOD_CONFIRMED.md`). Le harvester alimente
ensuite le scan temps réel (`FastScanner`).

## Pourquoi pas du scraping HTML

Le frontend d'un DEX lit la **même** donnée publique que nous (Indexer / on-chain).
Scraper le HTML serait **plus lent** (une couche de plus), **fragile** (casse au
moindre changement d'UI) et contraire aux ToS. La bonne source = **on-chain + flux
de trades**, qui est à la fois plus rapide et exhaustive (chaque fill = une adresse).

## Architecture

```
[Leaderboard] [Trade-tape] [On-chain blocks] [Import dataset]
       \           |              |               /
        ▼          ▼              ▼              ▼
                WalletIndex  (dedupe par adresse,
                             first/last seen, activité, sources)
                     │
                     ▼  rank()  =  filtre gates bot-viral + score
            top (address, score)  ──►  FastScanner.track_wallets()
```

### Composants (logique pure, testable hors réseau)

- `is_valid_address()` — n'accepte que des adresses **complètes** (`dydx1…` /
  `0x…40hex`) ; rejette les tronquées (`0xab…cd`). Règle projet.
- `WalletIndex` — index dédupliqué : `observe(address, source, now_ms, metrics)`
  fusionne (first_seen min, last_seen max, union des sources, activité++,
  métriques complétées). Cœur testable.
- `extract_leaderboard_addresses()` / `extract_tape_addresses()` — parsers
  défensifs de payloads publics (noms de champs variables).
- `WalletSource` + fabriques `leaderboard_source / tape_source / static_source /
  cosmos_source` — chaque source enveloppe une `fetch_fn` **injectable** → testable
  sans réseau ; une source qui tombe renvoie `[]` (jamais d'exception qui casse).
- **`cosmos_source` (on-chain, maximum d'adresses)** — pagine **tous** les
  subaccounts dYdX v4 via `cosmos_client.scan_subaccounts()` (Cosmos LCD public).
  Chaque subaccount actif = une adresse + sa balance USDC (qui alimente le score).
  C'est la vraie voie « 600k–1,5 M wallets », sans clé. Branchée via
  `WalletHarvester.add_cosmos_source(cosmos_client)` ou, en live,
  `FastScanIntegration.enable_cosmos_discovery(cosmos_client)` +
  `refresh_discovery()` (appelé en background par l'observer quand le flag est ON).
- `score_candidate()` — score 0–100 **transparent** : qualité d'exécution
  (winrate, profit_factor, ROI) + récence + confirmation multi-source + activité.
- `passes_viral_gates()` — filtre « qualité d'exécution » du bot viral :
  trades ≥ 10, winrate ≥ 40 %, profit_factor ≥ 1.2 (appliqué quand les métriques
  sont connues ; sinon le wallet reste découvrable en tier bas).
- `WalletHarvester` — `add_source()`, `harvest_once()` (fan-out, ne lève jamais),
  `rank()`, `top_for_scanner()` (→ `[(address, score)]` pour le scanner), `stats()`.

## Branchement (boucle complète, façon bot viral adaptée dYdX)

```python
from hyper_smart_observer.dydx_v4.wallet_harvester import (
    WalletHarvester, leaderboard_source, tape_source, static_source,
)
from hyper_smart_observer.dydx_v4.fast_scanner import FastScanner
from hyper_smart_observer.dydx_v4.ws_client import DydxIndexerWsClient

harvester = WalletHarvester(max_track=500)
harvester.add_source(leaderboard_source("dydx_leaderboard", fetch_leaderboard))
harvester.add_source(tape_source("market_tape", fetch_recent_trades))
harvester.add_source(static_source("seed", known_good_addresses))
# (on-chain : ajouter une source qui lit cosmos_client → adresses des fills)

scanner = FastScanner(max_age_ms=4000, hot_capacity=500)
ws = DydxIndexerWsClient(cfg.indexer_ws_url, on_message=scanner.handle_ws_message)
ws.start()

# Boucle de découverte (Job A élargi) — périodique :
harvester.harvest_once()
scanner.track_wallets(harvester.top_for_scanner())   # abonne les meilleurs en WS

# Boucle de copie (Job B) — temps réel :
while running:
    fill = scanner.get_fresh(timeout_s=0.5)
    if fill: lifecycle.process_fill(fill)            # OPEN/ADD/REDUCE/CLOSE, paper
```

## Sécurité

`WalletHarvester` n'expose **aucune** méthode contenant `order/sign/submit/place/
buy/sell/withdraw/deposit/private_key/seed/transfer` (test
`test_harvester_has_no_execution_methods`). Il lit, déduplique, score. Rien d'autre.

## Limites honnêtes

- Plus de wallets ≠ plus de profit : ça nourrit les **filtres** (consensus, edge).
- La source on-chain (énumération exhaustive) nécessite un accès full-node/RPC ou
  un dataset ; le module fournit le **point d'entrée** (`tape_source` /
  `static_source` / source on-chain à brancher sur `cosmos_client`), pas le node.
- Tests écrits ; exécution `pytest` à lancer côté machine utilisateur.
