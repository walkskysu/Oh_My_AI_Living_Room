# Oh My AI Living Room

一个温馨的「AI 客厅」桌面程序：客厅里住着几位角色，每位角色背后都是一个 CLI coding agent（Claude Code / Codex / DeepSeek Harness），有自己的人设、专长和 skills。点角色就能聊天或交代任务；她们在无聊、工作中、完成时会有不同的动画。

第一版（v0.1）：Tauri 2 + React，已实现角色 **Iris（艾莉丝）**（阅读与写作）、**Poppy（波比）**（画图、改图、反推提示词、拆图层）、**Claire（克莱尔）**（财经与股票技术分析）和 **Melody（美乐蒂）**（作曲、给歌词谱曲、纯音乐），支持 Claude Code、Codex 与 DeepSeek Harness 三种 harness，所有对话存进 SQLite。

## 运行

依赖：Node 20+、Rust（`rustup`）、Linux 上的 WebKitGTK 4.1 开发包（`libwebkit2gtk-4.1-dev` 等 Tauri 依赖），以及 `claude`（Claude Code CLI，已登录）、`codex` CLI、`dsh`（DeepSeek Harness，`npm install -g @deepseek-ai/dsh`，需要 Node 24.9+，`DEEPSEEK_API_KEY` 放在环境变量或 `~/.dsh/.env`）中的至少一个。

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
| 角色状态 | 看书（默认）→ 闲置 `boredAfterSec` 秒后**发呆**（打哈欠）→ 她开始动手（调用工具读写文件、执行命令等，或一轮回复超过 10 秒）时自动切到**工作中**（戴眼镜写笔记）→ 这一轮结束后**完成啦**（比 V），点她查看后回到看书。纯聊天回复中保持看书并显示「…」气泡 |
| 动画 | Rigby2D 骨骼动画导出的序列帧（呼吸、眨眼、点头、头发摆动、挥手），四个姿势共用同一画框，切换时淡入淡出 |
| 对话框 | 点角色（像素级命中）打开，聊天窗固定在右侧，场景会平移把这位角色移到剩余可见区域的中间（不会露出背景图边缘；本来就看得到的角色不动），关闭时滑回原位：单一输入框（不分聊天/任务，是否「工作」由后端按工具调用和耗时自动判断）、流式回复、工具调用折叠行、停止按钮、新对话、历史记录（重命名/删除）、「关于她」（人设、专长、skills、harness/模型/权限设置） |
| Agent | 每个角色在自己的工作目录里运行 harness：`~/.local/share/com.ohmyai.livingroom/workspaces/<id>/`，产出放 `outputs/` |
| 存储 | `~/.local/share/com.ohmyai.livingroom/living_room.db`：`conversations`（含 harness session id，用于续聊）+ `messages`（user / assistant / tool / error / system） |
| 音频 | 对话中提到的 `outputs/`、`inputs/` 里的 mp3 / wav / flac / ogg / m4a 显示为播放卡片：点 ▶ 才加载（歌一般几 MB），之后直接在聊天里播放、拖动进度；双击用系统播放器打开 |
| 附件 | 把文件拖到窗口上或在输入框粘贴截图，会复制到该角色工作目录的 `inputs/`，消息里以 `` `inputs/xxx.png` `` 引用；对话中提到的 `inputs/`、`outputs/` 图片直接显示缩略图（双击用系统看图软件打开） |
| Agent 检测 | 启动时（以及在设置里改了 CLI 路径后）检测本机有没有 `claude` / `codex` / `dsh`；有角色配置的 harness 本机找不到时，顶部弹出提示，列出是哪位角色、缺哪个命令，可以直接打开设置。该角色聊天窗的 harness 标签显示「未安装」，「关于她」的下拉框里也会标出未安装的 harness。浏览器预览可以用 `?missing=claude,dsh` 模拟 |
| 通知 | 对话框关闭时任务完成/出错会弹出 toast，点 toast 直接打开那段对话 |

