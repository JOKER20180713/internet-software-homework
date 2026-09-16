import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { basename, join } from "node:path";
import process from "node:process";
import { createInterface } from "node:readline/promises";
import { createRequire } from "node:module";
import { pushViaGitHubApi } from "./github-api-push.mjs";

const require = createRequire(import.meta.url);
const shared = require("../src/shared.js");

function parseArgs(argv) {
  const options = {
    remote: "",
    repoName: "",
    visibility: "public",
    message: "提交作业",
    yes: false,
    dryRun: false,
    allowSensitive: false,
    noOpen: false
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--remote") options.remote = argv[++index] || "";
    else if (argument === "--repo") options.repoName = argv[++index] || "";
    else if (argument === "--message") options.message = argv[++index] || "";
    else if (argument === "--private") options.visibility = "private";
    else if (argument === "--public") options.visibility = "public";
    else if (argument === "--yes" || argument === "-y") options.yes = true;
    else if (argument === "--dry-run") options.dryRun = true;
    else if (argument === "--allow-sensitive") options.allowSensitive = true;
    else if (argument === "--no-open") options.noOpen = true;
    else if (argument === "--help" || argument === "-h") options.help = true;
    else throw new Error(`未知参数：${argument}`);
  }
  return options;
}

function printHelp() {
  console.log(`用法：npm run submit -- [选项]

选项：
  --remote <url>       首次使用时绑定一个已经创建好的远程仓库
  --repo <name>        没有 origin 时，由 GitHub CLI 创建的仓库名
  --public             创建公开仓库（默认；身份信息不会进入仓库）
  --private            明确创建私有仓库
  --message <text>     自动提交时使用的提交说明（默认：提交作业）
  --yes, -y            不询问，自动暂存并提交当前全部变更
  --allow-sensitive    明确允许提交 .env、密钥等敏感文件
  --no-open            推送后不打开回收页，仅输出提交链接
  --dry-run            只检查并展示流程，不提交、推送或打开浏览器
  --help, -h           显示帮助`);
}

function run(command, args, { cwd, allowFailure = false, inherit = false } = {}) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    stdio: inherit ? "inherit" : "pipe",
    windowsHide: true
  });
  if (result.error && !allowFailure) throw result.error;
  if (result.status !== 0 && !allowFailure) {
    const detail = String(result.stderr || result.stdout || "").trim();
    throw new Error(`${command} ${args.join(" ")} 执行失败${detail ? `：${detail}` : ""}`);
  }
  return result;
}

function commandExists(command) {
  return run(command, ["--version"], { allowFailure: true }).status === 0;
}

function resolveGhCommand() {
  if (commandExists("gh")) return "gh";
  if (process.platform !== "win32") return "";

  const candidates = [
    join(process.env.ProgramFiles || "C:\\Program Files", "GitHub CLI", "gh.exe"),
    join(process.env.LOCALAPPDATA || "", "Programs", "GitHub CLI", "gh.exe")
  ];
  return candidates.find((candidate) => candidate && existsSync(candidate)) || "";
}

function getOutput(command, args, cwd, allowFailure = false) {
  const result = run(command, args, { cwd, allowFailure });
  return {
    ok: result.status === 0,
    value: String(result.stdout || "").trim()
  };
}

function changedPaths(statusOutput) {
  return statusOutput
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => line.slice(3).split(" -> ").at(-1).replace(/^"|"$/g, ""));
}

function findSensitiveFiles(paths) {
  return paths.filter((path) =>
    /(^|\/)(\.env(?:\.|$)|id_rsa$|id_ed25519$|credentials\.json$)|\.(?:pem|key|p12|pfx)$/i.test(
      path.replaceAll("\\", "/")
    )
  );
}

async function confirmCommit(paths) {
  const terminal = createInterface({ input: process.stdin, output: process.stdout });
  console.log("将暂存并提交以下变更：");
  paths.forEach((path) => console.log(`  - ${path}`));
  const answer = await terminal.question("继续吗？[y/N] ");
  terminal.close();
  return /^y(?:es)?$/i.test(answer.trim());
}

function openUrl(url) {
  if (process.platform === "win32") {
    run("rundll32.exe", ["url.dll,FileProtocolHandler", url], { inherit: true });
  } else if (process.platform === "darwin") {
    run("open", [url], { inherit: true });
  } else {
    run("xdg-open", [url], { inherit: true });
  }
}

