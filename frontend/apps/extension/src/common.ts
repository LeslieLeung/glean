interface InstanceConfig {
  baseUrl: string
  apiKey: string
}

interface HostPermission {
  origins: string[]
}

interface ExtensionAPI {
  i18n: { getMessage(key: string): string; getUILanguage(): string }
  permissions: {
    contains(permission: HostPermission): Promise<boolean>
    request(permission: HostPermission): Promise<boolean>
    remove(permission: HostPermission): Promise<boolean>
    getAll(): Promise<{ origins?: string[] }>
  }
  runtime: { openOptionsPage(): Promise<void> }
  storage: {
    local: {
      get(key: 'config'): Promise<{ config?: InstanceConfig }>
      set(items: { config: InstanceConfig }): Promise<void>
      remove(key: 'config'): Promise<void>
    }
  }
  tabs: {
    query(filter: {
      active: boolean
      currentWindow: boolean
    }): Promise<{ title?: string; url?: string }[]>
  }
}

declare const browser: ExtensionAPI | undefined
declare const chrome: ExtensionAPI

export const extension = typeof browser === 'undefined' ? chrome : browser
export const message = (key: string) => extension.i18n.getMessage(key)

export function localize() {
  document.documentElement.lang = extension.i18n.getUILanguage()
  for (const node of document.querySelectorAll<HTMLElement>('[data-message]')) {
    if (node.dataset.message) node.textContent = message(node.dataset.message)
  }
}

export function webUrl(value: string | undefined) {
  if (!value) return null
  try {
    const url = new URL(value)
    if (['https:', 'http:'].includes(url.protocol) && !url.username && !url.password) {
      return url
    }
  } catch {
    // Blank and incomplete URLs are invalid while the user is still typing.
  }
  return null
}

export function instanceSettings(value: string, key: string): InstanceConfig {
  const url = webUrl(value)
  if (!url || url.search || url.hash) throw new Error(message('invalidInstance'))
  if (!/^glean_[A-Za-z0-9_-]+$/.test(key)) throw new Error(message('invalidKey'))
  return { baseUrl: url.origin + url.pathname.replace(/\/+$/, ''), apiKey: key }
}

export function hostPermission(baseUrl: string): HostPermission {
  const { protocol, hostname } = new URL(baseUrl)
  return { origins: [`${protocol}//${hostname}/*`] }
}

export type Action = 'subscriptions' | 'bookmarks'
export type Page = { url: string; title?: string }

export async function request(config: InstanceConfig, path: 'connection' | Action, data?: Page) {
  if (!(await extension.permissions.contains(hostPermission(config.baseUrl)))) {
    throw new Error(message('permissionNeeded'))
  }

  let response
  try {
    response = await fetch(`${config.baseUrl}/api/extension/${path}`, {
      method: data ? 'POST' : 'GET',
      headers: {
        Authorization: `Bearer ${config.apiKey}`,
        ...(data && { 'Content-Type': 'application/json' }),
      },
      body: data && JSON.stringify(data),
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
      signal: AbortSignal.timeout(40000),
    })
  } catch {
    throw new Error(message('connectionFailed'))
  }

  if (response.status === (data ? 201 : 204)) return
  if (response.status === 401) throw new Error(message('invalidKey'))
  if (path === 'subscriptions') {
    if (response.status === 409) throw new Error(message('alreadySubscribed'))
    if (response.status === 400) throw new Error(message('feedNotFound'))
  }
  if (response.status === 422) throw new Error(message('invalidPage'))
  if (response.status === 404 || response.ok) throw new Error(message('unsupportedInstance'))
  throw new Error(message('requestFailed'))
}
