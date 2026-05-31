# Jules Branch Audit - 2026-05-31

Objectif: garder `main` comme seule branche distante, tout en conservant uniquement les apports utiles, testables et compatibles avec les garde-fous HyperSmart Observer.

## Decision d'architecture

`main` reste la branche officielle. Les branches Jules etaient des propositions paralleles, parfois redondantes, parfois trop agressives. Aucun merge brut n'a ete effectue. Les idees utiles ont ete portees manuellement dans `main` avec une implementation plus stricte:

- suivi de fraicheur des sources (`source_health`);
- moteur de comparaison de snapshots read-only;
- persistance enrichie des `wallet_snapshots`;
- centralisation des helpers de delta (`wallets/delta_utils.py`);
- tests unitaires dedies.

## Audit par branche

| Branche | Apport utile | Risque observe | Decision | Action sur `main` |
|---|---|---|---|---|
| `feat/intelligent-delta-detector-*` | Idee de scorecard delta/fills | Vocabulaire marketing, flip decompose en CLOSE+OPEN, risque de copier un flip ambigu | Rejet merge brut | Non retenu; la regle flip=UNKNOWN reste prioritaire |
| `feat/simplified-dashboard-v2-*` | UI plus lisible | Re-ecriture massive, screenshots binaires, risque de regression UI stable | Rejet merge brut | Non retenu |
| `feature/metagraphe-irreprochable-*` | Ameliorations visuelles du graphe | Recouvre le metagraphe deja stabilise; ajoute actions UI d'export client non necessaires | Rejet merge brut | Non retenu |
| `feature/unified-simulation-engine-*` | Idee d'un moteur commun replay/live | Place la simulation sous `execution/`, termes `execute_*`, grosses regressions routes | Rejet merge brut | Non retenu pour ce lot |
| `feature/virtual-portfolio-state-machine-*` | Persistance positions fermees/MFE/MAE | Fort chevauchement avec la persistence deja livree; gros diff UI | Rejet merge brut | Non retenu pour eviter de casser le PnL persistant |
| `fresh-data-engine-*` | `SourceHealth`, centralisation delta, garde donnees fraiches | Re-ecriture large de `routes.py` et paper engine parallele | Port partiel | `source_health`, `delta_utils`, updates collector/ws publics |
| `hypersmart-reinforcement-v1-*` | Divers tests/doc | Melange deux architectures, modifie beaucoup de fichiers | Rejet merge brut | Non retenu |
| `jules-codex-handoff-pack-*` | Documentation de handoff | Beaucoup de fichiers de contrat/handoff redondants | Rejet merge brut | Non retenu |
| `non-regression-tests-v10-*` | Idees de tests UI/persistence/safety | Test scanne `/exchange` trop brutalement et supprimerait des mentions d'interdiction legitimes | Rejet merge brut | Idees couvertes par tests existants et nouveaux tests cibles |
| `robust-snapshot-engine-*` | SnapshotData, comparaison current/previous, deltas depuis snapshots | Ajouts incomplets de colonnes, exceptions potentielles sur DB existante | Port partiel | `snapshot_engine.py`, `snapshot_service.py`, migrations safe |
| `signal-candidate-edge-remaining-*` | Fonctions edge/factors | `Gain Assurance`, decisions testnet candidates, schema large et risqué | Rejet merge brut | Non retenu dans ce lot |
| `verrou-capital-1000-sim-*` | Idee verrou capital 1000 | Chevauche deja livre, gros diff UI/reports | Rejet merge brut | Main conserve deja capital simulation 1000 USDT |
| `wallet-selection-engine-improvement-*` | Scoring wallet plus riche | Peut produire `TESTNET_CANDIDATE`, modifie schema et UI largement | Rejet merge brut | Non retenu dans ce lot |

## Fichiers utiles portes

- `src/hl_observer/wallets/delta_utils.py`
- `src/hl_observer/wallets/snapshot_engine.py`
- `src/hl_observer/wallets/snapshot_service.py`
- `tests/test_source_health_and_snapshot_engine.py`

## Garde-fous confirmes

- Aucun merge brut de branche experimentale.
- Aucun `/exchange` operationnel ajoute.
- Aucune signature ajoutee.
- Aucune cle privee ajoutee.
- Aucun ordre reel ajoute.
- Aucun executor testnet active.
- Les flips restent `UNKNOWN` dans le snapshot engine.
- Les changements de position sans fills correspondants deviennent `UNKNOWN`.

## Branches distantes

Apres validation des tests et push de `main`, les branches distantes Jules peuvent etre supprimees pour revenir a un remote avec `main` uniquement.
