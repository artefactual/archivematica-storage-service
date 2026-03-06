const REQUEST_DELETE_SELECTOR = 'a.request-delete'
const USER_DATA_SELECTOR = '#user-data-packages'
const PAGE_HEADING_SELECTOR = 'h1'
const ALERT_ID = 'package-delete-alert'
const AIP_DELETE_ENDPOINT_PATH = 'api/v2/file'
const FALLBACK_SUCCESS_MESSAGE = 'Package deletion request submitted.'
const FALLBACK_ERROR_MESSAGE = 'Package deletion request failed.'

type GettextGlobal = typeof globalThis & {
  gettext?: (message: string) => string
}

type RequestDeleteTrigger = HTMLElement & {
  dataset: DOMStringMap & {
    packageUuid?: string
    packagePipeline?: string
    packageType?: string
  }
}

type UserDataElement = HTMLElement & {
  dataset: DOMStringMap & {
    uri?: string
    userId?: string
    userEmail?: string
    userUsername?: string
    userApiKey?: string
  }
}

type UserData = {
  uri: string
  userId: string
  userEmail: string
  userUsername: string
  userApiKey: string
}

type DeleteRequestResponse = {
  message?: string
}

const translate = (message: string): string => {
  const gettext = (globalThis as GettextGlobal).gettext
  if (typeof gettext === 'function') {
    return gettext(message)
  }
  return message
}

const buildDeleteEndpointUrl = (uri: string, packageUuid: string): string => {
  const baseUri = new URL(uri, window.location.origin)
  return new URL(`${AIP_DELETE_ENDPOINT_PATH}/${packageUuid}/delete_aip/`, baseUri).toString()
}

const getUserData = (): UserData | null => {
  const userDataEl = document.querySelector<UserDataElement>(USER_DATA_SELECTOR)
  if (!userDataEl) {
    return null
  }

  const {
    uri,
    userId,
    userEmail,
    userUsername,
    userApiKey,
  } = userDataEl.dataset
  if (!uri || !userId || !userEmail || !userUsername || !userApiKey) {
    return null
  }

  return { uri, userId, userEmail, userUsername, userApiKey }
}

const renderAlert = (message: string, level: 'success' | 'warning'): void => {
  document.getElementById(ALERT_ID)?.remove()

  const heading = document.querySelector<HTMLElement>(PAGE_HEADING_SELECTOR)
  if (!heading) {
    return
  }

  const alert = document.createElement('div')
  alert.id = ALERT_ID
  alert.className = `alert ${level === 'success' ? 'alert-success' : 'alert-warning'}`
  alert.textContent = message

  heading.insertAdjacentElement('afterend', alert)
}

const parseResponseMessage = async (response: Response): Promise<string | null> => {
  try {
    const payload = await response.json() as DeleteRequestResponse
    if (typeof payload.message === 'string' && payload.message.length > 0) {
      return payload.message
    }
  } catch {
    // Ignore invalid JSON responses and fallback to default messages.
  }
  return null
}

const submitDeleteRequest = async (trigger: RequestDeleteTrigger): Promise<void> => {
  const {
    packageUuid,
    packagePipeline,
    packageType,
  } = trigger.dataset
  if (!packageUuid || !packagePipeline || !packageType) {
    return
  }

  const userData = getUserData()
  if (!userData) {
    return
  }

  const endpoint = buildDeleteEndpointUrl(userData.uri, packageUuid)
  const payload = {
    event_reason: `Storage Service user wants to delete ${packageType} ${packageUuid}.`,
    pipeline: packagePipeline,
    user_id: userData.userId,
    user_email: userData.userEmail,
  }

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Authorization': `ApiKey ${userData.userUsername}:${userData.userApiKey}`,
        'Content-Type': 'application/json; charset=utf-8',
      },
      body: JSON.stringify(payload),
    })

    const responseMessage = await parseResponseMessage(response)
    if (response.ok) {
      renderAlert(responseMessage ?? translate(FALLBACK_SUCCESS_MESSAGE), 'success')
      return
    }

    renderAlert(responseMessage ?? translate(FALLBACK_ERROR_MESSAGE), 'warning')
  } catch (error) {
    console.error('Failed to submit package deletion request', error)
    renderAlert(translate(FALLBACK_ERROR_MESSAGE), 'warning')
  }
}

let listenerBound = false

const bindListener = (): void => {
  if (listenerBound) {
    return
  }

  listenerBound = true
  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) {
      return
    }

    const requestDeleteTrigger = target.closest<RequestDeleteTrigger>(REQUEST_DELETE_SELECTOR)
    if (!requestDeleteTrigger) {
      return
    }

    event.preventDefault()
    void submitDeleteRequest(requestDeleteTrigger)
  })
}

export const init = (): void => {
  bindListener()
}