function pushToOrigin(root) {
  const branch = getOutput("git", ["symbolic-ref", "--short", "HEAD"], root, true);
  if (!branch.ok || !branch.value) throw new Error("当前处于 detached HEAD，无法确定要上传的分支。");

  const push = run("git", ["push", "-u", "origin", `HEAD:${branch.value}`], {
    cwd: root,
    allowFailure: true,
    inherit: true
  });
  if (push.status === 0) return;

  const gh = resolveGhCommand();
  const remote = getOutput("git", ["remote", "get-url", "origin"], root);
  if (!gh || !/github\.com/i.test(remote.value)) {
    throw new Error("git push 失败，且当前远程无法使用 GitHub CLI API 备用上传。");
  }
  const auth = run(gh, ["auth", "status"], { cwd: root, allowFailure: true });
  if (auth.status !== 0) {
    throw new Error("git push 失败，GitHub CLI 也尚未登录，无法执行备用上传。");
  }

  console.warn("普通 git push 不可用，正在切换到 GitHub CLI API 备用上传……");
  const uploaded = pushViaGitHubApi({
    cwd: root,
    remote: remote.value,
    branch: branch.value,
    gh
  });
  run("git", ["update-ref", `refs/remotes/origin/${branch.value}`, uploaded.sha], {
    cwd: root
  });
  run("git", ["config", `branch.${branch.value}.remote`, "origin"], { cwd: root });
  run("git", ["config", `branch.${branch.value}.merge`, `refs/heads/${branch.value}`], {
    cwd: root
  });
  console.log(`GitHub API 备用上传完成：${uploaded.repository}@${uploaded.sha.slice(0, 7)}`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }
  if (!commandExists("git")) throw new Error("未找到 Git，请先安装 Git。");

  const rootResult = getOutput("git", ["rev-parse", "--show-toplevel"], process.cwd(), true);
  if (!rootResult.ok) throw new Error("当前目录不是 Git 仓库。");
  const root = rootResult.value;
  const status = getOutput("git", ["status", "--porcelain"], root).value;
  const paths = changedPaths(status);
  const sensitive = findSensitiveFiles(paths);
  if (sensitive.length && !options.allowSensitive) {
    throw new Error(
      `检测到可能包含密钥的文件，已停止：${sensitive.join(", ")}。确认安全后可使用 --allow-sensitive。`
    );
  }

  const origin = getOutput("git", ["remote", "get-url", "origin"], root, true);
  const requestedRemote = shared.normalizeRepoUrl(options.remote);
  if (options.remote && !requestedRemote) throw new Error("--remote 不是有效的 HTTP(S) 或 SSH Git 地址。");

  if (options.dryRun) {
    const plannedRemote = origin.ok
      ? shared.normalizeRepoUrl(origin.value)
      : requestedRemote || `GitHub 新仓库：${options.repoName || basename(root)} (${options.visibility})`;
    console.log(`[演练] 本地仓库：${root}`);
    console.log(`[演练] 待提交文件：${paths.length}`);
    console.log(`[演练] 远程仓库：${plannedRemote}`);
    console.log("[演练] 将执行：提交变更 → 推送 origin → 打开回收页 → 仅填写仓库 URL → 自动提交");
    return;
  }

  if (paths.length) {
    if (!options.yes && !(await confirmCommit(paths))) throw new Error("已取消，未修改仓库。");
    run("git", ["add", "-A"], { cwd: root, inherit: true });
    const staged = run("git", ["diff", "--cached", "--quiet"], {
      cwd: root,
      allowFailure: true
    });
    if (staged.status !== 0) run("git", ["commit", "-m", options.message], { cwd: root, inherit: true });
  }

  const hasCommit = getOutput("git", ["rev-parse", "--verify", "HEAD"], root, true).ok;
  if (!hasCommit) throw new Error("仓库还没有可推送的提交。");

  if (!origin.ok) {
    if (options.remote) {
      run("git", ["remote", "add", "origin", options.remote], { cwd: root, inherit: true });
    } else {
      const gh = resolveGhCommand();
      if (!gh) {
        throw new Error(
          "当前仓库没有 origin，且未安装 GitHub CLI。请先创建远程仓库并使用 --remote <地址>，或安装 gh 后重试。"
        );
      }
      const auth = run(gh, ["auth", "status"], { cwd: root, allowFailure: true });
      if (auth.status !== 0) throw new Error("GitHub CLI 尚未登录，请先运行 gh auth login。");
      run(
        gh,
        [
          "repo",
          "create",
          options.repoName || basename(root),
          `--${options.visibility}`,
          "--source",
          root,
          "--remote",
          "origin"
        ],
        { cwd: root, inherit: true }
      );
    }
  } else if (options.remote && shared.normalizeRepoUrl(origin.value) !== requestedRemote) {
    throw new Error("仓库已有不同的 origin；为避免推错仓库，脚本不会自动覆盖它。");
  }

  pushToOrigin(root);
  const remote = getOutput("git", ["remote", "get-url", "origin"], root).value;
  const repoUrl = shared.normalizeRepoUrl(remote);
  if (!repoUrl) throw new Error("无法把 origin 转换为可提交的远程仓库网页地址。");

  const submissionUrl = shared.buildSubmissionUrl(shared.DEFAULT_SETTINGS.collectionUrl, repoUrl);
  console.log(`远程仓库已推送：${repoUrl}`);
  if (options.noOpen) {
    console.log(`作业提交链接：${submissionUrl}`);
  } else {
    console.log("正在打开作业回收页；扩展将只填写该仓库地址并自动提交。 ");
    openUrl(submissionUrl);
  }
}

main().catch((error) => {
  console.error(`提交失败：${error.message}`);
  process.exitCode = 1;
});
