<template>
  <article class="ui-card">
    <header class="ui-card__head">
      <slot name="header">
        <h3 v-if="title">{{ title }}</h3>
        <p v-if="subtitle">{{ subtitle }}</p>
      </slot>
    </header>

    <div class="ui-card__body">
      <slot />
    </div>

    <footer v-if="$slots.footer || footer" class="ui-card__foot">
      <slot name="footer">{{ footer }}</slot>
    </footer>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title?: string;
  subtitle?: string;
  footer?: string;
}>();
</script>
