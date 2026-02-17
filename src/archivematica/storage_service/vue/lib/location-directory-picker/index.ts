import { createApp } from 'vue'
import App from './App.vue'

const bootstrap = () => {
  const mountEl = document.getElementById('location-directory-picker')
  if (!mountEl) {
    throw new Error('Mount element not found.')
  }

  const message
    = mountEl.getAttribute('data-message')
      || 'Storage Service location directory picker workspace initialized.'

  createApp(App, { message }).mount(mountEl)
}

bootstrap()
