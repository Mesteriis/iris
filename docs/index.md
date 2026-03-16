---
hide:
  - navigation
  - toc
---

<div class="iris-home">
  <section class="iris-home__hero">
    <div class="iris-home__copy">
      <div class="iris-home__eyebrow">Event-Driven Market Intelligence</div>
      <h1 class="iris-home__title">IRIS documentation that matches the live system.</h1>
      <p class="iris-home__subtitle">
        Architecture, governance, runtime boundaries, Home Assistant integration, AI planning, and generated HTTP artifacts are grouped around the current repository instead of the legacy wiki model.
      </p>
      <div class="iris-home__actions">
        <a class="md-button md-button--primary" href="getting-started/">Get started</a>
        <a class="md-button" href="market-data-api-keys/">Market data keys</a>
        <a class="md-button" href="architecture/">Read architecture</a>
        <a class="md-button" href="_generated/">View generated API docs</a>
      </div>
      <div class="iris-home__chips">
        <span class="iris-chip">FastAPI + Redis Streams</span>
        <span class="iris-chip">TaskIQ worker runtime</span>
        <span class="iris-chip">Home Assistant bridge</span>
        <span class="iris-chip">Governed HTTP contracts</span>
      </div>
    </div>
    <div class="iris-home__preview">
      <div class="iris-home__logo-wrap">
        <img class="iris-home__logo" src="assets/img/logo.png" alt="IRIS logo" />
      </div>
    </div>
  </section>

  <section class="iris-home__section">
    <div class="iris-home__section-head">
      <h2>Disclaimer</h2>
      <p>
        IRIS provides informational and operational tooling for self-directed investors. It is not a broker, investment adviser, execution guarantee, or promise of profitability. Users remain solely responsible for any investment, trading, automation, and risk-management decisions.
      </p>
    </div>
  </section>

  <section class="iris-home__section">
    <div class="iris-home__section-head">
      <h2>Platform snapshot</h2>
      <p>The docs site follows the same product language as the frontend: dark shell, glass panels, tide green highlights, and amber action accents.</p>
    </div>
    <div class="iris-stat-grid">
      <div class="iris-stat">
        <div class="iris-stat__label">Backend domains</div>
        <div class="iris-stat__value">13</div>
      </div>
      <div class="iris-stat">
        <div class="iris-stat__label">Accepted ADRs</div>
        <div class="iris-stat__value">21</div>
      </div>
      <div class="iris-stat">
        <div class="iris-stat__label">Primary doc classes</div>
        <div class="iris-stat__value">6</div>
      </div>
      <div class="iris-stat">
        <div class="iris-stat__label">API governance snapshots</div>
        <div class="iris-stat__value">2</div>
      </div>
    </div>
  </section>

  <section class="iris-home__section">
    <div class="iris-home__section-head">
      <h2>Start from the right place</h2>
      <p>Use the navigation below according to intent, not by folder guesswork.</p>
    </div>
    <div class="iris-card-grid">
      <article class="iris-card">
        <div class="iris-card__eyebrow">Architecture</div>
        <h3>Accepted system shape</h3>
        <p>Runtime model, persistence boundaries, control plane, service-layer policy, and accepted ADRs.</p>
        <a href="architecture/">Open architecture docs</a>
      </article>
      <article class="iris-card">
        <div class="iris-card__eyebrow">Delivery</div>
        <h3>Execution plans and audits</h3>
        <p>Refactor rollout state, implementation audits, localization planning, and AI platform working docs.</p>
        <a href="delivery/">Open delivery docs</a>
      </article>
      <article class="iris-card">
        <div class="iris-card__eyebrow">Generated</div>
        <h3>Code-derived API truth</h3>
        <p>Availability matrix and HTTP capability catalog exported from the live codebase and used in CI governance.</p>
        <a href="_generated/">Open generated artifacts</a>
      </article>
      <article class="iris-card">
        <div class="iris-card__eyebrow">Home Assistant</div>
        <h3>Bridge and protocol surface</h3>
        <p>Server-driven integration docs, backend plans, HACS integration planning, and protocol contracts.</p>
        <a href="home-assistant/">Open Home Assistant docs</a>
      </article>
      <article class="iris-card">
        <div class="iris-card__eyebrow">Product</div>
        <h3>Framing and review checklists</h3>
        <p>Higher-level product value framing and endpoint review guidance that supports the architecture work.</p>
        <a href="product/">Open product docs</a>
      </article>
      <article class="iris-card">
        <div class="iris-card__eyebrow">OSS</div>
        <h3>Repository model</h3>
        <p>Contribution, security, licensing, and repository expectations for an external contributor path.</p>
        <a href="open-source/">Open OSS guide</a>
      </article>
    </div>
  </section>

  <section class="iris-home__section">
    <div class="iris-home__section-head">
      <h2>Current sources of truth</h2>
      <p>Not all markdown in the repository has the same authority.</p>
    </div>
    <ul class="iris-home__list">
      <li><strong>Generated artifacts first:</strong> use <a href="_generated/">code-derived HTTP snapshots</a> when validating what the platform actually exposes.</li>
      <li><strong>Accepted architecture second:</strong> use <a href="architecture/adr/">ADRs</a> and architecture policy docs for target boundaries and operating rules.</li>
      <li><strong>Integration specs third:</strong> use <a href="home-assistant/">integration-specific protocol docs</a> when the question is scoped to Home Assistant.</li>
      <li><strong>Execution docs fourth:</strong> use <a href="delivery/">delivery and audit docs</a> for rollout state, refactor campaigns, and principal implementation plans.</li>
    </ul>
  </section>
</div>
