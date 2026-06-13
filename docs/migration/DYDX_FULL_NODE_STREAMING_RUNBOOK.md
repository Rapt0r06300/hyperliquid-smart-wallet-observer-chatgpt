# Runbook — Full Node gRPC Streaming dYdX v4 (le vrai firehose)

READ-ONLY / PAPER-ONLY. C'est la solution à « notre logiciel n'est pas assez
rapide » : au lieu de poller wallet par wallet (lent, signaux périmés), on reçoit
**tous les fills de tous les wallets, avec leur adresse, en temps réel**.

## Pourquoi c'est la bonne voie

- Indexer WS `v4_trades` : tous les trades d'un marché mais **anonymisés** (pas d'adresse) → inutile pour copier.
- Indexer WS `v4_subaccounts` : temps réel mais **par wallet connu** → lent, limité.
- **Full Node gRPC Streaming** : flux `dydxprotocol.clob.Query/StreamOrderbookUpdates`.
  En s'abonnant à **tous les `clob_pair_id`**, chaque `StreamOrderbookFill` contient
  les `orders`, et chaque order porte `order_id.subaccount_id.owner` =
  **l'adresse du wallet**. → découverte ET signal frais, sans polling.

## Prérequis (côté infra — c'est ce que tu fournis)

1. **Un full node dYdX v4** synchronisé (mainnet). Matériel conseillé : ~8 vCPU,
   32 Go RAM, SSD NVMe, plusieurs centaines de Go. (Ou louer un node chez un
   fournisseur qui active le streaming — la plupart des endpoints publics ne
   l'activent PAS, c'est trop lourd.)
2. Activer le streaming dans la config du node (`app.toml` ou flags de lancement) :
   ```
   --grpc-streaming-enabled=true
   --grpc-streaming-flush-interval-ms=50
   ```
   Port gRPC par défaut : `9090` (ou WebSocket `9092` avec `--websocket-streaming-enabled=true`).

## Vérifier le flux (sanity check)

```
grpcurl -plaintext -d '{"clobPairId":[0,1]}' 127.0.0.1:9090 \
  dydxprotocol.clob.Query/StreamOrderbookUpdates
```
Tu dois voir défiler des `orderFill` / `orderbookUpdate` / `subaccountUpdate`.

## Brancher le bot

1. Dépendances Python (sur la machine du bot) :
   ```
   pip install grpcio v4-proto
   ```
2. Variables d'environnement (ou dans le lanceur) :
   ```
   set DYDX_FULL_NODE_STREAM=1
   set DYDX_FULL_NODE_STREAM_ENDPOINT=127.0.0.1:9090
   ```
3. Le module `hyper_smart_observer/dydx_v4/full_node_stream.py` :
   - `FullNodeStreamClient(endpoint, clob_pair_ids, on_fill, clob_to_market)` se
     connecte, s'abonne à tous les marchés, et appelle `on_fill(StreamedFill)`
     pour chaque fill (avec adresse), confirmés consensus (`exec_mode=7`).
   - Brancher `on_fill` sur la découverte (ajouter l'adresse au harvester) **et**
     sur le moteur de décision (signal frais → cluster). Les deux d'un coup.

## Ce que ça change

- Plus de « aucun wallet trouvé » : chaque wallet qui trade apparaît avec son adresse.
- Plus de « signal trop vieux » : latence sub-bloc (< 1 s), pas de polling.
- Le harvester + le moteur se remplissent en continu de wallets réellement actifs.

## Limites honnêtes

- Il faut **un node** (ou un accès à un node streaming) — c'est de l'infra, pas un
  script. C'est ce que font les outils pros (HyperTracker, Hyperbot).
- Le `subticks`/`quantums` est encodé entier : conversion en prix/taille humains
  via le tick/atomic resolution de chaque marché (mapping `clob_pair_id → market`
  + résolution fournis par le moteur).
- Le parsing est testé (`tests/dydx_v4/test_full_node_stream.py`) ; la couche
  réseau (gRPC + v4-proto + node) se valide une fois ton node en place.
- Toujours **READ-ONLY / PAPER** : on lit le flux, on ne signe rien, on ne place
  aucun ordre.
