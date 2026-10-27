# CampusClaw 个人项目阶段性验收

在 09/30 的 Token 登录和班级知识库项目上，新增四个 AI 应用、可保存的提示词模板、Skill 内置/上传/按需加载、外部 HTTP 计算器、MCP 接入及逐轮调用记录。

**本次作业独立目录：** `assignments/2026-10-28-stage-review`

- 仓库：https://github.com/JOKER20180713/internet-software-homework
- 作业目录：https://github.com/JOKER20180713/internet-software-homework/tree/master/assignments/2026-10-28-stage-review
- 提交文件：[个人项目阶段性验收报告.pdf](output/pdf/个人项目阶段性验收报告.pdf)
- 真实验收记录：`evidence/01-template.json` 至 `08-ui-template.json`
- 实际界面截图：`evidence/screenshots/`，左侧为应用，右侧为真实调用记录。

## 启动

需要 Python 3.12+、Node.js 24+ 和阿里云百炼 API Key。仅在本机演示，两个服务绑定 127.0.0.1；不要把默认演示账号部署到公网。

```powershell
cd assignments/2026-10-28-stage-review
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm ci --ignore-scripts
# 从本机已有环境读取 DASHSCOPE_API_KEY，不把密钥写入仓库。
# 若 Node.js 不在 PATH，可用 MCP_NODE 环境变量指定 node.exe 的绝对路径。
.\start.ps1
```

打开 http://127.0.0.1:8092/platform 。材料管理页面为 http://127.0.0.1:8092/ 。

演示账号：A 班教师 `teacher_a / teacherpass123`，A 班学生 `student_a1 / studentpass123`，B 班学生 `student_b1 / studentpass123`，B 班教师 `teacher_b / teacherpass123`。凭据是公开的本地演示数据，不是实际学校账号。

首次启动数据库为空，执行 `python verify_live.py` 会上传本目录合成资料、运行真实百炼调用并导出证据（产生模型调用费用）。仅在新建的演示数据库上执行；不要向验收数据库上传私人材料。数据、登录密钥和依赖目录已被 `.gitignore` 排除。

## 五项验证结论

1. 对话向百炼 `chat/completions` 发送 `model=qwen-plus`、`messages`、`temperature=0`、`enable_thinking=false`、`max_tokens=800`；工具模式增加 `tools`，首次指定工具时增加 `tool_choice`。渲染后的模板每轮在 system 消息中发送。完整响应保留 `choices`、`usage`、`id` 等服务端字段。
2. 知识库先按登录账号的班级过滤，再做关键词/向量混合检索，最多取 2 个片段。本次实际发送 A 班 5 个索引片段中的 2 个，不含 B 班内容。索引阶段会把文档切片发送到 embedding 接口；这是入库处理，不是每次问答把全部文档发送给聊天模型。
3. 本轮绑定 Skill 的首个模型请求仅含 ID、名称、描述及 `load_skill` 定义。模型请求加载后，服务端把该 Skill 的完整正文作为 `role=tool` 返回；本轮后续请求会包含正文。未绑定 Skill 的正文不发送。下一轮对话重新按需加载，不持久化之前的工具正文到聊天历史。
4. 内置计算 Skill 实际执行：第一轮模型调用 `load_skill`；第二轮读取正文后调用独立 HTTP 计算器；第三轮根据真实结果回答 63。服务器校验绑定、所属用户、工具白名单和参数，不直接执行上传的 Markdown 或代码。
5. MCP 客户端通过 stdio 完成 `initialize → notifications/initialized → tools/list → tools/call`。仅将允许的 `get-sum` 映射为 LLM 的 `mcp_add` 函数定义。模型返回参数后，服务端转成 MCP 调用，把结果加入 `role=tool`，再次请求模型；实测 `137+286=423`。

## 验证方式

```powershell
New-Item -ItemType Directory -Force .test-data
python -m unittest test_auth test_rag test_platform -v
python verify_live.py
```

自动测试 27 项，覆盖登录、Token 失效、上传/下载权限、班级隔离、来源验证、模板、多轮历史、Skill 正文延迟加载、上传校验、记录所属用户和工具参数。真实模型验收与单元测试分开：单元测试使用 mock，`evidence/0*.json` 来自真实百炼响应。

Chrome/Playwright 检查了 1600×1100 与 390×844 两种视口、模板保存刷新、真实网页问答、Skill 上传、历史记录切换和退出。Browser 插件未提供，使用本机 Playwright 回退。结果见 `evidence/browser-checks.json`。

## 文件说明

| 文件 | 作用 |
|---|---|
| `app.py`、`knowledge.py` | 原有 JWT、材料权限、SQLite 持久化与混合检索 |
| `platform_api.py` | 应用、模板、Skill、对话编排、私有调用记录 API |
| `platform.html`、`platform.js` | 左侧工作区与右侧真实调用记录 |
| `tracing.py` | ContextVar 隔离每轮记录，不记录认证请求头 |
| `external_calculator.py` | 独立 HTTP 计算服务，仅数字四则运算 |
| `mcp_client.py` | 有超时和白名单的 stdio JSON-RPC 客户端 |
| `skills/`、`fixtures/` | 内置技能、上传技能样例与合成课堂材料 |
| `evidence/` | 真实请求/响应 JSON、核验结果、截图 |

## 范围与限制

这是课程阶段验收原型：Skill 支持约定的 UTF-8 `.md` 格式（name、description、正文），不运行上传的任意脚本；MCP 接入固定为获确认的官方示例包 `@modelcontextprotocol/server-everything@2.0.1`，只开放 `get-sum`，不提供任意服务器安装入口。记录是应用捕获的真实请求/响应 JSON，不是伪造的浏览器网络截图；未保存 HTTP 认证头。原始记录会包含用户问题，应保持本地私有，发布时仅选择本次合成演示数据。

向量以 JSON 存入 SQLite，适用于本次小规模演示；关键词检索可能召回弱相关片段，本次第二个候选为美术材料，最终回答仅引用科学材料。当前仅校验引用编号，不能自动证明每个事实均受来源支持；通用应用的生成内容也需要人工核对。Flask 开发服务器、公开演示账号、有限历史窗口（最多 3 轮）不属于生产部署方案。

MCP 预检查于 2026-10-27 查询，登记最近扫描时间为 2026-10-15、身份未验证、D 级、建议 ask-first；经用户确认，仅接入加法工具。登记不是源码审计或安全认证，亦不保证对应当前包全部功能。实际工具列表记录在 `07-mcp.json`，但只有一个工具被映射给 LLM。

参考：[百炼 Function Calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling)、[MCP 官方示例](https://github.com/modelcontextprotocol/servers/tree/main/src/everything)、[预检查登记](https://policylayer.com/tools/server-everything)。
