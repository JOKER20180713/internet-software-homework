(function startContentScript() {
  "use strict";

  const shared = globalThis.HomeworkShared;
  const FIELD_SELECTORS = {
    studentId: "#studentId",
    name: "#name",
    content: "textarea"
  };

  function storageGet(area, keys) {
    return new Promise((resolve) => area.get(keys, resolve));
  }

  function storageSet(area, value) {
    return new Promise((resolve) => area.set(value, resolve));
  }

  async function loadSettings() {
    const stored = await storageGet(chrome.storage.local, null);
    let settings = shared.applyDefaults(stored);
    const importedRepo = shared.repoFromSubmissionUrl(location.href);
    if (!importedRepo) return settings;

    settings = shared.applyDefaults({ ...settings, repoUrl: importedRepo });
    await storageSet(chrome.storage.local, { repoUrl: importedRepo });

    const cleanUrl = new URL(location.href);
    cleanUrl.searchParams.delete("homeworkRepo");
    history.replaceState(null, "", `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`);
    return settings;
  }

  function dispatchValueEvents(element) {
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setControlledValue(element, value, { pulse = false } = {}) {
    const prototype =
      element instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;

    const assign = (nextValue) => {
      if (setter) setter.call(element, nextValue);
      else element.value = nextValue;
      dispatchValueEvents(element);
    };

    // If the static HTML was filled before React hydration, the DOM value can be
    // correct while React state is still empty. A harmless intermediate value
    // guarantees that the hydrated onChange handler observes a real change.
    if (pulse && element.value === value) assign(`${value} `);
    assign(value);
  }

  function waitForDocumentReady(timeoutMs = 20000) {
    if (document.readyState === "complete") return Promise.resolve(true);

    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => {
        window.removeEventListener("load", onLoad);
        resolve(false);
      }, timeoutMs);
      const onLoad = () => {
        window.clearTimeout(timeout);
        resolve(true);
      };
      window.addEventListener("load", onLoad, { once: true });
    });
  }

  function locateForm() {
    return {
      studentId: document.querySelector(FIELD_SELECTORS.studentId),
      name: document.querySelector(FIELD_SELECTORS.name),
      content: document.querySelector(FIELD_SELECTORS.content)
    };
  }

  function isCompleteForm(form) {
    return Boolean(form.studentId && form.name && form.content);
  }

  async function waitForForm(timeoutMs = 20000) {
    const initial = locateForm();
    if (isCompleteForm(initial)) return initial;

    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => {
        observer.disconnect();
        resolve(locateForm());
      }, timeoutMs);
      const observer = new MutationObserver(() => {
        const form = locateForm();
        if (!isCompleteForm(form)) return;
        window.clearTimeout(timeout);
        observer.disconnect();
        resolve(form);
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });
    });
  }

  function findSubmitButton() {
    return [...document.querySelectorAll("button")].find((button) =>
      button.textContent?.trim().includes("提交作业")
    );
  }

  async function waitForEnabledSubmit(refill, timeoutMs = 15000) {
    const startedAt = Date.now();
    let lastRefillAt = 0;
    while (Date.now() - startedAt < timeoutMs) {
      const button = findSubmitButton();
      if (button && !button.disabled) return button;

      const now = Date.now();
      if (refill && now - lastRefillAt >= 400) {
        refill();
        lastRefillAt = now;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    return null;
  }

  async function autoSubmitIfSafe(settings, conflicts, refill) {
    if (!settings.autoSubmit) return { submitted: false, reason: "auto-submit-off" };
    if (conflicts.length) return { submitted: false, reason: "conflicting-fields" };

    const fingerprint = shared.createSubmissionFingerprint(settings);
    const { submissionHistory = {} } = await storageGet(chrome.storage.local, [
      "submissionHistory"
    ]);
    if (submissionHistory[fingerprint]) {
      return { submitted: false, reason: "duplicate-blocked" };
    }

    const button = await waitForEnabledSubmit(refill);
    if (!button) return { submitted: false, reason: "submit-unavailable" };

    const nextHistory = {
      ...submissionHistory,
      [fingerprint]: { attemptedAt: new Date().toISOString() }
    };
    await storageSet(chrome.storage.local, { submissionHistory: nextHistory });
    button.click();
    return { submitted: true, reason: "submitted" };
  }

  async function fillPage({ force = false } = {}) {
    const settings = await loadSettings();
    if (!shared.isProfileComplete(settings)) {
      return { ok: false, reason: "profile-incomplete" };
    }

    await waitForDocumentReady();
    const form = await waitForForm();
    if (!isCompleteForm(form)) return { ok: false, reason: "form-not-found" };

    const desired = {
      studentId: settings.studentId.trim(),
      name: settings.name.trim(),
      content: shared.normalizeRepoUrl(settings.repoUrl)
    };
    const conflicts = [];

    Object.entries(desired).forEach(([key, value]) => {
      const element = form[key];
      const existing = String(element.value || "").trim();
      if (existing && existing !== value && !force) {
        conflicts.push(key);
        return;
      }
      if (force || !existing) setControlledValue(element, value);
    });

    const refill = () => {
      const currentForm = locateForm();
      if (!isCompleteForm(currentForm)) return;
      Object.entries(desired).forEach(([key, value]) => {
        if (!conflicts.includes(key)) {
          setControlledValue(currentForm[key], value, { pulse: true });
        }
      });
    };

    const submit = await autoSubmitIfSafe(settings, conflicts, refill);
    return {
      ok: true,
      filled: Object.keys(desired).filter((key) => !conflicts.includes(key)),
      conflicts,
      ...submit
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "HOMEWORK_AUTOFILL_STATUS") {
      const form = locateForm();
      sendResponse({ ok: true, formFound: isCompleteForm(form), url: location.href });
      return false;
    }
    if (message?.type === "HOMEWORK_AUTOFILL_FILL") {
      fillPage({ force: true })
        .then(sendResponse)
        .catch((error) => sendResponse({ ok: false, reason: error.message }));
      return true;
    }
    return false;
  });

  loadSettings()
    .then((settings) => {
      if (settings.autoFill) return fillPage({ force: false });
      return null;
    })
    .catch(() => {});
})();