## Poppy 的画图能力

| | Claude Code / DeepSeek Harness | Codex |
|---|---|---|
| 画图 / 改图 | `painting` skill → `comfy.py`（纯标准库）调用 ComfyUI：Qwen-Image 2.1 文生图 / 编辑 | Codex 内建图片生成 |
| 反推提示词 | `image-prompt-reverse` skill（[LunarXuan/image-prompt-reverse](https://github.com/LunarXuan/image-prompt-reverse)，GPL-3.0，原样收录）；可选 `comfy.py describe` 用 Qwen3-VL 先描述一遍作参考 | 同一 skill，直接看图 |
| 拆图层 | `comfy.py layers`（See-through，输出分层 PNG + PSD） | 不支持 |

- ComfyUI 地址在「客厅设置 → ComfyUI」里配置（默认 `http://127.0.0.1:8188`，带连接检测），以环境变量 `COMFYUI_URL` 传给 agent；`LIVING_ROOM_HARNESS` 告诉 skill 当前是 `claude`、`codex` 还是 `deepseek`。
- 工作流以 API 格式放在 `characters/poppy/skills/painting/workflows/`（由 ComfyUI 中保存的 `image_qwen_image_2_1_t2i` / `image_qwen_image_2_1_image_edit` / `QWenVL_desc_image_prompt` / `seethrough-basic` 转换而来），ComfyUI 端需装好对应模型和节点。
- `character.json` 的 `allowedTools`（如 `Bash(python3 .claude/skills/painting/comfy.py:*)`）以 `--allowedTools` 传给 Claude Code：无头模式没法弹确认框，skill 要跑的脚本必须预先放行（工作目录未被信任时 `.claude/settings.json` 里的 allow 会被忽略，所以不用它）。Iris 的 `to_pdf.py` 也同样放行。
- `character.json` 的 `harnessNotes.{claude,codex,deepseek}` 会分别追加到 Claude Code 的系统提示（persona.md）、Codex 的 `AGENTS.md` 和 DeepSeek Harness 的 persona（`dsh.patch.yml`），用来告诉角色在当前 harness 下该用哪种画图工具。

## Claire 的理财能力

| 技能 | 内容 |
|---|---|
| `stock-analysis` | `stock.py`（纯标准库）：输入美股 / A 股 / 港股代码或公司名（`AAPL`、`600519`、`0700`、`腾讯`），拉取约一年日线（Yahoo Finance，A 股 / 港股优先腾讯前复权，互为备用；名称用东方财富搜索解析），以过去四周（20 个交易日，`--weeks` 可调）为窗口计算 MA5/10/20/60、MACD、RSI、KDJ、布林带、ATR、量比、OBV、趋势斜率与 R²、最大回撤、K 线形态，给出带权重的多空信号、-100～100 评分、支撑 / 压力 / 止损 / 目标位，并画 K 线 + 成交量 + MACD + RSI 图（`outputs/<代码>-<日期>.png`，纯 Python 写 PNG）。Claire 据此写出趋势研判、情景概率和「可以买 / 等回调 / 观望 / 不建议」的结论 |
| `financial-analysis` | 财报解读（成长、盈利、偿债、现金流质量、估值、风险信号）、宏观经济与理财配置问答的方法和输出格式 |

- `allowedTools` 放行 `stock.py` 以及 `WebSearch` / `WebFetch`（查财报、新闻），无头模式下不会卡在确认上。SKILL.md 要求每次只运行脚本本身（`a || b` 这类组合命令在无头模式下会被拒绝）。
- 结论必须来自脚本或查到的真实数据，回复末尾固定附风险提示。
- 已在 Linux（WSL2）用 Claude Code 以 App 相同的参数（`-p --output-format stream-json --permission-mode acceptEdits --append-system-prompt-file … --allowedTools …`）实测：`AAPL 最近四周走势怎么样？现在能买吗？`（约 1 分钟，回复带图表）和 `帮我分析一下贵州茅台和腾讯，写一份详细报告`（中文名解析、联网查财报、输出 md 报告，约 3 分钟），均无权限拒绝。

## Melody 的作曲能力

| 技能 | 内容 |
|---|---|
| `music-composing` | `music.py`（纯标准库）调用 ComfyUI 的 MiniMax Music 3（`audio_minimax_music_3` 工作流，API 格式放在 `characters/melody/skills/music-composing/workflows/song.json`，平铺了原工作流的子图，固定用分块 VAE 解码）。Melody 先把英文编曲描述（Global Metadata / Vocal Details / Arrangement 三段）和带 `[Verse]` `[Chorus]` 等段落标签的歌词写进 `outputs/<歌名>.caption.txt` / `.lyrics.txt`，再 `music.py compose --caption-file … --lyrics-file … --duration 150 --out outputs/<歌名>.mp3`；纯音乐用 `--instrumental`（歌词只有段落标签，Vocal Details 写明 instrumental）。输出 mp3 320k（`--format flac` 无损），旁边写一个 `<歌名>.json` 记下 caption、歌词和 seed，方便复现或换 seed 重做 |

- 主人只给要求时她自己写词；给了歌词就原样使用，只加段落标签。她听不到生成的音频，所以人设和技能都要求她只说明设计（风格、结构、配器），不描述「听起来」如何。
- RTX 3090 上实测：30 秒的曲子约 75 秒（含加载模型），90 秒的纯音乐约 2 分 15 秒，130 秒的歌约 3 分 40 秒（生成时间约为曲长的 1.5–2.5 倍）。纯音乐没给歌词时脚本按时长排段落标签（约每 15 秒一段），段落太少模型容易提前收尾。脚本最多等 560 秒，超时会给出 `music.py wait <prompt_id> --out …` 继续取结果；技能里要求 Bash 超时设成 10 分钟。
- `allowedTools` 放行 `music.py`（`python` / `python3` / `py`），无头模式下不会卡在确认上。
- 已在 Linux（WSL2）用 Claude Code 以 App 相同的参数实测三种请求，均无权限拒绝：「写一首关于雨天和猫的温柔中文歌」（自己写词，130 秒，约 4 分钟）、「一分钟 lo-fi 纯音乐，不要人声」（第一版只出了 30 秒，她按技能换 seed 重做成 70 秒；之后加了按时长排段落标签）、给一段歌词谱成男声流行摇滚（歌词一字未改，自己加段落标签和 oh-oh 和声，107 秒）。
- 测试：`LR_CHAR=melody LR_PROMPT='…' cargo test --lib claude_live -- --ignored --nocapture`（在 `src-tauri/`）用和 App 完全相同的代码路径（工作目录准备、persona、`--allowedTools`、`COMFYUI_URL`）跑一次 Claude Code；`dsh_live` 同理跑 DeepSeek Harness。

## Agent harness 适配（`src-tauri/src/agent.rs`）

| | Claude Code | Codex | DeepSeek Harness |
|---|---|---|---|
| 命令 | `claude -p --output-format stream-json --verbose --include-partial-messages --permission-mode <mode> --append-system-prompt-file <workspace>/.living-room/persona.md [--model m] [--resume <sid>]` | `codex exec --json --skip-git-repo-check --sandbox workspace-write [--model m] [resume <thread>] -` | `dsh --profile headless --patch <workspace>/.living-room/dsh.patch.yml --json --permission-mode workspace-write --approval-policy never [--session-id <sid>] -` |
| 人设 | `--append-system-prompt-file` | 工作目录里的 `AGENTS.md` | patch 覆盖 `system-prompt.personaPrefix`（并关掉 `agent-instructions`，不读给 Codex 用的 `AGENTS.md`） |
| Skills | 复制到 `<workspace>/.claude/skills/`（项目级 skills） | 在 `AGENTS.md` 里列出并指向 SKILL.md | patch 把 `.claude/skills` 加到 `skill-filesystem.customSkillDirs`，原生 `skill` 工具加载 |
| 模型 | `--model` | `--model` | patch 覆盖 `agent-default-model`（`deepseek-flash` / `deepseek-v4-pro`，默认 flash） |
| 续聊 | `system/init.session_id` | `thread.started.thread_id` | `session.sessionId` |

两种输出都被解析成统一事件：`session / delta / message / tool / toolResult / done`，通过 Tauri 事件 `agent-event`、`agent-status`（`running` → `working` → `finished`，带 `worked` 标记）推给前端。Prompt 走 stdin。GUI 启动时会自动把 `~/.local/bin`、`~/.npm-global/bin` 等加入 PATH，也可在设置里手动指定 CLI 路径。

DeepSeek Harness 的说明：
- `bypassPermissions` 映射为 `danger-full-access`，其余为 `workspace-write`（沙箱内可写工作目录、可联网）；无头模式没法确认，所以固定 `--approval-policy never`，需要审批的调用直接被拒绝而不是卡住。`allowedTools` 只对 Claude Code 生效。
- `--json` 的 `text` 是整条提交的消息，不是逐 token 流，所以 DeepSeek 下回复是一段一段出现的。
- persona 里会附一段工具名对照（Read → read、WebSearch → web_search…），技能文档里的 Claude Code 工具名不用改。切换 harness 时会清空模型设置（模型名不通用）。
- 可以用 `LR_CHAR=claire LR_PROMPT='…' cargo test --lib dsh_live -- --ignored --nocapture`（在 `src-tauri/`）走和 App 相同的代码路径实测一次；`claude_live` 是 Claude Code 版。

> 已在 Linux（WSL2/WSLg）用 Claude Code 2.1.327 实测聊天、续聊、派任务写文件、使用 skill。Codex 适配按 `codex exec --json` 的事件格式实现并有单元测试，但本机未安装 codex，尚未实机验证。

## 新增角色

1. `characters/<id>/character.json`（参考 `characters/iris/character.json`）：人设 `persona`、按 harness 区分的补充说明 `harnessNotes`（可选）、`specialties`、`greeting`、`agent`（provider/model/permissionMode）、`scene`（舞台坐标 x/y/width）、`sprites`、气泡台词 `lines`。
2. `characters/<id>/skills/<skill>/SKILL.md`：角色专属 Claude Code skills。
3. 美术放到 `public/characters/<id>/`：`avatar.png`、`poses/<pose>.png`（静态，用于命中检测和加载前占位）、`anim/<pose>.json + .webp`（序列帧）。没有序列帧时只给 `image`，会退化为 CSS 呼吸/摇摆动画。

## 美术管线（`art/`）

1. **姿势变体**：ComfyUI `image_qwen_image_2_1_image_edit`（开启 prompt enhancer），以 Iris 原图为底改出 bored / working / done 三个姿势（`art/make_edit.py`，原图在 `art/src/`）。提示词要短、只描述要改的动作，长篇「保持不变」清单会让模型画成设定图。
2. **分层**：ComfyUI `seethrough-basic` 拆成 ~22 个图层（1024 画布）。
3. **修图层**：`art/tools/build_psd.py` —— 用原画颜色重新上色每层可见像素（修正缺失的瞳孔等），把没被覆盖的像素（如发带）并入邻近图层，输出 PSD。
4. **骨骼**：Rigby2D `autorig`（覆盖参数见 `art/rig/autorig_roles.json`，关 IK，手臂/道具挂躯干）→ `run_script` 跑 `art/rig/anims.py` 生成每个姿势的循环动画。工程文件在 `art/rig/*.rigby`。
5. **导出**：`export_sprite_sheet`（12fps，scale 0.6）→ `art/tools/pack_sheets.py` 按骨架原点对齐到统一画框、缩放 0.75、打包成方形 WebP 图集 + JSON，并生成首帧静态图。

Poppy 的素材在 `art/poppy/`：先用 `birefnet_remove_background` 去掉原图的暗色光晕背景并铺白底，其余步骤相同（`make_edit.py`、`run_edits.sh`、`run_st.sh`，工程在 `/mnt/e/rig_projects/poppy/`）。她坐在自己的高脚凳上：See-through 会把凳子和调色盘一起归进 objects 层，所以 `build_psd.py` 时加上 `SPLIT=prop:stool:570`，把画布 y≥570 的部分拆成单独的 `stool` 层（放在最底），autorig 时给它 `"stool": "none"`，让它挂在 root 上不跟着身体动；动画里也不移动 hip。

Poppy 的待机 / 工作 / 完成三个姿势带手部动作（调色盘上调颜料、转头对着画架挥笔、举手说话）：用 `make_edit.py` 生成新姿势（源图 `src/omalr_poppy_{mix,turn,wave}.png`，转头那张又对齐回原图的凳子位置）→ See-through → `build_psd.py` 后，用 `art/tools/split_layer.py` 把会动的小臂切成 `forearm_r` 层（放在袖子层下面，让袖口盖住关节）、把画笔切成 `brush` 层；autorig 时给 `forearm_r` 角色 `forearm`、`brush` 角色 `hand`（侧 `r`），得到肘部 `forearm_r` 和手腕 `hand_r` 骨骼；动画脚本是 `art/poppy/anims2.py`（`POSE = 'mix' | 'turn' | 'wave'`，分别导出为 reading / working / done）。这几张图 See-through 没拆出 face 层时，autorig 给 `hair_back` 角色 `head`。

Iris 的待机 / 工作 / 完成也带手部动作（看书时眼睛顺着行走、翻页；工作时握笔的手一直在写；完成时张开手掌挥手说话），动画脚本是 `art/iris/anims2.py`（`POSE = 'read' | 'write' | 'wave'`，工程在 `/mnt/e/rig_projects/iris/{reading2,working2,done2}/`，导出成 reading / working / done）：
- **翻页**：`art/iris/add_page.py` 往阅读 PSD 里画一张弯曲的纸页（`page` 层，放在书上面），autorig 给它 `hand` 角色得到一根骨骼；动画里绕书脊顶端从右翻到左，只在翻页那段显示（attachment key）。
- **写字**：`split_layer.py` 把握笔的手从 `arm_l` 切出来、把笔从 `prop`/`torso` 切出来，合成 `hand_r` 层（`KEEP=skin` 只取肤色和笔的像素，`REST=torso` 把手周围的上衣像素留给躯干，`FILL=torso` 补上手背后的上衣，`PAD=10` 让手腕在袖口下多延伸一点，移动时不露缝）。
- **挥手**：`make_edit.py` 把完成姿势的 V 字手改成张开的手掌（`src/omalr_iris_wave.png`，种子 33；提示词里写明紫色眼睛，否则会变成棕色），See-through → `build_psd.py`，再把袖口以上的手切成 `hand_r`（放在袖子层下面），整只袖子挂躯干。
- autorig 把手和纸页的骨骼放在它认为合适的地方，所以脚本里的 `pivot_rotate()` 会为每个旋转帧配一个平移帧，实现绕任意画布点（手腕、书脊）旋转。

Claire 的素材在 `art/claire/`（工程在 `/mnt/e/rig_projects/claire/<pose>/`，副本在 `art/claire/rig/`）。原图 `images/Claire.png` 本来就朝右，正好对着场景里书桌上的笔记本，坐在桌前的椅子上（`scene` x 1125 / y 128 / width 256）；顶部加了 160px 留白，给伸懒腰举起的手。
- **姿势**：`make_edit.py` 改出 bored（伸懒腰打哈欠）/ working（看平板上的 K 线，手指点划）/ done（竖大拇指）。生成的图身体位置和大小会漂，`align.py` 按腿部（坐姿里不动的部分）的轮廓 IoU 搜索缩放和平移，把它们对齐回原图画框。
- **分层与骨骼**：`make_st.py` + `run_st.sh` 跑 See-through → `build_psd.py`（reading 用透明底 `alpha`，其余用 `white`）。reading 用 `split_layer.py` 把拿报告的手和报告合成 `hand_r`（`arms,prop`，`PAD=14` 让小臂伸进袖口），`art/tools/move_layer.py` 调整图层顺序；working 把点平板的手切成 `hand_r`；bored / done 的举起的手臂本来就是单独图层，autorig 给它 `hand` 角色、侧 `r`。
- **动画**：`art/claire/anims.py`（`POSE = 'reading' | 'bored' | 'working' | 'done'`）：看报告时眼睛扫过报告、报告往自己这边倾、点头；发呆时举着的手臂摇晃、打个长哈欠；工作时手指在平板上点两下再划一下，眼睛跟着；完成时大拇指一上一下、点头微笑。`CHAR=claire pack_sheets.py` 打包（画框 `CROP (170, 0, 854, 1024)`），`preview.py` 出帧条检查。

Melody 的素材在 `art/melody/`（工程在 `/mnt/e/rig_projects/melody/<pose>/`，副本在 `art/melody/rig/`）。原图 `images/Melody.png` 是靠在什么东西上、跷着腿听耳机的姿势，正好放在客厅中间那张空着的粉色单人沙发里（`scene` x 763 / y 213 / width 289）。
- **去背景**：`workflows/rmbg.json`（BiRefNet）出遮罩 → `make_alpha.py` 收紧遮罩去掉暗色光晕，生成透明底 / 白底两版，并在顶部加 96px 留白（伸懒腰的手会举出原图画框）。
- **姿势**：`make_edit.py` 改出 bored（伸懒腰打哈欠，种子 11）/ working（睁眼低头，在五线谱本上用铅笔写，种子 33）/ done（睁开淡紫色眼睛挥手，种子 11）；原图闭着眼，提示词里要写明眼睛颜色。`align.py` 按腿部轮廓对齐回原图画框。
- **分层**：`run_st.sh` 跑 See-through → `build_layers.sh` 一步完成：`build_psd.py`（白底姿势加 `WHITE_INSIDE=1`：画面内部的白色——五线谱本、袜子——也按原画重新上色，否则会留着 See-through 猜的紫色，变成本子上的斑点），再用 `split_layer.py` 切出会动的部分：四个姿势都把跷着的那条腿的小腿 + 袜子切成 `shin_l`（放在腿层下面、`PAD=6` 伸进大腿下，绕膝盖转时不露缝），bored 切出举起的手臂、working 切出握铅笔的手（`KEEP=skin`，铅笔尾端在卫衣层里，单独补进去）、done 切出袖口以上挥动的手（`PAD=10` 伸进袖口）。
- **骨骼与动画**：autorig（关 IK；耳机 `ribbon` 给 `ear` 角色，跟着头走；手臂、本子挂躯干；腿和袜子挂 hip；`shin_l` 给 `shin`，切出来的手给 `hand` 侧 `r`）→ `art/melody/anims.py`（`POSE = 'reading' | 'bored' | 'working' | 'done'`）：听歌时闭着眼随 90 BPM 的节拍左右晃头、跷着的脚每拍点一下；发呆时举着的手臂摇晃、长长打个哈欠；工作时铅笔沿着五线谱一小段一小段地写、眼睛跟着；完成时张开手掌挥手、歪头笑。`CHAR=melody pack_sheets.py` 打包（画框 `CROP (186, 0, 838, 1024)`），`preview.py` 出帧条检查。
