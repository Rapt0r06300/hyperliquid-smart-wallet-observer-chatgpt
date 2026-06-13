# Pourquoi le bot Polymarket « ne se trompait presque jamais » — et ce que ça implique pour dYdX

Recherche web, 2026-06-12. Lecture honnête, sans maquillage. Sources en bas.

## 1. Le secret du 95–99 % de réussite : ce n'était PAS de la prédiction

Le run viral (ex. 0x8d… : 313 $ → ~438 000 $, **98 % de réussite sur 6 615 paris**
de contrats BTC/ETH/SOL « up/down » 15 min) reposait sur de l'**arbitrage de
latence**, pas sur de l'intelligence de marché :

- Les contrats courts de Polymarket **repricent avec 30–90 s de retard** sur le
  spot Binance.
- Le bot écoutait le **WebSocket Binance** et achetait le côté **quasi déjà
  gagnant** avant que Polymarket ajuste. Il **réagissait à un résultat presque
  déjà déterminé** — d'où le quasi-zéro erreur. Ce n'est pas « prédire juste »,
  c'est « parier sur ce qui est déjà arrivé mais pas encore affiché ».
- Variante sans risque : quand **YES + NO < 1 $**, acheter les deux → ~1,5–3 %
  garantis (un des deux paiera 1 $).
- Variante T‑10 s : ~85 % de la direction est connue 10 s avant la clôture ; les
  cotes Polymarket ne l'intègrent pas encore.

**Le « ne se trompe jamais » vient de la STRUCTURE du marché** (binaire, qui se
résout, avec un sous-jacent connu et un prix en retard), pas d'un cerveau magique.

## 2. Pourquoi ça NE se transpose PAS à dYdX (à dire franchement)

dYdX est un **perp DEX** : prix **continus**, pas de YES/NO qui se résout à 1 $,
et c'est un **CLOB temps réel** collé au prix index (pas de retard de 30–90 s à
exploiter). Conséquences :

- Il n'existe **aucun « résultat presque déterminé »** à arbitrer sur un perp.
- Copier un smart-wallet en directionnel sur dYdX = **prendre un vrai risque de
  marché**. Un bot de copie directionnel **ne peut pas** afficher 95–99 % de
  réussite. Quiconque le promet vend du rêve.
- **Et même sur Polymarket, cet edge est MORT** depuis janvier 2026 : les
  nouveaux taker fees (~1,56 % à 50/50) dépassent le spread exploitable. Un bot
  qui faisait 515 k$/mois à 99 % « est maintenant complètement mort ».

Donc viser « comme le bot viral » au sens « ne jamais se tromper » est un
**objectif impossible sur dYdX** — non par manque de code, mais par nature du
marché.

## 3. Ce qui EST adaptable (honnêtement)

| Principe du bot Polymarket | Adaptation dYdX réaliste | Statut |
|---|---|---|
| N'agir que sur du quasi-certain | **Sélectivité extrême** : consensus multi-wallets prouvés + edge ≫ coûts + frais + frais. Moins d'erreurs, jamais 98 %. | ✅ en place |
| Edge structurel sans risque | **Edges market-neutral** sur perps : funding-rate arb, basis perp/spot, cross-venue. = un AUTRE bot (delta-neutre), pas de la copie. | 🔧 piste future |
| Réaction ultra-rapide | **Scan temps réel < 1 s** (déjà fait) — utile pour capter l'edge d'un leader avant qu'il se dissipe. | ✅ |
| Valider que ça gagne vraiment | **Backtest** sur fills réels → ne copier que les wallets net-positifs. | ✅ `tools/dydx_pnl_sweep.py` |

## 4. Pourquoi NOTRE moteur ne trouvait AUCUNE opportunité

Cause n°1 : **3 marchés autorisés seulement** (`FOCUS_MARKETS` = BTC/ETH/SOL).
Le moteur refuse tout le reste. Pour qu'un consensus de 2 wallets se forme sur
*exactement* l'un de ces 3 marchés, dans la fenêtre fraîche, avec ~9 wallets
suivis → quasi impossible.

Corrigé (2026-06-12) :
- **Marchés élargis à 16 perps liquides** (DOGE, AVAX, LINK, SUI, XRP, LTC, BNB,
  NEAR, APT, ARB, OP, TIA, WLD + BTC/ETH/SOL). Les gates liquidité/edge gardent la
  qualité.
- **Shortlist de décision élargie à 60 wallets** (découverte Cosmos).
→ Le consensus peut enfin se former, sans baisser la barre de qualité.

## 5. Le bon objectif (réaliste, non maquillé)

Pas « ne jamais perdre » (impossible sur perps directionnels). Mais :
**peu de trades, propres, à espérance positive après coûts**, validés sur
l'historique. C'est la version honnête du « bot qui se trompe peu ».

## Sources
- [How AI traders exploit prediction-market glitches (CoinDesk)](https://www.coindesk.com/markets/2026/02/21/how-ai-is-helping-retail-traders-exploit-prediction-market-glitches-to-make-easy-money)
- [Beyond simple arbitrage: 4 Polymarket strategies (2026)](https://medium.com/illumination/beyond-simple-arbitrage-4-polymarket-strategies-bots-actually-profit-from-in-2026-ddacc92c5b4f)
- [Latency arbitrage in 15-minute crypto markets (Indie Hackers)](https://www.indiehackers.com/post/latency-arbitrage-in-15-minute-crypto-markets-building-a-polymarket-trading-edge-2026-f77cc226c0)
- [Arbitrage bots dominate Polymarket (Yahoo Finance)](https://finance.yahoo.com/news/arbitrage-bots-dominate-polymarket-millions-100000888.html)
- [Polymarket BTC 5m market-making & arbitrage guide](https://academy.exmon.pro/polymarket-btc-5m-trading-market-making-arbitrage-guide)
