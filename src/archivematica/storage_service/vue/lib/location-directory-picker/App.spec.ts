import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import App from './App.vue'

describe('LocationDirectoryPickerApp', () => {
  it('renders provided message', () => {
    const wrapper = mount(App, {
      props: {
        message: 'Test message',
      },
    })

    expect(wrapper.text()).toContain('Test message')
  })
})
