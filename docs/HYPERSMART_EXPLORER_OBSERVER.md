# HyperSmart Explorer Observer

L'observer Explorer est experimental et desactive par defaut.

Regles:

- aucun endpoint prive;
- aucune authentification;
- aucun contournement;
- rate limit strict;
- import manuel possible;
- action ambigue classee `UNKNOWN`.

Les donnees Explorer sont des observations publiques ou des imports, jamais une source d'execution.
## Docs-to-code checklist

- [x] Explorer remains experimental.
- [x] No aggressive scraping policy documented.
- [ ] Manual explorer export parser.
- [ ] Provider health status for explorer disabled/default.
- [ ] Tests proving explorer provider is disabled by default.
