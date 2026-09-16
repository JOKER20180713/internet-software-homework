import { access, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(await readFile(join(projectRoot, "manifest.json"), "utf8"));

if (manifest.manifest_version !== 3) throw new Error("manifest.json 必须使用 Manifest V3");

const referencedFiles = new Set([
  manifest.action?.default_popup,
  manifest.action?.default_icon,
  manifest.background?.service_worker,
  manifest.options_ui?.page,
  ...Object.values(manifest.icons || {}),
  ...(manifest.content_scripts || []).flatMap((entry) => entry.js || [])
].filter(Boolean));

await Promise.all([...referencedFiles].map((file) => access(join(projectRoot, file))));
console.log(`扩展结构检查通过：${referencedFiles.size} 个清单文件均存在。`);
