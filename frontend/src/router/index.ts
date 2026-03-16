import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior() {
    return { top: 0 };
  },
  routes: [
    {
      path: "/",
      name: "assets",
      component: () => import("../pages/Assets.vue"),
      meta: {
        title: "Assets",
        description: "All tracked quotes and instruments currently available in IRIS.",
        hideShellHeader: true,
      },
    },
    {
      path: "/market",
      name: "market",
      component: () => import("../pages/Market.vue"),
      meta: {
        title: "Market",
        description: "Signal, radar, and cross-market intelligence surfaces.",
        hideShellHeader: true,
      },
    },
    {
      path: "/portfolio",
      name: "portfolio",
      component: () => import("../pages/Portfolio.vue"),
      meta: {
        title: "Portfolio",
        description: "Positions, actions, risk, and current portfolio state.",
        hideShellHeader: true,
      },
    },
    {
      path: "/research",
      name: "research",
      component: () => import("../pages/Research.vue"),
      meta: {
        title: "Research",
        description: "Strategies, backtests, pattern health, and discovery outputs.",
        hideShellHeader: true,
      },
    },
    {
      path: "/runtime",
      name: "runtime",
      component: () => import("../pages/Runtime.vue"),
      meta: {
        title: "Runtime",
        description: "System health, background jobs, provider cooldowns, and live stream surfaces.",
        hideShellHeader: true,
      },
    },
    {
      path: "/assets/:symbol",
      name: "asset-detail",
      component: () => import("../pages/CoinHistory.vue"),
      props: true,
      meta: {
        title: "Asset analysis desk",
        description: "Detailed asset view with history, indicators, decisions, and context.",
      },
    },
    {
      path: "/control-plane",
      name: "control-plane",
      component: () => import("../pages/ControlPlane.vue"),
      meta: {
        title: "Control plane",
        description: "Event registry, routes, drafts, and runtime observability for the event graph.",
        hideShellHeader: true,
      },
    },
  ],
});

export default router;
