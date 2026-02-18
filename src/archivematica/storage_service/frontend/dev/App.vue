<script setup lang="ts">
import { ref } from 'vue'
import LocationDirectoryPickerApp from '@/location-directory-picker/App.vue'

const spaceUuid = ref('')
const rootPath = ref('')
const selectedPath = ref('')
</script>

<template>
  <div class="page-container">
    <h1>Storage Service Frontend Components</h1>
    <div class="well">
      <h2>Location Directory Picker</h2>

      <div class="form-group">
        <label for="space-uuid">Space UUID</label>
        <input
          id="space-uuid"
          v-model="spaceUuid"
          type="text"
          class="form-control"
          placeholder="e.g. 7d20c992-bc92-4f92-a794-7161ff2cc08b"
        >
      </div>

      <div class="form-group">
        <label for="root-path">Root path</label>
        <input
          id="root-path"
          v-model="rootPath"
          type="text"
          class="form-control"
          placeholder="e.g. /var/archivematica/sharedDirectory"
        >
      </div>

      <div id="location-directory-picker">
        <LocationDirectoryPickerApp
          :space-uuid="spaceUuid"
          :root-path="rootPath"
          :selected-path="selectedPath"
          @update:selected-path="selectedPath = $event"
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
