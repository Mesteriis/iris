# ADR 0020: Dependency Direction Rules and Import Boundaries

## Status

Accepted

## Date

2026-03-16

## Context

IRIS uses a domain-oriented package structure:

- `iris.api`
- `iris.apps.<domain>`
- `iris.core`
- `iris.runtime`

Each domain inside `iris.apps` is organized into layers:

- `api`
- `application`
- `domain`
- `infrastructure`
- `contracts`

Without a formal dependency-direction model, even a clean structure degrades quickly:

- `api` starts containing orchestration
- `domain` starts importing SQLAlchemy models
- one domain reaches into another domain’s repositories
- `contracts` start depending on transport or ORM details
- `core` turns into a junk-drawer shared bucket

The architecture must therefore define explicitly:

- who may import whom
- which dependencies are allowed
- which dependencies are forbidden
- which boundaries are enforced by linter and CI

## Decision

IRIS uses a unidirectional dependency model.

This is a binding dependency model. CI-enforced service-layer scanners now run against the active codebase, and broader package-boundary checks are ratcheted tighter as compatibility entrypoints are removed.

The core principle:

Dependencies point inward toward more stable and more abstract layers.

A more external layer may depend on a more internal layer.
A more internal layer must not depend on a more external layer.

### Canonical Dependency Direction

Within a domain, the allowed direction is:

```text
api -> application -> domain
infrastructure -> domain
```

`infrastructure -> application.contracts` is allowed only where needed for persistence or adapter mapping.

`application -> contracts` is allowed.

`api -> contracts` is allowed.

`domain -> contracts` is forbidden by default, except for explicitly permitted truly domain-owned contracts.

### Layer Intent

`domain`

The most stable layer of business logic.

Contains:

- entities
- value objects
- policies
- domain events
- enums
- domain exceptions

The domain does not know about transport, ORM, frameworks, API, cache, or external integrations.

`application`

The use-case and orchestration layer.

Contains:

- commands
- queries
- application services
- orchestration logic
- transaction coordination

The application layer uses domain objects and contracts, but must not depend on transport details.

`api`

The transport-adapter layer.

Contains:

- routes
- request parsing
- response serialization
- dependency wiring
- error mapping
- localization rendering

The API layer must not contain business logic and must not work directly with ORM models.

`infrastructure`

The technical-adapter implementation layer.

Contains:

- ORM models
- repositories
- query implementations
- cache adapters
- external service adapters
- integration clients

Infrastructure implements dependencies required by application and domain, but does not own business rules.

`contracts`

Typed boundary objects.

Contains:

- command DTOs
- response DTOs
- read models
- event payload contracts

Contracts must remain lightweight and stable.

### Allowed Dependencies Inside a Domain

`api` may import:

- `application`
- `contracts`
- `domain` only for stable enums or exceptions when necessary, but preferably through application or contracts
- `iris.core`

`application` may import:

- `domain`
- `contracts`
- `iris.core`

`domain` may import:

- only `iris.core` modules explicitly designated as domain-safe
- standard library
- internal same-layer domain modules

`infrastructure` may import:

- `domain`
- `contracts`
- application interfaces, protocols, or ports
- `iris.core`

`contracts` may import:

- standard library
- `pydantic`, `typing`, and tiny shared primitives
- `iris.core` only if extremely lightweight and stable

Contracts must not import domain services, infrastructure models, or transport code.

### Forbidden Dependencies Inside a Domain

`domain` must not import:

- `api`
- `application`
- `infrastructure`
- ORM models
- repositories
- framework-specific request or response objects
- cache clients
- external SDKs unless explicitly wrapped as rare domain-safe abstractions

`application` must not import:

- `api`
- FastAPI request or response classes
- ORM session-management details unless abstracted
- transport-layer serializers

`api` must not import:

- infrastructure ORM models
- raw repositories directly when an application layer exists for the same use case
- business rules embedded in endpoints

`contracts` must not import:

- `api`
- `application.services`
- `infrastructure`
- ORM models
- transport-framework types

### Cross-Domain Dependency Rules

A domain must not import another domain’s internals.

Another domain may be imported only through:

- contracts
- explicitly declared public facades
- rare shared abstractions moved into `iris.core`

### Forbidden Cross-Domain Imports

Forbidden:

- `iris.apps.<other_domain>.api.*`
- `iris.apps.<other_domain>.infrastructure.*`
- `iris.apps.<other_domain>.repositories.*`
- `iris.apps.<other_domain>.models.*`
- `iris.apps.<other_domain>.application.services.*` directly, unless this is an explicit public facade

### Cross-Domain Interaction Principle

If one domain needs another domain, it must depend on one of these instead of internals:

- a public contract
- a public application facade
- a shared event contract
- a shared abstraction in `iris.core`, only when it is truly a platform-level concern

