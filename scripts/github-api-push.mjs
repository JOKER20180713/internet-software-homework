import { spawnSync } from "node:child_process";

function run(command, args, { cwd, input, allowFailure = false, encoding = "utf8" } = {}) {
  const result = spawnSync(command, args, {
    cwd,
    input,
    encoding,
    stdio: [input === undefined ? "ignore" : "pipe", "pipe", "pipe"],
    windowsHide: true,
    maxBuffer: 64 * 1024 * 1024
  });
  if (result.error && !allowFailure) throw result.error;
  if (result.status !== 0 && !allowFailure) {
    const detail = String(result.stderr || result.stdout || "").trim();
    throw new Error(`${command} ${args.join(" ")} 执行失败${detail ? `：${detail}` : ""}`);
  }
  return result;
}

function gitText(cwd, args, allowFailure = false) {
  const result = run("git", args, { cwd, allowFailure });
  return {
    ok: result.status === 0,
    value: String(result.stdout || "").trim()
  };
}

function ghApi(gh, endpoint, { method = "GET", body, allowFailure = false } = {}) {
  const args = ["api", endpoint, "--method", method];
  const input = body === undefined ? undefined : JSON.stringify(body);
  if (input !== undefined) args.push("--input", "-");
  const result = run(gh, args, { input, allowFailure });
  const output = String(result.stdout || "").trim();

  if (result.status !== 0) {
    return {
      ok: false,
      status: result.status,
      error: String(result.stderr || result.stdout || "").trim()
    };
  }

  return {
    ok: true,
    value: output ? JSON.parse(output) : {}
  };
}

function parseGitHubRepository(remote) {
  let value = String(remote || "").trim();
  const scp = value.match(/^git@github\.com:([^/]+)\/(.+)$/i);
  if (scp) value = `https://github.com/${scp[1]}/${scp[2]}`;

  try {
    const url = new URL(value);
    if (url.hostname.toLowerCase() !== "github.com") return null;
    const parts = url.pathname.replace(/\.git\/?$/i, "").split("/").filter(Boolean);
    if (parts.length !== 2) return null;
    return { owner: parts[0], repo: parts[1], slug: `${parts[0]}/${parts[1]}` };
  } catch {
    return null;
  }
}

function offsetToIso(timestamp, offset) {
  const match = String(offset).match(/^([+-])(\d{2})(\d{2})$/);
  if (!match) throw new Error(`无法解析 Git 时区：${offset}`);
  const direction = match[1] === "+" ? 1 : -1;
  const offsetSeconds = direction * (Number(match[2]) * 60 + Number(match[3])) * 60;
  const local = new Date((Number(timestamp) + offsetSeconds) * 1000)
    .toISOString()
    .replace(/\.\d{3}Z$/, "");
  return `${local}${match[1]}${match[2]}:${match[3]}`;
}

function parseIdentity(value) {
  const match = value.match(/^(.*) <([^<>]+)> (\d+) ([+-]\d{4})$/);
  if (!match) throw new Error(`无法解析 Git 提交身份：${value}`);
  return {
    name: match[1],
    email: match[2],
    date: offsetToIso(match[3], match[4])
  };
}

function readCommit(cwd, sha) {
  const raw = String(run("git", ["cat-file", "commit", sha], { cwd }).stdout);
  const divider = raw.indexOf("\n\n");
  if (divider < 0) throw new Error(`无法解析本地提交：${sha}`);

  const headers = raw.slice(0, divider);
  if (/^(?:gpgsig|mergetag|encoding) /m.test(headers)) {
    throw new Error("GitHub API 备用上传暂不支持签名、mergetag 或非 UTF-8 提交。");
  }

  const lines = headers.split("\n");
  const tree = lines.find((line) => line.startsWith("tree "))?.slice(5);
  const parents = lines
    .filter((line) => line.startsWith("parent "))
    .map((line) => line.slice(7));
  const author = lines.find((line) => line.startsWith("author "))?.slice(7);
  const committer = lines.find((line) => line.startsWith("committer "))?.slice(10);
  if (!tree || !author || !committer) throw new Error(`提交元数据不完整：${sha}`);

  return {
    sha,
    tree,
    parents,
    author: parseIdentity(author),
    committer: parseIdentity(committer),
    message: raw.slice(divider + 2)
  };
}

function readTreeEntries(cwd, commit) {
  const output = run("git", ["ls-tree", "-r", "-z", commit], {
    cwd,
    encoding: null
  }).stdout;

  return output
    .toString("utf8")
    .split("\0")
    .filter(Boolean)
    .map((entry) => {
      const tab = entry.indexOf("\t");
      const [mode, type, sha] = entry.slice(0, tab).split(" ");
      const path = entry.slice(tab + 1);
      if (type !== "blob") {
        throw new Error(`GitHub API 备用上传暂不支持 ${type} 条目：${path}`);
      }
      return { mode, type, sha, path };
    });
}

function ensureBlob({ gh, slug, cwd, entry, uploadedBlobs }) {
  if (uploadedBlobs.has(entry.sha)) return;
  const content = run("git", ["cat-file", "blob", entry.sha], {
    cwd,
    encoding: null
  }).stdout.toString("base64");
  const response = ghApi(gh, `repos/${slug}/git/blobs`, {
    method: "POST",
    body: { content, encoding: "base64" }
  });
  if (response.value.sha !== entry.sha) {
    throw new Error(`远程 blob 校验失败：${entry.path}`);
  }
  uploadedBlobs.add(entry.sha);
}

