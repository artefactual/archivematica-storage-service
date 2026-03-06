const ROOT_SELECTOR = 'form[data-space-protocol-form-url]'
const ACCESS_PROTOCOL_SELECTOR = 'select#id_space-access_protocol'
const PROTOCOL_FORM_SELECTOR = '#protocol_form'

type SpaceProtocolRoot = HTMLFormElement & {
  dataset: DOMStringMap & {
    spaceProtocolFormUrl?: string
  }
}

const buildRequestUrl = (endpoint: string, protocol: string): string => {
  const url = new URL(endpoint, window.location.origin)
  url.searchParams.set('protocol', protocol)
  return url.toString()
}

const updateProtocolFields = async (
  root: SpaceProtocolRoot,
  protocolField: HTMLSelectElement,
  protocolContainer: HTMLElement,
): Promise<void> => {
  const endpoint = root.dataset.spaceProtocolFormUrl
  if (!endpoint) {
    return
  }

  try {
    const response = await fetch(buildRequestUrl(endpoint, protocolField.value), {
      credentials: 'same-origin',
    })
    if (!response.ok) {
      throw new Error(`Failed to fetch protocol fields with status ${response.status}`)
    }
    protocolContainer.innerHTML = await response.text()
  } catch (error) {
    console.error('Failed to load protocol fields', error)
  }
}

const bindRoot = (root: SpaceProtocolRoot): void => {
  const protocolField = root.querySelector<HTMLSelectElement>(ACCESS_PROTOCOL_SELECTOR)
  const protocolContainer = root.querySelector<HTMLElement>(PROTOCOL_FORM_SELECTOR)
  if (!protocolField || !protocolContainer) {
    return
  }

  protocolField.addEventListener('change', () => {
    void updateProtocolFields(root, protocolField, protocolContainer)
  })
}

export const init = (): void => {
  const roots = document.querySelectorAll<SpaceProtocolRoot>(ROOT_SELECTOR)
  roots.forEach((root) => {
    bindRoot(root)
  })
}
