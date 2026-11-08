import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SignIn from '@/components/settings/SignIn.vue'

function mountSignIn(props: { error?: string | null; busy?: boolean } = {}) {
  return mount(SignIn, { props: { error: null, busy: false, ...props } })
}

describe('SignIn', () => {
  it('renders the prototype sign-in screen with no remember control', () => {
    const wrapper = mountSignIn()

    expect(wrapper.find('[data-od-id="sign-in-screen"]').exists()).toBe(true)
    const input = wrapper.get('[data-od-id="owner-token-input"]')
    expect(input.attributes('type')).toBe('password')
    expect(input.attributes('autocomplete')).toBe('off')
    expect(wrapper.get('[data-od-id="sign-in-button"]').text()).toBe('Sign in')
    expect(wrapper.text()).toContain('Owner access token')
    expect(wrapper.text()).toContain('The token stays for this tab only.')
    expect(wrapper.text().toLowerCase()).not.toContain('remember')
  })

  it('shows the rejection and marks the field invalid', () => {
    const wrapper = mountSignIn({ error: 'That token was rejected.' })

    expect(wrapper.get('.err-msg').text()).toContain('That token was rejected.')
    expect(wrapper.get('[data-od-id="owner-token-input"]').attributes('aria-invalid')).toBe(
      'true',
    )
  })

  it('puts the caret back in the field when a submit is refused', async () => {
    const wrapper = mount(SignIn, {
      attachTo: document.body,
      props: { error: null, busy: false },
    })

    await wrapper.setProps({ error: 'That token was rejected.' })
    await flushPromises()

    expect(document.activeElement).toBe(
      wrapper.get('[data-od-id="owner-token-input"]').element,
    )
    wrapper.unmount()
  })

  it('submits the typed token and disables the button while busy', async () => {
    const wrapper = mountSignIn()

    await wrapper.get('[data-od-id="owner-token-input"]').setValue('sekret')
    await wrapper.get('#signin-form').trigger('submit')

    expect(wrapper.emitted('submit')).toEqual([['sekret']])

    await wrapper.setProps({ busy: true })
    expect(wrapper.get('[data-od-id="sign-in-button"]').attributes('disabled')).toBeDefined()
  })
})