function uploadCommit({ gh, slug, cwd, commitSha, uploadedBlobs }) {
  const commit = readCommit(cwd, commitSha);
  const entries = readTreeEntries(cwd, commitSha);
  entries.forEach((entry) => ensureBlob({ gh, slug, cwd, entry, uploadedBlobs }));

  const treeResponse = ghApi(gh, `repos/${slug}/git/trees`, {
    method: "POST",
    body: {
      tree: entries.map(({ path, mode, type, sha }) => ({ path, mode, type, sha }))
    }
  });
  if (treeResponse.value.sha !== commit.tree) {
    throw new Error(`远程 tree 校验失败：${commitSha}`);
  }

  const commitResponse = ghApi(gh, `repos/${slug}/git/commits`, {
    method: "POST",
    body: {
      message: commit.message,
      tree: commit.tree,
      parents: commit.parents,
      author: commit.author,
      committer: commit.committer
    }
  });
  if (commitResponse.value.sha !== commitSha) {
    throw new Error(
      `远程提交校验失败：本地 ${commitSha}，GitHub ${commitResponse.value.sha}。远程分支未更新。`
    );
  }
}

function createBootstrapBranch(gh, slug, defaultBranch) {
  const response = ghApi(gh, `repos/${slug}/contents/.codex-bootstrap`, {
    method: "PUT",
    body: {
      message: "Initialize repository for API upload",
      content: Buffer.from("temporary\n", "utf8").toString("base64"),
      branch: defaultBranch
    }
  });
  return response.value.commit.sha;
}

export function pushViaGitHubApi({ cwd, remote, branch, gh, log = console.log }) {
  const repository = parseGitHubRepository(remote);
  if (!repository) throw new Error("远程地址不是可识别的 GitHub 仓库。");

  const repoResponse = ghApi(gh, `repos/${repository.slug}`);
  const repoInfo = repoResponse.value;
  const refEndpoint = `repos/${repository.slug}/git/ref/heads/${branch}`;
  let refResponse = ghApi(gh, refEndpoint, { allowFailure: true });
  let remoteSha = refResponse.ok ? refResponse.value.object.sha : "";
  let bootstrapBranch = "";

  if (!remoteSha) {
    const defaultBranch = repoInfo.default_branch || "main";
    const defaultRef = ghApi(
      gh,
      `repos/${repository.slug}/git/ref/heads/${defaultBranch}`,
      { allowFailure: true }
    );
    if (defaultRef.ok) {
      throw new Error(`GitHub 上不存在 ${branch} 分支，且仓库并非空仓库；已停止以避免覆盖。`);
    }
    bootstrapBranch = defaultBranch;
    log(`GitHub 空仓库初始化：${bootstrapBranch}`);
    createBootstrapBranch(gh, repository.slug, bootstrapBranch);
  }

  const head = gitText(cwd, ["rev-parse", "HEAD"]).value;
  let commits;
  if (remoteSha) {
    if (remoteSha === head) return { sha: head, branch, repository: repository.slug };
    const remoteExistsLocally = gitText(cwd, ["cat-file", "-e", `${remoteSha}^{commit}`], true).ok;
    const fastForward =
      remoteExistsLocally &&
      run("git", ["merge-base", "--is-ancestor", remoteSha, head], {
        cwd,
        allowFailure: true
      }).status === 0;
    if (!fastForward) {
      throw new Error("GitHub 远程分支与本地历史不一致；已停止以避免强制覆盖。");
    }
    commits = gitText(cwd, ["rev-list", "--reverse", "--topo-order", `${remoteSha}..${head}`]).value;
  } else {
    commits = gitText(cwd, ["rev-list", "--reverse", "--topo-order", head]).value;
  }

  const commitList = commits.split(/\r?\n/).filter(Boolean);
  const uploadedBlobs = new Set();
  commitList.forEach((commitSha, index) => {
    log(`GitHub API 上传提交 ${index + 1}/${commitList.length}：${commitSha.slice(0, 7)}`);
    uploadCommit({
      gh,
      slug: repository.slug,
      cwd,
      commitSha,
      uploadedBlobs
    });
  });

  if (bootstrapBranch) {
    if (bootstrapBranch === branch) {
      ghApi(gh, `repos/${repository.slug}/git/refs/heads/${branch}`, {
        method: "PATCH",
        body: { sha: head, force: true }
      });
    } else {
      ghApi(gh, `repos/${repository.slug}/git/refs`, {
        method: "POST",
        body: { ref: `refs/heads/${branch}`, sha: head }
      });
      ghApi(gh, `repos/${repository.slug}`, {
        method: "PATCH",
        body: { default_branch: branch }
      });
      ghApi(gh, `repos/${repository.slug}/git/refs/heads/${bootstrapBranch}`, {
        method: "DELETE"
      });
    }
  } else {
    ghApi(gh, `repos/${repository.slug}/git/refs/heads/${branch}`, {
      method: "PATCH",
      body: { sha: head, force: false }
    });
  }

  return { sha: head, branch, repository: repository.slug };
}

export const __test = {
  parseGitHubRepository,
  offsetToIso
};
