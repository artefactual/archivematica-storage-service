<script setup lang="ts">
import LocationDirectoryPickerApp from '@/location-directory-picker/App.vue'
</script>

<template>
  <div class="page-container">
    <h1>Storage Service Vue Components</h1>
    <div class="well">
      <h2>Location Directory Picker</h2>
      <div id="location-directory-picker">
        <LocationDirectoryPickerApp
          message="Storage Service location directory picker workspace initialized."
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  max-width: 1200px;
  margin: 0 auto;
  background: #fff;
  padding: 20px;
  border-radius: 4px;
  border: 1px solid #ddd;
}

h1 {
  margin-top: 0;
  font-size: 26px;
}
</style>
