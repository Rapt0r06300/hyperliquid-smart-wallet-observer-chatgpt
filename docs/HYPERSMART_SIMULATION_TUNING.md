# HyperSmart Simulation Tuning

Ce document de tuning concerne uniquement la simulation locale. Il ne cree aucun ordre, ne signe rien, n'appelle pas `/exchange` et ne garantit aucun profit.

## Constat logs

Les logs recents montrent que le probleme principal n'est pas seulement le nombre de wallets suivis. Le probleme dominant est la fraicheur du signal:

- la plupart des signaux arrivent apres la fenetre utile de copie;
- beaucoup de fermetures arrivent sans position locale correspondante;
- les frais, spread, slippage et degradation de copie mangent les petits edges;
- les pertes se concentrent sur certains coins et certains wallets.

## Reglages appliques

- Fenetre d'entree simulation par defaut: `3000 ms`.
- Consensus prioritaire `copy-run`: `3 wallets` alignes dans `4 secondes`.
- Positions simultanees par defaut: `6`.
- Entrees solo: autorisees seulement avec edge restant beaucoup plus fort.
- Cooldown local: si un coin ou leader perd deja dans la session, les nouvelles entrees sont refusees sauf consensus frais de 3 wallets ou plus.
- Optimisation strategie: selection uniquement sur train + validation; le holdout sert seulement de verification apres selection.
- Les lignes `NO_TRADE`, doublons, snapshots ignores et cleanups ne peuvent jamais etre recomptees comme trades rentables.

## Anti-lookahead / anti-triche

Le tournoi de strategies respecte maintenant une separation temporelle contigue:

1. debut du journal = train;
2. milieu suivant = validation;
3. fin du journal = holdout.

Le holdout n'est pas utilise pour choisir la meilleure configuration. Si une configuration gagne en train/validation mais perd en holdout, elle reste affichee avec `holdout_failed_after_selection=true`. Cela evite de selectionner une strategie parce que l'on connait deja son resultat futur.

Sur les logs actuels, le rapport `strategy-tournament` selectionne `no_trade_baseline`: toutes les configurations candidates perdent apres frais, spread, slippage et latence. Ce n'est pas un echec a cacher; c'est une preuve que le bot doit rester en protection tant que les signaux frais et exploitables ne sont pas presents.

## Diagnostic si le PnL ne bouge pas

Si le metagraphe ou le PnL semblent figes, verifier d'abord les sorties runtime:

```powershell
python -m hl_observer runtime-write-check --from-logs "C:\Users\flo\Desktop\Projet invest\logs\logs à envoyer"
python -m hl_observer realtime-health --from-logs "C:\Users\flo\Desktop\Projet invest\logs\logs à envoyer" --stale-after-seconds 60
python -m hl_observer quality-gates --from-logs "C:\Users\flo\Desktop\Projet invest\logs\logs à envoyer"
```

Le gate `GATE_RUNTIME_WRITES` separe maintenant clairement deux cas:

- le bot refuse de simuler une entree parce que les signaux sont mauvais, trop vieux ou trop chers apres frais;
- les fichiers de simulation/replay ne peuvent pas etre rafraichis parce que le dossier runtime est verrouille ou non inscriptible.

Dans le second cas, il ne faut pas regler le moteur de trading au hasard. Il faut fermer proprement les anciennes fenetres HyperSmart, relancer le lanceur visible, puis verifier que `runtime-write-check` repasse en `OK`.

Si `logs\logs à envoyer` est verrouille mais que le simulateur doit quand meme produire un rapport, l'export bascule maintenant vers `%TEMP%\hypersmart_logs_a_envoyer` avec `directory_status=FALLBACK_USED`. Ce fallback ne change pas le PnL, n'invente pas de trade et ne contourne pas les garde-fous: il preserve seulement les diagnostics lisibles.

## Pourquoi ne pas simplement scanner sans limite

Hyperliquid impose des limites read-only et WebSocket. Un scan massif non borne augmente:

- la latence;
- les refus stale;
- le risque de signaux deja consommes;
- le bruit dans les deltas;
- les frais simules sur des edges trop faibles.

La voie correcte est:

1. utiliser les donnees publiques read-only;
2. prioriser les wallets actifs et recents;
3. limiter les subscriptions user-specific;
4. detecter les clusters coin/side dans quelques secondes;
5. refuser tout signal vieux ou non mesurable;
6. conserver le PnL reel de simulation, meme rouge.

## Commandes utiles

```powershell
python -m hl_observer simulation-tuning-report --from-logs "C:\Users\flo\Desktop\Projet invest\logs\logs à envoyer"
python -m hl_observer freshness-diagnostics --from-logs "C:\Users\flo\Desktop\Projet invest\logs\logs à envoyer"
python -m hl_observer live-pnl --from-logs "C:\Users\flo\Desktop\Projet invest\logs\logs à envoyer"
python -m hl_observer copy-run --interval 300 --dry-run --network-read --consensus-window-seconds 4 --consensus-min-wallets 3
```

## Interpretation

Un PnL negatif n'est pas un bug a cacher. C'est une information de calibration. Le bot doit devenir plus selectif, plus frais, et plus mesurable. Si la simulation ne prouve pas une amelioration stable, aucune phase d'execution ne doit etre activee.
