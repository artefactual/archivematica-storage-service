import { createHttpClient, toHttpErrorInfo } from '../../../shared/http/client'
import { translate } from '../../../shared/i18n/plain'

const REQUEST_DELETE_SELECTOR = 'a.request-delete'
const REQUEST_DELETE_URL_DATA_KEY = 'packageRequestDeleteUrl'
const REQUEST_DELETE_CSRF_TOKEN_DATA_KEY = 'packageRequestDeleteCsrfToken'
const PAGE_HEADING_SELECTOR = 'h1'
const ALERT_ID = 'package-delete-alert'
const FALLBACK_SUCCESS_MESSAGE_KEY = 'packageRequestDelete.success'
const FALLBACK_ERROR_MESSAGE_KEY = 'packageRequestDelete.failure'

type RequestDeleteTrigger = HTMLElement & {
  dataset: DOMStringMap & {
    packageRequestDeleteUrl?: string
    packageRequestDeleteCsrfToken?: string
  }
}

type DeleteRequestResponse = {
  message?: string
  error_message?: string
}

const httpClient = createHttpClient()

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

const parseResponseMessage = (payload: unknown): string | null => {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const {
    message,
    error_message: errorMessage,
  } = payload as DeleteRequestResponse
  if (typeof message === 'string' && message.length > 0) {
    return message
  }
  if (typeof errorMessage === 'string' && errorMessage.length > 0) {
    return errorMessage
  }
  return null
}

const submitDeleteRequest = async (trigger: RequestDeleteTrigger): Promise<void> => {
  const endpoint = trigger.dataset[REQUEST_DELETE_URL_DATA_KEY]
  const csrfToken = trigger.dataset[REQUEST_DELETE_CSRF_TOKEN_DATA_KEY]
  if (!endpoint || !csrfToken) {
    return
  }

  try {
    const payload = await httpClient.requestJson<DeleteRequestResponse | null>(endpoint, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken,
      },
    })
    const responseMessage = parseResponseMessage(payload)
    renderAlert(responseMessage ?? translate(FALLBACK_SUCCESS_MESSAGE_KEY), 'success')
  } catch (error) {
    const errorMessage = parseResponseMessage(toHttpErrorInfo(error)?.bodyJson)
    console.error('Failed to submit package deletion request', error)
    renderAlert(errorMessage ?? translate(FALLBACK_ERROR_MESSAGE_KEY), 'warning')
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
