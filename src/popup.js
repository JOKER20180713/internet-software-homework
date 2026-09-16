(async function initializePopup() {
  "use strict";

  const shared = globalThis.HomeworkShared;
  const elements = {
    settingsButton: document.querySelector("#settingsButton"),
    footerSettings: document.querySelector("#footerSettings"),
    statusIcon: document.querySelector("#statusIcon"),
    statusTitle: document.querySelector("#statusTitle"),
    statusDescription: document.querySelector("#statusDescription"),
    finishDot: document.querySelector("#finishDot"),
    repoInput: document.querySelector("#repoInput"),
    repoHint: document.querySelector("#repoHint"),
    autoFill: document.querySelector("#autoFill"),
    autoSubmit: document.querySelector("#autoSubmit"),
    primaryButton: document.querySelector("#primaryButton"),
    toast: document.querySelector("#toast")
  };

  const storageGet = (area, keys) => new Promise((resolve) => area.get(keys, resolve));
  const storageSet = (area, value) => new Promise((resolve) => area.set(value, resolve));
  const queryTabs = (query) => new Promise((resolve) => chrome.tabs.query(query, resolve));
  const createTab = (properties) => new Promise((resolve) => chrome.tabs.create(properties, resolve));
  const sendMessage = (tabId, message) =>
    new Promise((resolve) => {
      chrome.tabs.sendMessage(tabId, message, (response) => {
        if (chrome.runtime.lastError) resolve({ ok: false, reason: "content-unavailable" });
        else resolve(response || { ok: false, reason: "empty-response" });
      });
    });

  let settings = shared.applyDefaults(await storageGet(chrome.storage.local, null));
  const [activeTab] = await queryTabs({ active: true, currentWindow: true });
  const activeUrl = activeTab?.url || "";
  const isCollectionPage = activeUrl.startsWith(settings.collectionUrl);
  const detectedRepo = shared.repoFromPageUrl(activeUrl);

  elements.repoInput.value = detectedRepo || settings.repoUrl;
  elements.autoFill.checked = settings.autoFill;
  elements.autoSubmit.checked = settings.autoSubmit;

  function showToast(message) {
    elements.toast.textContent = message;
    window.setTimeout(() => {
      if (elements.toast.textContent === message) elements.toast.textContent = "";
    }, 2600);
  }

  function showStatus(title, description, warning = false) {
    elements.statusTitle.textContent = title;
    elements.statusDescription.textContent = description;
    elements.statusIcon.classList.toggle("is-warning", warning);
  }

  function refreshStatus() {
    const candidate = shared.normalizeRepoUrl(elements.repoInput.value);
    const profile = { ...settings, repoUrl: candidate };
    if (!settings.studentId.trim() || !settings.name.trim()) {
      showStatus("请先完成身份设置", "填写学号和姓名后即可自动化", true);
      elements.primaryButton.textContent = "自动提交作业";
      return;
    }
    if (!candidate) {
      showStatus("还缺少仓库地址", "粘贴地址，或从 GitHub / Gitee 仓库页打开扩展", true);
      elements.primaryButton.textContent = "自动提交作业";
      return;
    }
    if (isCollectionPage) {
      showStatus("当前页面可提交", "已检测到作业回收页面，将自动填写并提交");
      elements.primaryButton.textContent = "自动填写并提交";
    } else if (detectedRepo) {
      showStatus("已识别当前仓库", "点击后将打开回收系统并自动提交");
      elements.primaryButton.textContent = "自动提交作业";
      elements.repoHint.textContent = "已从当前 Git 仓库页面识别";
    } else {
      showStatus("信息已准备好", "点击后将打开回收系统并自动提交");
      elements.primaryButton.textContent = "自动提交作业";
    }
  }

  async function saveQuickSettings() {
    const repoUrl = shared.normalizeRepoUrl(elements.repoInput.value);
    if (!repoUrl) return false;
    settings = {
      ...settings,
      repoUrl,
      autoFill: elements.autoFill.checked,
      autoSubmit: elements.autoSubmit.checked
    };
    await storageSet(chrome.storage.local, settings);
    elements.repoInput.value = repoUrl;
    return true;
  }

  async function openOptions() {
    await chrome.runtime.openOptionsPage();
  }

  elements.settingsButton.addEventListener("click", openOptions);
  elements.footerSettings.addEventListener("click", openOptions);
  elements.repoInput.addEventListener("input", refreshStatus);
  elements.repoInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") elements.primaryButton.click();
  });

  elements.primaryButton.addEventListener("click", async () => {
    if (!settings.studentId.trim() || !settings.name.trim()) {
      await openOptions();
      return;
    }
    if (!(await saveQuickSettings())) {
      showToast("请先填写有效的仓库地址");
      elements.repoInput.focus();
      return;
    }

    if (!isCollectionPage) {
      await createTab({ url: settings.collectionUrl });
      return;
    }

    const result = await sendMessage(activeTab.id, { type: "HOMEWORK_AUTOFILL_FILL" });
    if (!result.ok) {
      showToast(result.reason === "form-not-found" ? "未找到回收表单" : "填写失败，请刷新页面重试");
      return;
    }
    elements.finishDot.classList.add("is-complete");
    showToast(result.submitted ? "已自动提交" : "已填写，请检查后提交");
  });

  refreshStatus();
})();
