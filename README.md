# 交作业

一个面向“互联网软件开发技术与实践”课程回收页的本地发布工具和 Chrome / Edge 扩展。工具会把当前 Git 仓库推送到远程，随后打开回收页；扩展从浏览器本地存储读取身份信息，并且只把远程仓库 URL 写入作业内容后自动提交。

## 功能

- 姓名和学号由用户在扩展设置页填写，仅保存在 `chrome.storage.local`，不进入源码和 Git 历史。
- 等待回收页的 React 表单完成初始化后，自动填写学号、姓名和作业内容，并直接提交。
- 从当前 Git 仓库页面识别仓库根地址，也支持手动粘贴地址。
- 一条命令提交本地变更、上传到 GitHub 并打开回收页。
- 普通 `git push` 因当前网络不可用时，自动通过已登录的 GitHub CLI API 完成同一提交的备用上传。
- 作业内容强制为纯远程仓库 URL，不添加标题、说明或其他 Markdown。
- 自动填写和自动提交固定开启，并使用本地记录拦截同一份内容的重复提交。
- 自动填写不会覆盖回收页里已有且不同的内容。

## 安装

1. 打开 Chrome 的 `chrome://extensions/`（Edge 使用 `edge://extensions/`）。
2. 开启右上角“开发者模式”。
3. 选择“加载已解压的扩展程序”，选择本项目根目录。
4. 打开扩展的“设置”，填写姓名和学号并保存。身份信息只保存在当前浏览器中。

## 使用

首次使用且已经创建了一个空远程仓库：

```bash
node scripts/publish-and-submit.mjs --remote https://github.com/你的账号/仓库名.git
```

以后在同一仓库中只需运行：

```bash
npm run submit
```

脚本会列出准备提交的文件并请求确认，然后执行 `git add -A`、`git commit`、上传 GitHub，最后打开回收页。扩展会等待页面脚本初始化完成，再填入固定身份和纯仓库 URL；如果普通 `git push` 受网络限制，脚本会在确认 GitHub 历史可安全快进后自动使用 GitHub CLI API 备用上传。需要完全无人值守时可以使用：

```bash
node scripts/publish-and-submit.mjs --yes
```

如果仓库没有 `origin`，脚本也可通过已经登录的 GitHub CLI 自动创建公开仓库：

```bash
gh auth login
node scripts/publish-and-submit.mjs --repo 仓库名 --public
```

默认创建公开仓库，方便课程系统和教师访问；姓名与学号只存在浏览器本地存储，不会随代码上传。需要私有仓库时可显式使用 `--private`。当前机器未安装 `gh` 时，请先在网站创建空仓库，再使用 `--remote` 方式。

仍然可以从 GitHub / Gitee / GitLab / Bitbucket 仓库页面点击扩展，手动输入或自动识别仓库地址后提交。

> 回收页提示“提交后不可修改”。本版本按要求固定开启自动提交，请务必在打开回收系统前确认仓库地址正确。

脚本会拒绝自动提交 `.env`、私钥、证书和常见凭据文件。如确认这些文件不含敏感信息，必须显式添加 `--allow-sensitive`。

只需要上传、不立即打开回收页时，可添加 `--no-open`。

## 开发与检查

项目不依赖第三方运行库。需要 Node.js 18 或更高版本：

```bash
npm run check
```

扩展仅申请 `storage`、`tabs`、`activeTab` 权限；身份与仓库信息平时保存在当前浏览器的本地存储中，内容脚本只在 `https://mn4wszvkpp.coze.site/*` 运行，提交时才把姓名、学号和仓库地址发送给该课程回收系统。仓库中不应保存真实姓名、学号、口令、令牌或密钥；常见敏感文件已加入 `.gitignore`，发布脚本也会在提交前再次拦截。
