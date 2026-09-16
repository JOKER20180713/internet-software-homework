"use strict";

importScripts("shared.js");

chrome.runtime.onInstalled.addListener((details) => {
  chrome.storage.local.get(null, (stored) => {
    const settings = HomeworkShared.applyDefaults(stored);
    const persistedSettings = Object.fromEntries(
      Object.keys(HomeworkShared.DEFAULT_SETTINGS).map((key) => [key, settings[key]])
    );
    chrome.storage.local.set(persistedSettings);
  });
});
