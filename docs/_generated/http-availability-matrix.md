# HTTP Availability Matrix

Generated from the mode-aware OpenAPI contract.

| Domain | `full` | `local` | `ha_addon` |
| --- | --- | --- | --- |
| `control-plane` | `read`, `commands` | `read`, `commands` | `read` |
| `hypothesis` | `read`, `commands`, `jobs`, `streams` | `read`, `commands`, `jobs`, `streams` | `read`, `commands` |
| `indicators` | `read` | `read` | `read` |
| `market-data` | `read`, `commands`, `jobs` | `read`, `commands`, `jobs` | `read`, `commands`, `jobs` |
| `market-structure` | `read`, `commands`, `jobs`, `onboarding`, `webhooks` | `read`, `commands`, `jobs`, `onboarding`, `webhooks` | `read`, `commands`, `webhooks` |
| `news` | `read`, `commands`, `jobs`, `onboarding` | `read`, `commands`, `jobs`, `onboarding` | `read` |
| `patterns` | `read`, `commands` | `read`, `commands` | `read`, `commands` |
| `portfolio` | `read` | `read` | `read` |
| `predictions` | `read` | `read` | `read` |
| `signals` | `read`, `backtests`, `decisions`, `final-signals`, `market-decisions`, `strategies` | `read`, `backtests`, `decisions`, `final-signals`, `market-decisions`, `strategies` | `read`, `backtests`, `decisions`, `final-signals`, `market-decisions`, `strategies` |
| `system` | `read`, `operations` | `read`, `operations` | `read`, `operations` |

## Route Counts

| Domain | Category | `full` | `local` | `ha_addon` |
| --- | --- | ---: | ---: | ---: |
| `control-plane` | `read` | 10 | 10 | 10 |
| `control-plane` | `commands` | 7 | 7 | 0 |
| `hypothesis` | `read` | 3 | 3 | 3 |
| `hypothesis` | `commands` | 3 | 3 | 3 |
| `hypothesis` | `jobs` | 1 | 1 | 0 |
| `hypothesis` | `streams` | 1 | 1 | 0 |
| `indicators` | `read` | 4 | 4 | 4 |
| `market-data` | `read` | 2 | 2 | 2 |
| `market-data` | `commands` | 3 | 3 | 3 |
| `market-data` | `jobs` | 1 | 1 | 1 |
| `market-structure` | `read` | 5 | 5 | 5 |
| `market-structure` | `commands` | 4 | 4 | 4 |
| `market-structure` | `jobs` | 2 | 2 | 0 |
| `market-structure` | `onboarding` | 10 | 10 | 0 |
| `market-structure` | `webhooks` | 2 | 2 | 2 |
| `news` | `read` | 3 | 3 | 3 |
| `news` | `commands` | 3 | 3 | 0 |
| `news` | `jobs` | 1 | 1 | 0 |
| `news` | `onboarding` | 6 | 6 | 0 |
| `patterns` | `read` | 7 | 7 | 7 |
| `patterns` | `commands` | 2 | 2 | 2 |
| `portfolio` | `read` | 3 | 3 | 3 |
| `predictions` | `read` | 1 | 1 | 1 |
| `signals` | `read` | 2 | 2 | 2 |
| `signals` | `backtests` | 3 | 3 | 3 |
| `signals` | `decisions` | 3 | 3 | 3 |
| `signals` | `final-signals` | 3 | 3 | 3 |
| `signals` | `market-decisions` | 3 | 3 | 3 |
| `signals` | `strategies` | 2 | 2 | 2 |
| `system` | `read` | 2 | 2 | 2 |
| `system` | `operations` | 3 | 3 | 3 |
