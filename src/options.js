(async function initializeOptions() {
  "use strict";

  const shared = globalThis.HomeworkShared;
  const form = document.querySelector("#settingsForm");
  const fields = {
    studentId: document.querySelector("#studentId"),
    name: document.querySelector("#name"),
    repoUrl: document.querySelector("#repoUrl"),
    collectionUrl: document.querySelector("#collectionUrl"),
    autoFill: document.querySelector("#autoFill"),
    autoSubmit: document.querySelector("#autoSubmit")
  };
  const saveStatus = document.querySelector("#saveStatus");
  const resetHistory = document.querySelector("#resetHistory");
  const navLinks = [...document.querySelectorAll("nav a")];

  const storageGet = (area, keys) => new Promise((resolve) => area.get(keys, resolve));
  const storageSet = (area, value) => new Promise((resolve) => area.set(value, resolve));
  const storageRemove = (area, keys) => new Promise((resolve) => area.remove(keys, resolve));

  const settings = shared.applyDefaults(await storageGet(chrome.storage.local, null));
  Object.entries(fields).forEach(([key, element]) => {
    if (element.type === "checkbox") element.checked = Boolean(settings[key]);
    else element.value = settings[key];
  });

  function setStatus(message, isError = false) {
    saveStatus.textContent = message;
    saveStatus.classList.toggle("is-error", isError);
    window.setTimeout(() => {
      if (saveStatus.textContent === message) saveStatus.textContent = "";
    }, 3000);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const next = {
      studentId: fields.studentId.value.trim(),
      name: fields.name.value.trim(),
      repoUrl: fields.repoUrl.value.trim()
        ? shared.normalizeRepoUrl(fields.repoUrl.value)
        : "",
      collectionUrl: shared.DEFAULT_SETTINGS.collectionUrl,
      autoFill: true,
      autoSubmit: true
    };

    if (!next.studentId || !next.name) {
      setStatus("请填写学号和姓名", true);
      (next.studentId ? fields.name : fields.studentId).focus();
      return;
    }

    if (fields.repoUrl.value.trim() && !next.repoUrl) {
      setStatus("仓库地址格式不正确", true);
      fields.repoUrl.focus();
      return;
    }
    await storageSet(chrome.storage.local, next);
    fields.repoUrl.value = next.repoUrl;
    setStatus("✓ 已保存");
  });

  resetHistory.addEventListener("click", async () => {
    await storageRemove(chrome.storage.local, "submissionHistory");
    setStatus("✓ 已清除防重复记录");
  });

  const sections = [...document.querySelectorAll(".settings-section")];
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      navLinks.forEach((link) =>
        link.classList.toggle("active", link.hash === `#${visible.target.id}`)
      );
    },
    { rootMargin: "-20% 0px -65% 0px", threshold: [0, 0.2, 0.6] }
  );
  sections.forEach((section) => observer.observe(section));
})();
