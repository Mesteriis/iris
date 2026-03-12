import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior() {
    return { top: 0 };
  },
  routes: [
    {
      path: "/",
      name: "coins",
      component: () => import("../pages/Coins.vue"),
      meta: {
        title: "Long-horizon market board",
      },
    },
    {
      path: "/coins/:symbol",
      name: "coin-history",
      component: () => import("../pages/CoinHistory.vue"),
      props: true,
      meta: {
        title: "Coin analysis desk",
      },
    },
    {
      path: "/control-plane",
      name: "control-plane",
      component: () => import("../pages/ControlPlane.vue"),
      meta: {
        title: "Event control plane",
      },
    },
  ],
});

export default router;
