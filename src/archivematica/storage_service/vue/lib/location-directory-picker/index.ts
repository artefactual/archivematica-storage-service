import { createApp } from 'vue'
import App from './App.vue'
import { i18n, initI18n } from '@/shared/i18n'

async function bootstrap() {
  const mountEl = document.getElementById('location-directory-picker')
  if (!mountEl) {
    throw new Error('Mount element not found.')
  }

  await initI18n()

  const spaceUuid = mountEl.getAttribute('data-space-uuid') || ''
  const rootPath = mountEl.getAttribute('data-root-path') || ''
  const selectedPath = mountEl.getAttribute('data-selected-path') || ''

  const app = createApp(App, {
    spaceUuid,
    rootPath,
    selectedPath,
  })

  app.use(i18n)
  app.mount(mountEl)
}

bootstrap().catch((err) => {
  console.error('Failed to bootstrap app:', err)
})
