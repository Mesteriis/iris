<template>
  <div v-if="open" :class="backdropClass" @click.self="$emit('backdrop')">
    <div :class="modalClass">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  open: boolean;
  backdropClass: string;
  modalClass: string;
}>();

defineEmits<{
  backdrop: [];
}>();
</script>
