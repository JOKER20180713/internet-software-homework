(function bootstrapShared(root) {
  "use strict";

  const DEFAULT_SETTINGS = Object.freeze({
    studentId: "",
    name: "",
    repoUrl: "",
    collectionUrl: "https://mn4wszvkpp.coze.site/",
    autoFill: true,
    autoSubmit: true
  });

  function applyDefaults(value) {
    const raw = value && typeof value === "object" ? value : {};
    return {
      ...DEFAULT_SETTINGS,
      ...raw,
      studentId: String(raw.studentId || "").trim().slice(0, 30),
      name: String(raw.name || "").trim().slice(0, 100),
      repoUrl: normalizeRepoUrl(raw.repoUrl),
      collectionUrl: DEFAULT_SETTINGS.collectionUrl,
      autoFill: true,
      autoSubmit: true
    };
  }

  function normalizeRepoUrl(value) {
    let input = String(value || "").trim();
    if (!input) return "";

    const scpMatch = input.match(/^git@([^:]+):(.+)$/i);
    if (scpMatch) input = `https://${scpMatch[1]}/${scpMatch[2]}`;

    try {
      const url = new URL(input);
      if (url.protocol === "ssh:") {
        url.protocol = "https:";
        url.username = "";
        url.password = "";
        url.port = "";
      }
      if (!/^https?:$/.test(url.protocol)) return "";

      url.hash = "";
      url.search = "";
      url.username = "";
      url.password = "";
      url.pathname = url.pathname.replace(/\.git\/?$/i, "").replace(/\/+$/, "");
      return url.toString().replace(/\/$/, "");
    } catch {
      return "";
    }
  }

  function repoFromPageUrl(value) {
    try {
      const url = new URL(value);
      const host = url.hostname.toLowerCase().replace(/^www\./, "");
      let parts = url.pathname.split("/").filter(Boolean);

      if (host === "github.com" || host === "gitee.com" || host === "bitbucket.org") {
        if (parts.length < 2) return "";
        parts = parts.slice(0, 2);
      } else if (host === "gitlab.com") {
        const utilityIndex = parts.indexOf("-");
        if (utilityIndex >= 0) parts = parts.slice(0, utilityIndex);
        if (parts.length < 2) return "";
      } else {
        return "";
      }

      return normalizeRepoUrl(`https://${host}/${parts.join("/")}`);
    } catch {
      return "";
    }
  }

  function buildSubmissionUrl(collectionUrl, repoUrl) {
    const normalizedRepo = normalizeRepoUrl(repoUrl);
    if (!normalizedRepo) return "";
    try {
      const url = new URL(collectionUrl || DEFAULT_SETTINGS.collectionUrl);
      url.searchParams.set("homeworkRepo", normalizedRepo);
      return url.toString();
    } catch {
      return "";
    }
  }

  function repoFromSubmissionUrl(value) {
    try {
      const url = new URL(value);
      return normalizeRepoUrl(url.searchParams.get("homeworkRepo"));
    } catch {
      return "";
    }
  }

  function createSubmissionFingerprint(settings) {
    const normalized = applyDefaults(settings);
    return [
      normalized.collectionUrl.replace(/\/$/, ""),
      normalized.studentId.trim(),
      normalized.name.trim(),
      normalizeRepoUrl(normalized.repoUrl)
    ].join("\u241f");
  }

  function isProfileComplete(settings) {
    const value = applyDefaults(settings);
    return Boolean(
      value.studentId.trim() &&
        value.name.trim() &&
        normalizeRepoUrl(value.repoUrl)
    );
  }

  const api = {
    DEFAULT_SETTINGS,
    applyDefaults,
    normalizeRepoUrl,
    repoFromPageUrl,
    buildSubmissionUrl,
    repoFromSubmissionUrl,
    createSubmissionFingerprint,
    isProfileComplete
  };

  root.HomeworkShared = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
