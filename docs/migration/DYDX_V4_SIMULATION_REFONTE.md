# dYdX v4 — Refonte de la simulation (UI + réalisme mainnet)

READ-ONLY · PAPER-ONLY · 2026-06-12. 0 ordre, 0 clé, 0 signature.

## 1. Nouvel écran (principal)

`src/hl_observer/ui/static/simulation_v2.html` — page autonome, moderne, simple :
- Noms simples : Solde, Gain/perte, Trades gagnants, Taux de réussite, Achat/Vente,
  « 3 wallets d'accord », « signal trop vieux »… (traduction des raisons techniques).
- **Métagraphe** propre de l'évolution du solde (canvas natif, 0 dépendance externe),
  ligne de référence à 1000 $, vert si ≥ départ sinon rouge, accumulé en direct.
- Positions ouvertes + décisions récentes en langage humain.
- Rafraîchissement 4 s, hauteur stable → **aucun saut d'écran**.
- Lit le moteur dYdX live (`/api/dydx/status|positions|wallets`).

Le lanceur ouvre désormais cette page (`/static/simulation_v2.html`). L'ancien
tableau de bord reste accessible (`/`) en secours — rien n'est supprimé.

## 2. Réalisme « comme sur le mainnet »

Demande : *si on perd en simulation, on aurait perdu sur le mainnet ; si on gagne,
on gagne comme sur le mainnet.* Module `paper_fill.py` (pur, testé) :

| Élément | Comment c'est fidèle au mainnet |
|---------|--------------------------------|
| Décisions | Identiques sim/mainnet (même logique bot). |
| Prix d'entrée/sortie | Mode `orderbook_real` : VWAP sur le **carnet d'ordres réel** → exactement le prix obtenu, slippage réel inclus. Mode `mark_simple` : mark réel + coûts forfaitaires. |
| Coûts | Frais taker ×2 + spread + slippage + **funding** réels. |
| PnL | Marké aux **vrais prix** d'entrée/sortie/courant du mainnet (`realized_pnl_usdc`, `unrealized_pnl_usdc`). |

Config : `DYDX_FILL_REALISM=orderbook_real` (défaut) ou `mark_simple`.

### Limite honnête (à dire clairement)

Aucun paper trade n'est identique à 100 % au live, pour deux raisons qu'on
**modélise** (jamais qu'on cache) :
1. l'**impact de marché** de notre propre ordre (modélisé par le slippage + le cap
   de participation au carnet `max_book_participation_pct`) ;
2. la **latence** d'acheminement vers l'exchange (modélisée en bps).

Avec le carnet réel + ces coûts, la simulation est le **proxy le plus fidèle
possible** du mainnet sans passer d'ordre. Si elle perd, le mainnet aurait perdu ;
si elle gagne (après ces coûts), c'est un gain réaliste — pas une garantie.

## 3. Tests

`tests/dydx_v4/test_paper_fill.py` (VWAP carnet, slippage, coûts, funding, PnL
long/short marké). À exécuter : `python -m pytest tests/dydx_v4/ -q`.

## Sécurité

`paper_fill.py` ne fait que calculer des prix/coûts/PnL à partir de données
publiques. Aucune méthode d'ordre/signature/dépôt. READ-ONLY / PAPER-ONLY.
