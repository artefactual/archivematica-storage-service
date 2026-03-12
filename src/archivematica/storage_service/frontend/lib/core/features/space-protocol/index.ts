import DOMPurify from 'dompurify'

const ROOT_SELECTOR = 'form[data-space-protocol-form-url]'
const ACCESS_PROTOCOL_SELECTOR = 'select#id_space-access_protocol'
const PROTOCOL_FORM_SELECTOR = '#protocol_form'
const TRUSTED_TYPES_POLICY_NAME = 'am-storage-service'

type TrustedHtmlPolicy = {
  createHTML: (input: string) => unknown
}

type TrustedTypesFactory = {
  createPolicy: (
    name: string,
    policy: {
      createHTML: (input: string) => string
    },
  ) => TrustedHtmlPolicy
}

type SpaceProtocolRoot = HTMLFormElement & {
  dataset: DOMStringMap & {
    spaceProtocolFormUrl?: string
  }
}

let trustedHtmlPolicy: TrustedHtmlPolicy | null = null
let trustedHtmlPolicyInitialized = false

const sanitizeMarkup = (markup: string): string =>
  DOMPurify.sanitize(markup, { RETURN_TRUSTED_TYPE: false })

const getTrustedTypesFactory = (): TrustedTypesFactory | null =>
  ((window as Window & { trustedTypes?: TrustedTypesFactory }).trustedTypes ?? null)

const getTrustedHtmlPolicy = (): TrustedHtmlPolicy | null => {
  if (trustedHtmlPolicyInitialized) {
    return trustedHtmlPolicy
  }

  trustedHtmlPolicyInitialized = true

  const trustedTypesFactory = getTrustedTypesFactory()
  if (!trustedTypesFactory?.createPolicy) {
    return null
  }

  try {
    trustedHtmlPolicy = trustedTypesFactory.createPolicy(TRUSTED_TYPES_POLICY_NAME, {
      createHTML: (markup: string) => sanitizeMarkup(markup),
    })
  } catch (error) {
    console.error('Failed to create Trusted Types policy for protocol fields', error)
    trustedHtmlPolicy = null
  }

  return trustedHtmlPolicy
}

const replaceProtocolMarkup = (protocolContainer: HTMLElement, markup: string): void => {
  const policy = getTrustedHtmlPolicy()
  const safeMarkup = policy ? policy.createHTML(markup) : sanitizeMarkup(markup)
  ;(protocolContainer as { innerHTML: unknown }).innerHTML = safeMarkup
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
    replaceProtocolMarkup(protocolContainer, await response.text())
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
