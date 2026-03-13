# Application Bootstrap

<cite>
**Referenced Files in This Document**
- [src/main.py](file://src/main.py)
- [src/core/bootstrap/app.py](file://src/core/bootstrap/app.py)
- [src/core/bootstrap/lifespan.py](file://src/core/bootstrap/lifespan.py)
- [src/core/settings/base.py](file://src/core/settings/base.py)
- [src/core/db/session.py](file://src/core/db/session.py)
- [src/migrations/env.py](file://src/migrations/env.py)
- [alembic.ini](file://alembic.ini)
- [src/runtime/orchestration/broker.py](file://src/runtime/orchestration/broker.py)
- [src/runtime/streams/runner.py](file://src/runtime/streams/runner.py)
- [src/apps/system/views.py](file://src/apps/system/views.py)
- [src/apps/system/services.py](file://src/apps/system/services.py)
- [src/runtime/scheduler/__init__.py](file://src/runtime/scheduler/__init__.py)
- [src/core/db/persistence.py](file://src/core/db/persistence.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)

## Introduction
This document explains the IRIS application bootstrap process. It covers how the FastAPI application is created, how routers for feature modules are registered, how CORS middleware is configured, and how the lifespan is deferred and managed. It also documents the dynamic import system used to load routers, Alembic migration integration, conditional feature loading based on settings, the application initialization sequence, dependency injection setup, startup/shutdown procedures, configuration options for different environments, error handling during bootstrapping, and performance considerations for application startup.

## Project Structure
The bootstrap pipeline centers around three primary files:
- Application entrypoint and server runner
- FastAPI application factory and router registration
- Lifespan manager coordinating startup and shutdown

```mermaid
graph TB
A["src/main.py<br/>Entry point and Uvicorn runner"] --> B["src/core/bootstrap/app.py<br/>FastAPI app factory and router registration"]
B --> C["src/core/bootstrap/lifespan.py<br/>Deferred lifespan manager"]
C --> D["src/core/db/session.py<br/>Database connectivity helpers"]
C --> E["src/runtime/orchestration/broker.py<br/>Taskiq brokers"]
C --> F["src/runtime/streams/runner.py<br/>Event worker processes"]
C --> G["src/runtime/scheduler/__init__.py<br/>Scheduler entrypoints"]
B --> H["src/core/settings/base.py<br/>Environment settings"]
B --> I["src/migrations/env.py<br/>Alembic env configuration"]
I --> J["alembic.ini<br/>Alembic configuration"]
```

**Diagram sources**
- [src/main.py:1-22](file://src/main.py#L1-L22)
- [src/core/bootstrap/app.py:1-81](file://src/core/bootstrap/app.py#L1-L81)
- [src/core/bootstrap/lifespan.py:1-70](file://src/core/bootstrap/lifespan.py#L1-L70)
- [src/core/db/session.py:1-72](file://src/core/db/session.py#L1-L72)
- [src/runtime/orchestration/broker.py:1-23](file://src/runtime/orchestration/broker.py#L1-L23)
- [src/runtime/streams/runner.py:1-84](file://src/runtime/streams/runner.py#L1-L84)
- [src/runtime/scheduler/__init__.py:1-30](file://src/runtime/scheduler/__init__.py#L1-L30)
- [src/core/settings/base.py:1-90](file://src/core/settings/base.py#L1-L90)
- [src/migrations/env.py:1-56](file://src/migrations/env.py#L1-L56)
- [alembic.ini:1-38](file://alembic.ini#L1-L38)

**Section sources**
- [src/main.py:1-22](file://src/main.py#L1-L22)
- [src/core/bootstrap/app.py:1-81](file://src/core/bootstrap/app.py#L1-L81)
- [src/core/bootstrap/lifespan.py:1-70](file://src/core/bootstrap/lifespan.py#L1-L70)

## Core Components
- FastAPI application factory: Creates the ASGI app, sets title from settings, registers CORS middleware, and conditionally includes routers for feature modules.
- Deferred lifespan manager: Coordinates database readiness, waits for Redis, runs Alembic migrations, starts brokers and workers, and orchestrates cleanup on shutdown.
- Settings provider: Centralized configuration with environment-specific defaults and normalization.
- Database session helpers: Async engine and retry logic for database connectivity.
- Alembic integration: Configures Alembic via environment and settings, and exposes a migration runner callable attached to app state.
- Runtime components: Taskiq brokers, event worker processes, and scheduler entrypoints are started and stopped within the lifespan.

**Section sources**
- [src/core/bootstrap/app.py:37-81](file://src/core/bootstrap/app.py#L37-L81)
- [src/core/bootstrap/lifespan.py:22-70](file://src/core/bootstrap/lifespan.py#L22-L70)
- [src/core/settings/base.py:8-90](file://src/core/settings/base.py#L8-L90)
- [src/core/db/session.py:19-72](file://src/core/db/session.py#L19-L72)
- [src/migrations/env.py:11-56](file://src/migrations/env.py#L11-L56)
- [alembic.ini:1-38](file://alembic.ini#L1-L38)

## Architecture Overview
The bootstrap architecture follows a layered approach:
- Entry point initializes the app and runs the server.
- App factory constructs the FastAPI instance, configures CORS, and registers routers.
- Lifespan performs pre-flight checks (database and Redis), runs migrations, starts background systems, and manages shutdown.

```mermaid
sequenceDiagram
participant Entrypoint as "src/main.py"
participant Factory as "src/core/bootstrap/app.py"
participant Lifespan as "src/core/bootstrap/lifespan.py"
participant DB as "src/core/db/session.py"
participant Alembic as "src/migrations/env.py"
participant Settings as "src/core/settings/base.py"
Entrypoint->>Factory : create_app()
Factory->>Settings : get_settings()
Factory->>Factory : configure CORS and include routers
Factory-->>Entrypoint : FastAPI app
Entrypoint->>Entrypoint : uvicorn.run(app)
Entrypoint->>Lifespan : lifespan(app) enter
Lifespan->>DB : wait_for_database()
Lifespan->>DB : wait_for_redis()
Lifespan->>Alembic : run_migrations()
Lifespan-->>Entrypoint : yield to serve requests
Entrypoint->>Lifespan : lifespan(app) exit
Lifespan->>Lifespan : stop workers, shutdown brokers, cleanup
```

**Diagram sources**
- [src/main.py:8-22](file://src/main.py#L8-L22)
- [src/core/bootstrap/app.py:49-81](file://src/core/bootstrap/app.py#L49-L81)
- [src/core/bootstrap/lifespan.py:22-70](file://src/core/bootstrap/lifespan.py#L22-L70)
- [src/core/db/session.py:61-72](file://src/core/db/session.py#L61-L72)
- [src/migrations/env.py:34-56](file://src/migrations/env.py#L34-L56)
- [src/core/settings/base.py:87-90](file://src/core/settings/base.py#L87-L90)

## Detailed Component Analysis

### FastAPI Application Creation Workflow
- Dynamic router imports: Routers are imported from feature modules and included in the app. Conditional inclusion is supported for the hypothesis engine router based on settings.
- CORS middleware: Configured using origins from settings with permissive allow-all methods and headers.
- Deferred lifespan: The lifespan is attached as an async context manager so that startup steps occur before serving requests and shutdown occurs after.

```mermaid
flowchart TD
Start(["create_app()"]) --> InitApp["Initialize FastAPI with title from settings"]
InitApp --> ConfigureCORS["Add CORSMiddleware with origins from settings"]
ConfigureCORS --> IncludeRouters["include_router for system/control_plane/market_data/market_structure/news/indicators/patterns/signals/portfolio/predictions"]
IncludeRouters --> ConditionalRouter{"enable_hypothesis_engine?"}
ConditionalRouter --> |Yes| IncludeHypothesis["include_router for hypothesis_engine"]
ConditionalRouter --> |No| SkipHypothesis["Skip hypothesis router"]
IncludeHypothesis --> SetMigrations["Attach run_migrations to app.state"]
SkipHypothesis --> SetMigrations
SetMigrations --> ReturnApp(["Return FastAPI app"])
```

**Diagram sources**
- [src/core/bootstrap/app.py:49-81](file://src/core/bootstrap/app.py#L49-L81)

**Section sources**
- [src/core/bootstrap/app.py:49-81](file://src/core/bootstrap/app.py#L49-L81)

### Router Registration for Feature Modules
- Routers are imported from feature modules and registered in a fixed order. The hypothesis engine router is included conditionally based on a setting.
- The system router is always included to expose health and status endpoints.

**Section sources**
- [src/core/bootstrap/app.py:21-31](file://src/core/bootstrap/app.py#L21-L31)
- [src/core/bootstrap/app.py:68-79](file://src/core/bootstrap/app.py#L68-L79)

### CORS Middleware Configuration
- Origins are loaded from settings and normalized. The middleware allows credentials, all methods, and all headers.

**Section sources**
- [src/core/bootstrap/app.py:60-66](file://src/core/bootstrap/app.py#L60-L66)
- [src/core/settings/base.py:25-31](file://src/core/settings/base.py#L25-L31)
- [src/core/settings/base.py:79-84](file://src/core/settings/base.py#L79-L84)

### Deferred Lifespan Management
- Pre-start:
  - Wait for database connectivity with retries.
  - Wait for Redis connectivity with retries.
  - Run Alembic migrations synchronously using a thread executor to avoid blocking the event loop.
  - Register legacy receivers synchronously.
- Runtime:
  - Start Taskiq brokers.
  - Spawn taskiq worker processes and event worker processes.
  - Start scheduler tasks.
- Shutdown:
  - Signal schedulers to finish and await their completion.
  - Stop worker processes.
  - Shutdown brokers and reset internal message buses.
  - Close async task lock client and market source carousel.

```mermaid
flowchart TD
Enter(["lifespan(app) enter"]) --> DBWait["wait_for_database()"]
DBWait --> RedisWait["wait_for_redis()"]
RedisWait --> Migrate["run_migrations() in thread"]
Migrate --> RegisterReceivers["register_default_receivers() in thread"]
RegisterReceivers --> StartBrokers["broker.startup(), analytics_broker.startup()"]
StartBrokers --> SpawnWorkers["spawn_taskiq_worker_processes()<br/>spawn_event_worker_processes()"]
SpawnWorkers --> StartScheduler["start_scheduler(app, events)"]
StartScheduler --> Serve(["yield to serve requests"])
Serve --> Exit(["lifespan(app) exit"])
Exit --> StopScheduler["set finish_event, await scheduler tasks"]
StopScheduler --> StopWorkers["stop_taskiq_worker_processes(), stop_event_worker_processes()"]
StopWorkers --> ShutdownBrokers["analytics_broker.shutdown(), broker.shutdown()"]
ShutdownBrokers --> Cleanup["reset_message_bus(), reset_event_publisher(), close_async_task_lock_client(), carousel.close()"]
```

**Diagram sources**
- [src/core/bootstrap/lifespan.py:22-70](file://src/core/bootstrap/lifespan.py#L22-L70)
- [src/core/db/session.py:61-72](file://src/core/db/session.py#L61-L72)
- [src/runtime/orchestration/broker.py:12-22](file://src/runtime/orchestration/broker.py#L12-L22)
- [src/runtime/streams/runner.py:50-84](file://src/runtime/streams/runner.py#L50-L84)
- [src/runtime/scheduler/__init__.py:1-30](file://src/runtime/scheduler/__init__.py#L1-L30)

**Section sources**
- [src/core/bootstrap/lifespan.py:22-70](file://src/core/bootstrap/lifespan.py#L22-L70)

### Dynamic Import System
- Routers are imported dynamically at module level in the app factory. This enables clean separation of concerns and straightforward registration without circular imports at import time.
- Conditional inclusion is performed based on settings, allowing feature toggles without modifying the import list.

**Section sources**
- [src/core/bootstrap/app.py:21-31](file://src/core/bootstrap/app.py#L21-L31)
- [src/core/bootstrap/app.py:78-79](file://src/core/bootstrap/app.py#L78-L79)

### Alembic Migration Integration
- Alembic configuration is loaded from the repository’s alembic.ini and adjusted programmatically to set the script location and SQLAlchemy URL from settings.
- A callable is attached to app state to run migrations asynchronously via a thread executor during startup.
- The Alembic env script reads settings and configures metadata and offline/online modes accordingly.

```mermaid
sequenceDiagram
participant App as "src/core/bootstrap/app.py"
participant Env as "src/migrations/env.py"
participant AlembicIni as "alembic.ini"
participant Settings as "src/core/settings/base.py"
App->>Settings : get_settings()
App->>Env : get_alembic_config()
Env->>Settings : get_settings()
Env->>AlembicIni : read configuration
Env-->>App : Alembic Config
App->>App : app.state.run_migrations = run_migrations
App->>App : run_migrations() called in lifespan
```

**Diagram sources**
- [src/core/bootstrap/app.py:37-47](file://src/core/bootstrap/app.py#L37-L47)
- [src/migrations/env.py:11-56](file://src/migrations/env.py#L11-L56)
- [alembic.ini:1-38](file://alembic.ini#L1-L38)
- [src/core/settings/base.py:87-90](file://src/core/settings/base.py#L87-L90)

**Section sources**
- [src/core/bootstrap/app.py:37-47](file://src/core/bootstrap/app.py#L37-L47)
- [src/migrations/env.py:11-56](file://src/migrations/env.py#L11-L56)
- [alembic.ini:1-38](file://alembic.ini#L1-L38)

### Conditional Feature Loading Based on Settings
- The hypothesis engine router is included only when the corresponding setting is enabled. This allows enabling/disabling features without changing the app factory code.

**Section sources**
- [src/core/bootstrap/app.py:78-79](file://src/core/bootstrap/app.py#L78-L79)
- [src/core/settings/base.py:53](file://src/core/settings/base.py#L53)

### Application Initialization Sequence
- Load settings.
- Create FastAPI app with title from settings.
- Add CORS middleware using settings.
- Include routers for system and all major feature domains.
- Conditionally include the hypothesis router.
- Attach migration runner to app state.
- Run via Uvicorn with host/port from settings.

**Section sources**
- [src/main.py:8-22](file://src/main.py#L8-L22)
- [src/core/bootstrap/app.py:49-81](file://src/core/bootstrap/app.py#L49-L81)
- [src/core/settings/base.py:87-90](file://src/core/settings/base.py#L87-L90)

### Dependency Injection Setup
- Database sessions are provided via an async generator that yields scoped sessions.
- Persistence utilities offer standardized logging and data sanitization for repositories and query services.
- Market source carousel and rate limit manager are exposed via services for use in system views.

**Section sources**
- [src/core/db/session.py:48-54](file://src/core/db/session.py#L48-L54)
- [src/core/db/persistence.py:61-124](file://src/core/db/persistence.py#L61-L124)
- [src/apps/system/services.py:1-5](file://src/apps/system/services.py#L1-L5)

### Startup and Shutdown Procedures
- Startup:
  - Database and Redis readiness checks.
  - Alembic migrations executed once during bootstrap.
  - Brokers and workers started.
  - Scheduler tasks launched.
- Shutdown:
  - Schedulers signaled and awaited.
  - Workers stopped gracefully.
  - Brokers shut down and internal buses reset.
  - Resource cleanup performed.

**Section sources**
- [src/core/bootstrap/lifespan.py:22-70](file://src/core/bootstrap/lifespan.py#L22-L70)

### Configuration Options for Different Environments
- Environment variables are loaded from a .env file with relaxed case sensitivity and ignored extras.
- Defaults are provided for development, including database and Redis URLs, API host/port, and CORS origins.
- Additional keys include API keys for external providers, scheduler intervals, worker counts, and feature flags.

**Section sources**
- [src/core/settings/base.py:72-77](file://src/core/settings/base.py#L72-L77)
- [src/core/settings/base.py:8-71](file://src/core/settings/base.py#L8-L71)

## Dependency Analysis
The bootstrap pipeline exhibits low coupling and clear separation of concerns:
- Entry point depends on the app factory.
- App factory depends on settings and router modules.
- Lifespan depends on database, Redis, brokers, workers, and scheduler.
- Alembic env depends on settings and shared metadata.

```mermaid
graph LR
Main["src/main.py"] --> App["src/core/bootstrap/app.py"]
App --> Settings["src/core/settings/base.py"]
App --> Lifespan["src/core/bootstrap/lifespan.py"]
Lifespan --> DB["src/core/db/session.py"]
Lifespan --> Broker["src/runtime/orchestration/broker.py"]
Lifespan --> Streams["src/runtime/streams/runner.py"]
Lifespan --> Scheduler["src/runtime/scheduler/__init__.py"]
App --> AlembicEnv["src/migrations/env.py"]
AlembicEnv --> AlembicIni["alembic.ini"]
```

**Diagram sources**
- [src/main.py:5-9](file://src/main.py#L5-L9)
- [src/core/bootstrap/app.py:32-34](file://src/core/bootstrap/app.py#L32-L34)
- [src/core/bootstrap/lifespan.py:8-17](file://src/core/bootstrap/lifespan.py#L8-L17)
- [src/migrations/env.py:8-18](file://src/migrations/env.py#L8-L18)

**Section sources**
- [src/main.py:5-9](file://src/main.py#L5-L9)
- [src/core/bootstrap/app.py:32-34](file://src/core/bootstrap/app.py#L32-L34)
- [src/core/bootstrap/lifespan.py:8-17](file://src/core/bootstrap/lifespan.py#L8-L17)
- [src/migrations/env.py:8-18](file://src/migrations/env.py#L8-L18)

## Performance Considerations
- Deferred migrations: Executed synchronously in a thread to keep the HTTP path unblocked, minimizing cold-start latency impact.
- Worker spawning: Process-based workers are started once during bootstrap; this avoids per-request overhead but increases initial resource usage.
- Retry loops: Database and Redis readiness checks use bounded retries with delays to tolerate slow container startups.
- CORS configuration: Permissive settings simplify development but should be narrowed in production.
- Scheduler tasks: Background scheduling is coordinated centrally; ensure intervals are tuned to workload.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
- Database connectivity failures during startup:
  - Verify DATABASE_URL and network reachability.
  - Increase retries and delays if containers start out of order.
- Redis connectivity failures:
  - Confirm REDIS_URL and network configuration.
  - Adjust retries and delays similarly.
- Alembic migration errors:
  - Inspect logs for SQL errors.
  - Ensure migrations directory and script location are correct.
- CORS issues:
  - Validate that allowed origins include frontend URLs.
- Health endpoint:
  - Use the system health endpoint to confirm database connectivity.
- Worker processes:
  - Check process lists and logs for worker startup and termination.

**Section sources**
- [src/core/db/session.py:61-72](file://src/core/db/session.py#L61-L72)
- [src/apps/system/views.py:49-53](file://src/apps/system/views.py#L49-L53)

## Conclusion
The IRIS bootstrap process is designed for reliability and modularity. The app factory centralizes configuration and router registration, while the deferred lifespan ensures robust startup sequencing. Alembic migrations are integrated cleanly, and conditional feature loading supports flexible deployments. With proper environment configuration and monitoring, the system achieves predictable startup and graceful shutdown across development and production environments.