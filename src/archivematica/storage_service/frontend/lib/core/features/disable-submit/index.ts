const FORM_SELECTOR = 'form[data-disable-submit]'
const SUBMIT_CONTROL_SELECTOR = 'button[type="submit"], input[type="submit"]'

const disableSubmitControls = (form: HTMLFormElement): void => {
  form.querySelectorAll<HTMLButtonElement | HTMLInputElement>(SUBMIT_CONTROL_SELECTOR).forEach((control) => {
    control.disabled = true
  })
}

const initializedForms = new WeakSet<HTMLFormElement>()

const initializeForm = (form: HTMLFormElement): void => {
  if (initializedForms.has(form)) {
    return
  }

  initializedForms.add(form)
  form.addEventListener('submit', () => {
    disableSubmitControls(form)
  })
}

export const init = (): void => {
  document.querySelectorAll<HTMLFormElement>(FORM_SELECTOR).forEach((form) => {
    initializeForm(form)
  })
}
