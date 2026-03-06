import { translate } from '@/shared/i18n/plain'

const CALLBACK_FORM_SELECTOR = '.callback > form'
const HEADER_INPUT_SELECTOR = 'input[name^="header_"]'
const DELETE_LINK_CLASS = 'delete_header'
const ADD_LINK_CLASS = 'add_header'

const getHeaderInputs = (row: ParentNode): HTMLInputElement[] => {
  return Array.from(row.querySelectorAll<HTMLInputElement>(HEADER_INPUT_SELECTOR))
}

const isHeaderRow = (row: Element): row is HTMLParagraphElement => {
  if (!(row instanceof HTMLParagraphElement)) {
    return false
  }
  return getHeaderInputs(row).length >= 2
}

const getHeaderRows = (form: HTMLFormElement): HTMLParagraphElement[] => {
  return Array.from(form.querySelectorAll('p')).filter(isHeaderRow)
}

const renumberName = (value: string, increment: number): string => {
  return value.replace(/\d+/, digits => String(Number.parseInt(digits, 10) + increment))
}

const updateHeaderInputs = (
  rows: readonly HTMLParagraphElement[],
  increment = 0,
  clean = true,
): void => {
  if (increment === 0 && !clean) {
    return
  }

  rows.forEach((row) => {
    getHeaderInputs(row).forEach((input) => {
      if (increment !== 0) {
        if (input.id) {
          input.id = renumberName(input.id, increment)
        }
        input.name = renumberName(input.name, increment)
      }
      if (clean) {
        input.value = ''
      }
    })
  })
}

const ensureDeleteLink = (row: HTMLParagraphElement): void => {
  if (row.querySelector(`a.${DELETE_LINK_CLASS}`)) {
    return
  }

  const inputs = getHeaderInputs(row)
  const valueField = inputs[1]
  if (!valueField) {
    return
  }

  const deleteLink = document.createElement('a')
  deleteLink.href = '#'
  deleteLink.className = DELETE_LINK_CLASS
  deleteLink.textContent = translate('callbackHeaders.delete')
  valueField.insertAdjacentElement('afterend', deleteLink)
}

const ensureAddLink = (form: HTMLFormElement): void => {
  if (form.querySelector(`a.${ADD_LINK_CLASS}`)) {
    return
  }

  const headerRows = getHeaderRows(form)
  const lastHeader = headerRows[headerRows.length - 1]
  if (!lastHeader) {
    return
  }

  const wrapper = document.createElement('p')
  const addLink = document.createElement('a')
  addLink.href = '#'
  addLink.className = ADD_LINK_CLASS
  addLink.textContent = translate('callbackHeaders.addHeader')
  wrapper.append(addLink)

  lastHeader.insertAdjacentElement('afterend', wrapper)
}

const initializeForm = (form: HTMLFormElement): void => {
  getHeaderRows(form).forEach((headerRow) => {
    ensureDeleteLink(headerRow)
  })
  ensureAddLink(form)
}

const removeHeader = (deleteLink: HTMLAnchorElement): void => {
  const form = deleteLink.closest('form')
  const row = deleteLink.closest('p')
  if (!(form instanceof HTMLFormElement) || !(row instanceof HTMLParagraphElement) || !isHeaderRow(row)) {
    return
  }

  const headerRows = getHeaderRows(form)
  if (headerRows.length > 1) {
    const rowIndex = headerRows.indexOf(row)
    if (rowIndex < 0) {
      return
    }

    const followingRows = headerRows.slice(rowIndex + 1)
    updateHeaderInputs(followingRows, -1, false)

    const label = row.querySelector('label')
    if (label && followingRows.length > 0) {
      followingRows[0].prepend(label)
    }

    row.remove()
    return
  }

  updateHeaderInputs([row])
}

const addHeader = (addLink: HTMLAnchorElement): void => {
  const form = addLink.closest('form')
  if (!(form instanceof HTMLFormElement)) {
    return
  }

  const headerRows = getHeaderRows(form)
  const lastHeader = headerRows[headerRows.length - 1]
  if (!lastHeader) {
    return
  }

  const clone = lastHeader.cloneNode(true)
  if (!(clone instanceof HTMLParagraphElement)) {
    return
  }

  clone.querySelector('label')?.remove()
  updateHeaderInputs([clone], 1, true)
  lastHeader.insertAdjacentElement('afterend', clone)
}

let listenersBound = false

const bindListeners = (): void => {
  if (listenersBound) {
    return
  }

  listenersBound = true
  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) {
      return
    }

    const deleteLink = target.closest<HTMLAnchorElement>(`.callback > form a.${DELETE_LINK_CLASS}`)
    if (deleteLink) {
      event.preventDefault()
      removeHeader(deleteLink)
      return
    }

    const addLink = target.closest<HTMLAnchorElement>(`.callback > form a.${ADD_LINK_CLASS}`)
    if (!addLink) {
      return
    }

    event.preventDefault()
    addHeader(addLink)
  })
}

export const init = (): void => {
  document.querySelectorAll<HTMLFormElement>(CALLBACK_FORM_SELECTOR).forEach((form) => {
    initializeForm(form)
  })
  bindListeners()
}
