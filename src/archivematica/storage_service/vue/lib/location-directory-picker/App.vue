<script setup lang="ts">
const props = defineProps<{
  message: string
}>()
</script>

<template>
  <section aria-label="Location directory picker">
    <p>{{ props.message }}</p>
  </section>
</template>
