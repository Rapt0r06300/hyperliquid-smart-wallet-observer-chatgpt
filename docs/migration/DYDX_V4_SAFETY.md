# Règles de sécurité absolue — dYdX v4

## Règle fondamentale

**Ce module est READ-ONLY / PAPER-ONLY / TESTNET-FIRST / DENY-BY-DEFAULT.**

Un signal n'est jamais un ordre.  
Un paper trade n'est jamais un ordre.  
Aucun argent réel. Aucune clé privée. Aucune signature.

## Valeurs interdites

Les paramètres suivants lèvent une `ValueError` immédiatement à l'init:

```python
DydxV4Config(allow_trading=True)       # INTERDIT
DydxV4Config(allow_private_key=True)   # INTERDIT
DydxV4Config(paper_only=False)         # INTERDIT
DydxV4Config(read_only=False)          # INTERDIT
```

`load_config_from_env()` force toujours ces valeurs à `False/True`
indépendamment des variables d'environnement.

## Mots-clés interdits dans les URLs et payloads

```python
FORBIDDEN_KEYWORDS = frozenset({
    "private_key", "mnemonic", "seed", "signature",
    "/orders", "/transfers", "/withdraw", "/deposit",
    "broadcast", "sendTransaction", "signTransaction",
    "wallet_connect",
})
```

## Séparation des modes

Le PnL LIVE ne peut jamais être contaminé par:
- BACKTEST (fills historiques rejouées)
- REPLAY (debug)
- TEST_FIXTURE (adresses de test connues)

Chaque mode a une `PaperSession` isolée dans `DydxPaperSimulator`.

## Adresses de test (exclues du PnL live)

```python
TEST_FIXTURE_ADDRESSES = {
    "0x1111111111111111111111111111111111111111",
    "0x2222222222222222222222222222222222222222",
    "0x0000000000000000000000000000000000000000",
    "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
}
```

## Vérification en test

```
tests/dydx_v4/test_dydx_safety_and_config.py — 34 tests
- TestDefaultConfig: config safe par défaut
- TestSafetyViolations: ValueError sur paramètres dangereux
- TestAssertPaperOnly: gate paper_only
- TestUrlSafety: URLs interdites rejetées
- TestPayloadSafety: payloads interdits rejetés
- TestSignalGate: signaux trop vieux rejetés
- TestAuditConfig: audit complet de la config
```

## Vérification manuelle

```bash
python -m hyper_smart_observer.dydx_v4.cli safety-check
python -m hyper_smart_observer.dydx_v4.cli runtime-check
```
