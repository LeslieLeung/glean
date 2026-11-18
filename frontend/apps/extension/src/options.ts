import {
  extension,
  hostPermission,
  instanceSettings,
  localize,
  message,
  request,
} from './common.js'

const form = document.querySelector<HTMLElement>('#settings')!
const instance = document.querySelector<HTMLInputElement>('#instance')!
const key = document.querySelector<HTMLInputElement>('#key')!
const save = document.querySelector<HTMLButtonElement>('#save')!
const disconnect = document.querySelector<HTMLButtonElement>('#disconnect')!
const status = document.querySelector<HTMLElement>('#status')!

localize()

let { config } = await extension.storage.local.get('config')
if (config) {
  instance.value = config.baseUrl
  key.value = config.apiKey
  disconnect.hidden = false
}
save.disabled = false

instance.addEventListener('input', () => {
  if (key.value === config?.apiKey) key.value = ''
})

function setBusy(busy: boolean) {
  instance.disabled = key.disabled = save.disabled = disconnect.disabled = busy
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  setBusy(true)
  status.textContent = message('connecting')
  let requested: ReturnType<typeof hostPermission> | undefined
  try {
    const next = instanceSettings(instance.value.trim(), key.value.trim())
    const permission = hostPermission(next.baseUrl)
    // Request directly from the submit gesture before the first await (required by Firefox).
    if (!(await extension.permissions.request(permission))) {
      throw new Error(message('permissionNeeded'))
    }

    requested = permission
    await request(next, 'connection')
    await extension.storage.local.set({ config: next })
    const previous = config && hostPermission(config.baseUrl)
    config = next
    instance.value = config.baseUrl
    key.value = config.apiKey
    disconnect.hidden = false
    if (previous && previous.origins[0] !== permission.origins[0]) {
      await extension.permissions.remove(previous)
    }
    status.textContent = message('connected')
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : message('requestFailed')
    const savedOrigin = config && hostPermission(config.baseUrl).origins[0]
    if (requested && requested.origins[0] !== savedOrigin) {
      await extension.permissions.remove(requested)
    }
  } finally {
    setBusy(false)
  }
})

disconnect.addEventListener('click', async () => {
  setBusy(true)
  try {
    await extension.storage.local.remove('config')
    config = undefined
    instance.value = key.value = ''
    disconnect.hidden = true
    const { origins = [] } = await extension.permissions.getAll()
    if (origins.length) await extension.permissions.remove({ origins })
    status.textContent = message('disconnected')
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : message('requestFailed')
  } finally {
    setBusy(false)
  }
})
