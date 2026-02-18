import { createApp, defineComponent, h, ref } from 'vue'
import App from './App.vue'
import { i18n, initI18n } from '@/shared/i18n'
import { toAbsolutePath, toRelativePath } from './pathUtils'
import 'font-awesome/css/font-awesome.min.css'

async function bootstrap() {
  const mountEl = document.getElementById('location-directory-picker')
  if (!mountEl) {
    throw new Error('Mount element not found.')
  }

  await initI18n()

  const spaceUuid = mountEl.getAttribute('data-space-uuid') || ''
  const rootPath = mountEl.getAttribute('data-root-path') || ''
  const resolveSelectedPath = () => {
    const relativePath = mountEl.getAttribute('data-selected-relative-path')
    if (relativePath !== null) {
      return toAbsolutePath(rootPath, relativePath)
    }
    return mountEl.getAttribute('data-selected-path') || ''
  }
  const selectedPath = ref(resolveSelectedPath())
  const syncSelectedPath = () => {
    selectedPath.value = resolveSelectedPath()
  }

  const handleSelectedPath = (path: string) => {
    selectedPath.value = path
    mountEl.setAttribute('data-selected-relative-path', toRelativePath(rootPath, path))
    mountEl.setAttribute('data-selected-path', path)
    mountEl.dispatchEvent(new CustomEvent('location-directory-picker:selected-path', {
      detail: {
        path,
        relativePath: toRelativePath(rootPath, path),
      },
    }))
  }

  const Root = defineComponent({
    name: 'LocationDirectoryPickerRoot',
    setup() {
      return () => h(App, {
        spaceUuid,
        rootPath,
        selectedPath: selectedPath.value,
        onSelect: handleSelectedPath,
      })
    },
  })

  const app = createApp(Root)

  app.use(i18n)
  app.mount(mountEl)

  const attributeObserver = new MutationObserver((mutations) => {
    if (mutations.some(mutation => mutation.attributeName === 'data-selected-relative-path'
      || mutation.attributeName === 'data-selected-path')) {
      syncSelectedPath()
    }
  })

  attributeObserver.observe(mountEl, {
    attributes: true,
    attributeFilter: ['data-selected-relative-path', 'data-selected-path'],
  })
}

bootstrap().catch((err) => {
  console.error('Failed to bootstrap app:', err)
})
