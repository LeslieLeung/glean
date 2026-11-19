# Glean browser extension

The extension connects to your self-hosted Glean instance with an API key. It can discover and add a feed from the current page or a feed URL you enter, and save the current page to Bookmarks.

## Build and install

Run from the repository root using Python 3.11 or later.

```sh
pnpm --dir frontend install --frozen-lockfile
python3 frontend/apps/extension/build.py
```

- **Chrome 123+** — Open `chrome://extensions`, enable Developer mode, and select **Load unpacked**. Choose `frontend/apps/extension/dist/chrome`.
- **Firefox 140+** — Open `about:debugging#/runtime/this-firefox`, select **Load Temporary Add-on**, and choose `frontend/apps/extension/dist/firefox/manifest.json`. Firefox removes temporary add-ons on restart. Persistent installation requires a Mozilla-signed package.

The build also creates `glean-chrome.zip` and `glean-firefox.zip` in `frontend/apps/extension/dist/`.

## Connect and use

1. Run a Glean server from a version that includes the browser extension API. In Glean, open **Settings → API Tokens**, create a token, and copy it.
2. Open the extension settings. Enter the Glean web address, using HTTPS for remote instances, and paste the token into **API Key**. Select **Connect and save** and allow access to that host.
3. Open the toolbar popup on a web page. Select **Bookmark this page** or **Add subscription**. You can replace the prefilled URL with a direct feed URL.

The key stays in local extension storage. The extension sends the URL and, when bookmarking, the page title to the configured Glean instance when you submit an action. Revoke the token from Glean to invalidate it.

## 中文

扩展支持 **Chrome 123+** 和 **Firefox 140+**。在仓库根目录执行上方命令安装前端依赖和构建扩展，需要 Python 3.11 或更新版本。

- **Chrome**：进入 `chrome://extensions`，开启开发者模式，点击「加载已解压的扩展程序」，选择 `frontend/apps/extension/dist/chrome`。
- **Firefox**：进入 `about:debugging#/runtime/this-firefox`，点击「临时载入附加组件」，选择 `frontend/apps/extension/dist/firefox/manifest.json`。临时扩展在 Firefox 重启后会移除，长期安装需要 Mozilla 签名。

运行包含扩展 API 的 Glean 版本。在 Glean 的「设置 → API 令牌」中创建并复制令牌，然后在扩展设置中填入 Glean 网页地址和 API Key，点击「连接并保存」并授予该站点的访问权限。建议远程实例使用 HTTPS。

浏览网页时点击工具栏中的 Glean 图标，即可收藏当前页面或尝试查找并订阅该页的 RSS。也可以直接填入订阅源地址。密钥保存在本地浏览器中，可在 Glean 随时撤销。
