# Oh My AI Living Room

一个温馨的「AI 客厅」桌面程序：客厅里住着几位角色，每位角色背后都是一个 CLI coding agent（Claude Code / Codex），有自己的人设、专长和 skills。点角色就能聊天或派任务；她们在无聊、工作中、完成时会有不同的动画。

第一版（v0.1）：Tauri 2 + React，已实现角色 **Iris（艾莉丝）**，支持 Claude Code 与 Codex 两种 harness，所有对话存进 SQLite。

## 运行

依赖：Node 20+、Rust（`rustup`）、Linux 上的 WebKitGTK 4.1 开发包（`libwebkit2gtk-4.1-dev` 等 Tauri 依赖），以及 `claude`（Claude Code CLI，已登录）和/或 `codex` CLI。

```bash
npm install
npm run tauri dev      # 开发模式
npm run tauri build    # 打包：src-tauri/target/release/bundle/{deb,appimage}
npm run dev            # 只开前端：浏览器里用 mock 数据预览 UI（http://localhost:1420）
```

WSLg 下如果窗口白屏，可加 `WEBKIT_DISABLE_DMABUF_RENDERER=1`。

### Windows

Tauri 不能在 Linux 上可靠地交叉打包 Windows 版，请在 Windows 本机构建（PowerShell）：

```powershell
# 1. 工具链（一次性）
winget install Rustlang.Rustup          # 装完重开终端；默认 stable-x86_64-pc-windows-msvc
# 需要 VS 2022 Build Tools 的「使用 C++ 的桌面开发」（MSVC + Windows SDK）、Node 20+、WebView2（Win10/11 自带）

# 2. Agent CLI（Windows 版，和 WSL 里的那份是两套）
npm install -g @anthropic-ai/claude-code   # 然后运行一次 `claude` 登录；Claude Code 在 Windows 上需要 Git for Windows
npm install -g @openai/codex               # 可选

# 3. 把项目放到 Windows 盘再装依赖（不要直接用 \\wsl$ 路径，也不要复用 Linux 的 node_modules）
git clone <repo> E:\dev\Oh_My_AI_Living_Room   # 或整个目录复制过去后删掉 node_modules 和 src-tauri\target
cd E:\dev\Oh_My_AI_Living_Room
npm install

npm run tauri dev          # 测试
npm run build:windows      # 打包 → src-tauri\target\release\bundle\{nsis,msi}\
```

Windows 下数据（对话库、设置、角色工作目录）在 `%APPDATA%\ohmyailivingroom\`；找不到 `claude` 时可在设置里填 `claude.exe` / `claude.cmd` 的完整路径。

## 功能

| | |
|---|---|
| 客厅场景 | `public/background.jpg` 铺满窗口（cover），角色按 1672×941 舞台坐标摆放 |
| 角色状态 | 看书（默认）→ 闲置 `boredAfterSec` 秒后**发呆**（打哈欠）→ 派任务时**工作中**（戴眼镜写笔记）→ 任务完成**完成啦**（比 V），点她查看后回到看书。聊天回复中显示「…」气泡 |
| 动画 | Rigby2D 骨骼动画导出的序列帧（呼吸、眨眼、点头、头发摆动、挥手），四个姿势共用同一画框，切换时淡入淡出 |
| 对话框 | 点角色（像素级命中）打开：💬 聊天 / 📋 派任务、流式回复、工具调用折叠行、停止按钮、新对话、历史记录（重命名/删除）、「关于她」（人设、专长、skills、harness/模型/权限设置） |
| Agent | 每个角色在自己的工作目录里运行 harness：`~/.local/share/com.ohmyai.livingroom/workspaces/<id>/`，产出放 `outputs/` |
| 存储 | `~/.local/share/com.ohmyai.livingroom/living_room.db`：`conversations`（含 harness session id，用于续聊）+ `messages`（user / assistant / tool / error / system） |
| 通知 | 对话框关闭时任务完成/出错会弹出 toast，点 toast 直接打开那段对话 |

## Agent harness 适配（`src-tauri/src/agent.rs`）

| | Claude Code | Codex |
|---|---|---|
| 命令 | `claude -p --output-format stream-json --verbose --include-partial-messages --permission-mode <mode> --append-system-prompt <persona> [--model m] [--resume <sid>]` | `codex exec --json --skip-git-repo-check --sandbox workspace-write [--model m] [resume <thread>] -` |
| 人设 | `--append-system-prompt` | 工作目录里的 `AGENTS.md` |
| Skills | 复制到 `<workspace>/.claude/skills/`（项目级 skills） | 在 `AGENTS.md` 里列出并指向 SKILL.md |
| 续聊 | `system/init.session_id` | `thread.started.thread_id` |

两种输出都被解析成统一事件：`session / delta / message / tool / toolResult / done`，通过 Tauri 事件 `agent-event`、`agent-status` 推给前端。Prompt 走 stdin。GUI 启动时会自动把 `~/.local/bin`、`~/.npm-global/bin` 等加入 PATH，也可在设置里手动指定 CLI 路径。

> 已在 Linux（WSL2/WSLg）用 Claude Code 2.1.327 实测聊天、续聊、派任务写文件、使用 skill。Codex 适配按 `codex exec --json` 的事件格式实现并有单元测试，但本机未安装 codex，尚未实机验证。

## 新增角色

1. `characters/<id>/character.json`（参考 `characters/iris/character.json`）：人设 `persona`、`specialties`、`greeting`、`agent`（provider/model/permissionMode）、`scene`（舞台坐标 x/y/width）、`sprites`、气泡台词 `lines`。
2. `characters/<id>/skills/<skill>/SKILL.md`：角色专属 Claude Code skills。
3. 美术放到 `public/characters/<id>/`：`avatar.png`、`poses/<pose>.png`（静态，用于命中检测和加载前占位）、`anim/<pose>.json + .webp`（序列帧）。没有序列帧时只给 `image`，会退化为 CSS 呼吸/摇摆动画。

## 美术管线（`art/`）

1. **姿势变体**：ComfyUI `image_qwen_image_2_1_image_edit`（开启 prompt enhancer），以 Iris 原图为底改出 bored / working / done 三个姿势（`art/make_edit.py`，原图在 `art/src/`）。提示词要短、只描述要改的动作，长篇「保持不变」清单会让模型画成设定图。
2. **分层**：ComfyUI `seethrough-basic` 拆成 ~22 个图层（1024 画布）。
3. **修图层**：`art/tools/build_psd.py` —— 用原画颜色重新上色每层可见像素（修正缺失的瞳孔等），把没被覆盖的像素（如发带）并入邻近图层，输出 PSD。
4. **骨骼**：Rigby2D `autorig`（覆盖参数见 `art/rig/autorig_roles.json`，关 IK，手臂/道具挂躯干）→ `run_script` 跑 `art/rig/anims.py` 生成每个姿势的循环动画。工程文件在 `art/rig/*.rigby`。
5. **导出**：`export_sprite_sheet`（12fps，scale 0.6）→ `art/tools/pack_sheets.py` 按骨架原点对齐到统一画框、缩放 0.75、打包成方形 WebP 图集 + JSON，并生成首帧静态图。
