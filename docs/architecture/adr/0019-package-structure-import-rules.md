# ADR 0019: Package Structure, Import Rules, and Source Root Policy

## Status

Proposed

## Date

2026-02-01

## Context

IRIS is an analytical platform built around:

- domain-oriented modules
- bounded contexts
- event-driven orchestration
- layered architecture
- strict separation of concerns

As the project grows, the following risks appear:

- chaotic package structure
- implicit dependencies between domains
- the spread of generic "utility" files
- deep relative imports
- mixing infrastructure and domain logic

In addition, the current structure uses `src` as the source root, which leads to imports such as:

```python
from src.apps.signals.services import ...
```

That couples the code to the repository layout and reduces readability.

A standard is therefore needed to:

- make project structure predictable
- make domain dependencies explicit
- remove the infrastructure namespace `src` from product code
- establish one product namespace: `iris`

## Decision

IRIS uses a single product namespace: `iris`.

All product imports must begin with:

```python
iris.*
```

`src/` is used only as repository layout and is not part of the product namespace.

### Source Root Policy

Repository layout:

```text
backend/
  src/
    iris/
```

Example:

```text
backend/src/iris/apps/signals
```

Import:

```python
from iris.apps.signals.application.services.build_signal_snapshot import ...
```

Forbidden:

```python
from src.apps.signals ...
```

`src` is a layout concern, not part of the runtime namespace.

This is a target-state decision. The repository has not been fully migrated to it yet, so until the migration rollout is complete, this decision is not an enforceable baseline for the whole `backend/src` tree.

### Project Package Layout

Backend package structure:

```text
iris/
  api/
  apps/
  core/
  runtime/
  main.py
```

### Package Responsibilities

`iris.api`

HTTP and transport layer.

Contains:

- routers
- dependencies
- request mapping
- response mapping
- error translation

Business logic is forbidden here.

`iris.apps`

Bounded contexts.

Each product domain is implemented as a dedicated package.

Examples:

- `iris.apps.signals`
- `iris.apps.market_data`
- `iris.apps.control_plane`
- `iris.apps.settings`

`iris.core`

Shared platform kernel.

Contains:

- configuration
- i18n
- logging
- base error classes
- telemetry
- shared utilities

`core` must remain minimal and stable.

`iris.runtime`

Infrastructure runtime:

- workers
- stream processors
- schedulers
- event-loop orchestration

### Domain Package Structure

Each domain in `iris.apps` must follow the same structure.

```text
apps/<domain>/
  api/
  application/
  domain/
  infrastructure/
  contracts/
```

### Layer Responsibilities

`api`

Transport adapters.

Examples:

- `routes.py`
- `read_routes.py`
- `write_routes.py`
- `dependencies.py`
- `error_mapping.py`

`application`

Use cases and orchestration.

Contains:

- `commands/`
- `queries/`
- `services/`

Example files:

- `create_signal.py`
- `activate_strategy.py`
- `list_signals.py`
- `refresh_market_data.py`

`domain`

Pure domain model.

Contains:

- `entities.py`
- `value_objects.py`
- `events.py`
- `exceptions.py`
- `enums.py`
- `policies/`

The domain layer does not depend on infrastructure.

`infrastructure`

Persistence and integrations.

Contains:

- `models.py`
- `repositories/`
- `queries/`
- `cache/`
- `integrations/`

`contracts`

Typed contracts between layers.

Contains:

- `commands.py`
- `responses.py`
- `read_models.py`
- `events.py`

### File Naming Rules

A file must describe a concrete responsibility.

Allowed:

- `refresh_market_data.py`
- `build_signal_snapshot.py`
- `activate_strategy.py`
- `signal_history_query.py`

Forbidden:

- `utils.py`
- `helpers.py`
- `common.py`
- `misc.py`
- `manager.py`
- `processor.py`
- `service.py`

Such names are treated as architectural smells.

### Avoid Tautological Naming

The path already contains the architectural layer.

Bad:

```text
application/services/signal_service.py
domain/models/domain_models.py
```

Good:

```text
application/services/build_signal_snapshot.py
domain/entities.py
```

### Aggregator Files

Files such as:

- `repositories.py`
- `schemas.py`
- `models.py`

are allowed only if:

- they are small
- they contain a logically related object group

As they grow, they must be split.

### Import Rules

#### Within the Same Domain

Relative imports are allowed.

Example:

```python
from .exceptions import SignalError
from ..contracts.read_models import SignalSummary
```

#### Cross-Domain Imports

Cross-domain imports must be absolute.

Example:

```python
from iris.apps.market_data.contracts.read_models import MarketSnapshot
```

Forbidden:

```python
from ...market_data.contracts import MarketSnapshot
```

#### Relative Import Depth

Relative imports deeper than `..` are forbidden.

Allowed:

- `.`
- `..`

Forbidden:

- `...`
- `....`

### Cross-Domain Dependency Rules

A domain may import another domain only through public modules.

Allowed:

- contracts
- public facades

Forbidden:

- API
- infrastructure
- repositories
- ORM models
- private services

Example of a bad import:

```python
from iris.apps.market_data.infrastructure.models import MarketModel
```

### Core Imports

`iris.core` is imported only through absolute imports.

```python
from iris.core.config import settings
```

### Test Imports

Tests may use additional import-path configuration.

`src` may be used as a source root in the test environment.

However, product code must not use the `src` namespace.

### Architectural Goal

Project structure must provide:

- readable paths
- explicit domain boundaries
- minimal coupling
- easy refactoring
- architectural scalability

## Consequences

### Positive

IRIS gains:

- one stable namespace: `iris`
- a strict domain-package structure
- clear file names
- controlled cross-domain dependencies
- a predictable import system

That makes the architecture more resilient as the system grows.

### Negative

- a phased migration from the existing `src.*` namespace will be required
- until migration is complete, the repository will live in a mixed state
- some CI constraints cannot be enabled as immediate hard failures

## See also

- [ADR 0020: Dependency Direction Rules and Import Boundaries](0020-dependency-direction-import-boundaries.md) — dependency-direction rules
- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — infrastructure layer