### Core Rules

`iris.core` is a shared kernel, not a dumping ground.

Only the following are allowed in `core`:

- config
- logging
- i18n
- shared error base classes
- telemetry primitives
- platform-safe utility abstractions
- foundational typing helpers

Code must not be moved into `core` just to bypass domain boundaries.

### Core Dependency Policy

All layers may import `iris.core`, but only its stable, layer-safe parts.

`core` must not become a backdoor for hidden coupling between domains.

If a module in `core` depends on a concrete domain, it does not belong in `core`.

### Runtime Rules

`iris.runtime` may import:

- `iris.apps.*.application`
- `iris.apps.*.contracts`
- selected infrastructure adapters where orchestration genuinely requires them
- `iris.core`

Domain packages must not depend on runtime.

### Main Composition Rule

The composition root lives at the top level:

- `iris.main`
- transport bootstrap
- runtime bootstrap
- DI wiring
- app assembly

The composition root is what ties together:

- routes
- application services
- infrastructure implementations
- runtime processes

Lower layers must not assemble the application themselves.

### Dependency Matrix

Allowed matrix inside a domain:

- `api -> application`: allowed
- `api -> contracts`: allowed
- `api -> domain`: limited and discouraged
- `api -> infrastructure`: discouraged, allowed only by explicit migration exception
- `application -> domain`: allowed
- `application -> contracts`: allowed
- `application -> infrastructure`: forbidden except through abstraction, protocol, or port boundaries
- `domain -> application`: forbidden
- `domain -> api`: forbidden
- `domain -> infrastructure`: forbidden
- `domain -> contracts`: forbidden by default
- `infrastructure -> domain`: allowed
- `infrastructure -> contracts`: allowed
- `infrastructure -> application`: allowed only for ports, protocols, or interfaces, not concrete orchestration flows
- `infrastructure -> api`: forbidden
- `contracts -> domain`: forbidden
- `contracts -> application`: forbidden
- `contracts -> infrastructure`: forbidden
- `contracts -> api`: forbidden

### Ports and Protocols Rule

If the application layer needs an infrastructure implementation, the dependency must go through a port, protocol, or interface declared in `application` or in a dedicated stable boundary module.

Example:

```text
application/ports/market_data_reader.py
infrastructure/repositories/sql_market_data_reader.py
```

The application layer knows the contract; infrastructure knows the implementation.

### ORM Isolation Rule

ORM models must live only in infrastructure.

They must not leak into:

- `domain`
- `contracts`
- `api`

Domain entities and ORM models are not the same thing.

### Transport Isolation Rule

FastAPI, HTTP, SSE, WebSocket, and request or response objects must live only in `api` and the composition root.

They must not appear in:

- `domain`
- `application`
- `contracts`

### Localization Boundary Rule

Localization must happen in boundary layers:

- `api`
- UI
- integration-rendering layers

Domain and application layers must not generate user-facing text.

### Exceptions Policy

Domain exceptions:

- define the business meaning of an error

Application exceptions:

- define orchestration and use-case failures

API error mapping:

- turns exceptions into transport-safe responses and localized messages

The API layer must not push raw framework-specific exceptions into the domain, and the domain must not know the transport error shape.

### Temporary Migration Exceptions

During refactoring, temporary violations are allowed only if they:

- are documented
- are marked with `TODO` and an owner
- have a removal deadline
- are not disguised as the target architecture

Temporary exceptions are not part of the standard.

### CI Enforcement

Architectural constraints should be checked automatically where possible.

Recommended tools:

- `import-linter`
- `deptry`
- `ruff`
- custom architecture checks

CI should progressively enforce:

- `domain` does not import `infrastructure`
- `contracts` do not import ORM or API code
- cross-domain imports go only through contracts or approved facades
- `src.*` is absent from product code
- relative imports deeper than `..` are absent

## Consequences

### Positive

- real rather than decorative bounded contexts
- predictable dependency architecture
- less hidden coupling
- easier refactoring and testing
- easier automated architectural enforcement in CI

### Negative

- stronger discipline is required when adding new modules
- some legacy code will need migration
- sometimes extra ports or contracts will be needed instead of “quick direct imports”

These costs are considered acceptable.

### Result

IRIS uses a strict dependency-direction model where:

- dependencies point to more stable layers
- the domain is isolated from transport and infrastructure
- cross-domain links are controlled
- `core` is not used as a shortcut
- architectural boundaries can be verified automatically

## See also

- [ADR 0019: Package Structure and Import Rules](0019-package-structure-import-rules.md) — package structure
- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — infrastructure layer
- [ADR 0009: Signals Service/Engine Split](0009-signals-service-engine-split.md) — example of layer separation
