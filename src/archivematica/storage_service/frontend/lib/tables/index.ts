import { createApp } from 'vue'
import App from './App.vue'
import { i18n, initI18n } from '@/shared/i18n'

type TableRoot = HTMLElement & {
  dataset: DOMStringMap & {
    tableScriptId?: string
  }
}

const parsePayload = (scriptId: string): unknown => {
  const script = document.getElementById(scriptId)
  if (!script?.textContent) {
    throw new Error(`Table payload script not found: ${scriptId}`)
  }
  return JSON.parse(script.textContent)
}

const mountTables = (): void => {
  const roots = document.querySelectorAll<HTMLElement>('[data-table-root]')
  roots.forEach((rootEl) => {
    const root = rootEl as TableRoot
    root.closest('.row')?.classList.add('tables-content-row')
    const scriptId = root.dataset.tableScriptId
    if (!scriptId) {
      console.error('Missing data-table-script-id on table root', root)
      return
    }

    try {
      const payload = parsePayload(scriptId)
      createApp(App, { payload }).use(i18n).mount(root)
    } catch (error) {
      console.error('Failed to mount table', error)
    }
  })
}

async function bootstrap(): Promise<void> {
  await initI18n()
  mountTables()
}

bootstrap().catch((error) => {
  console.error('Failed to bootstrap tables', error)
})
