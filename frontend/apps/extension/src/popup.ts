import {
  type Action,
  type Page,
  extension,
  hostPermission,
  localize,
  message,
  request,
  webUrl,
} from './common.js'

localize()
const status = document.querySelector<HTMLElement>('#status')!
document.querySelector<HTMLButtonElement>('#settings')!.addEventListener('click', () => {
  void extension.runtime.openOptionsPage()
})

async function init() {
  const { config } = await extension.storage.local.get('config')
  if (!config) {
    status.textContent = message('setupNeeded')
    return
  }
  if (!(await extension.permissions.contains(hostPermission(config.baseUrl)))) {
    status.textContent = message('permissionNeeded')
    return
  }

  const [tab] = await extension.tabs.query({ active: true, currentWindow: true })
  const pageUrl = webUrl(tab?.url)
  const feedUrl = document.querySelector<HTMLInputElement>('#feed-url')!
  const bookmark = document.querySelector<HTMLButtonElement>('#bookmark')!
  const subscribe = document.querySelector<HTMLButtonElement>('#subscribe')!
  let bookmarked = false
  let subscribedUrl: string | undefined

  if (pageUrl) {
    document.querySelector<HTMLElement>('#page')!.hidden = false
    document.querySelector<HTMLElement>('#page-title')!.textContent = tab?.title || pageUrl.href
    document.querySelector<HTMLElement>('#page-host')!.textContent = pageUrl.host
    feedUrl.value = pageUrl.href
  } else {
    status.textContent = message('noPage')
  }
  document.querySelector<HTMLElement>('#capture')!.hidden = false

  function updateButtons() {
    subscribe.disabled = !feedUrl.value.trim() || subscribedUrl === feedUrl.value.trim()
    bookmark.disabled = bookmarked
  }
  updateButtons()
  feedUrl.addEventListener('input', updateButtons)

  const send = async (
    path: Action,
    data: Page,
    pending: string,
    success: string,
    onSuccess: () => void
  ) => {
    feedUrl.disabled = subscribe.disabled = bookmark.disabled = true
    status.textContent = message(pending)
    try {
      await request(config, path, data)
      onSuccess()
      status.textContent = message(success)
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : message('requestFailed')
    } finally {
      feedUrl.disabled = false
      updateButtons()
    }
  }

  document.querySelector<HTMLElement>('#subscription')!.addEventListener('submit', (event) => {
    event.preventDefault()
    const value = feedUrl.value.trim()
    const url = webUrl(value)
    if (!url || url.href.length > 2048) {
      status.textContent = message('invalidPage')
      return
    }
    void send('subscriptions', { url: url.href }, 'discovering', 'subscribed', () => {
      subscribedUrl = value
    })
  })

  bookmark.addEventListener('click', () => {
    if (!pageUrl || pageUrl.href.length > 2048) {
      status.textContent = message('invalidPage')
      return
    }
    const title = Array.from(tab?.title?.trim() ?? '')
      .slice(0, 500)
      .join('')
    void send('bookmarks', { url: pageUrl.href, title }, 'saving', 'bookmarked', () => {
      bookmarked = true
    })
  })
}

init().catch(() => {
  status.textContent = message('requestFailed')
})
