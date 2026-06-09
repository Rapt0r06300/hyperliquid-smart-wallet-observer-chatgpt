# HyperSmart Simulation Audit

Date: 2026-06-01

## Objectif

Ce document trace l'audit du mode simulation HyperSmart Observer. La simulation doit rester locale, read-only et sans ordre reel. Elle doit afficher le solde du bot simule comme un portefeuille de 1000 USDT pendant la session du lanceur, puis repartir de 1000 USDT uniquement au prochain lancement.

## Corrections appliquees

1. Session du lanceur
   - Le lanceur appelle `python -m hl_observer reset-simulation-state --starting-equity 1000`.
   - Une nouvelle ouverture du lanceur redemarre une session propre a 1000 USDT.
   - Une simple reconnexion de la page ne remet plus le solde a zero.

2. Historique P&L
   - Ajout de `simulation_equity_history` dans l'etat UI.
   - L'historique conserve les points de portefeuille, les entrees/sorties simulees et le mark-to-market.
   - Le metagraphe est maintenant construit depuis cet historique de session, pas depuis une liste d'evenements volatile.

3. Positions virtuelles
   - Les positions restent ouvertes jusqu'a un `REDUCE` ou `CLOSE` leader correspondant.
   - Le bot ne ferme pas une position juste parce que le P&L ouvert est rouge.
   - Les positions orphelines legacy sont nettoyees sans inventer de P&L.
   - Les leaders qui ouvrent le meme coin dans le meme sens sur une fenetre fraiche de 4 secondes forment maintenant une position virtuelle de consensus.
   - Une position de consensus ne multiplie pas l'exposition par wallet: les doublons confirment le cluster au lieu de creer des positions redondantes.
   - Une position de consensus se reduit ou se ferme seulement avec les leaders qui ont contribue au cluster.

4. Scanner
   - Le runtime arrete aussi les processus `live-user-fills-scan` orphelins.
   - Le poller garde la rotation read-only: public trades pour decouverte, userFills WS pour leaders shortlistes, puis `/info` borne.
   - La limite de 10 users WebSocket user-specific est respectee.

5. UI debutant
   - `Latent` est remplace par `gain/perte ouvert`.
   - `Expose` est remplace par `capital utilise` et `capital disponible`.
   - Le consensus affiche la fenetre fraiche de 4 secondes.
   - Les positions virtuelles indiquent maintenant `consensus X leaders` quand le bot simule une position issue d'un groupe de leaders.

## Limites honnetes

- La simulation peut perdre. Elle ne doit jamais afficher un faux profit.
- Un consensus multi-wallet n'est pas une garantie de gain.
- Les mouvements de leaders peuvent etre detectes trop tard apres frais, spread, slippage et latence.
- Le scan massif illimite est volontairement refuse: Hyperliquid impose des limites API/WS et le logiciel doit rester stable.
- Aucun ordre reel, aucune signature, aucune cle privee, aucun mainnet et aucun executor testnet actif.

## Verification

Commandes recommandees:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q tests/test_ui_simulation_persistence.py tests/test_hypersmart_single_launcher.py tests/test_copy_cli_and_safety.py tests/test_ui_copy_dashboard.py
python -m hl_observer safety-audit
```
