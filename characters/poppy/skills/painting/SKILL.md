---
name: painting
description: 画图（文生图）、改图（换背景/换装/改风格/加减元素/修细节）、拆图层，以及反推提示词时的图片识别辅助。当主人说「画一张」「生成图片」「帮我改图」「把背景换成」「换成 xx 风格」「拆图层」「分层」时使用。
---

# 画图与改图（Poppy 的做法）

先看系统提示 / AGENTS.md 里「画图工具」一节，确认你现在运行在哪个 harness 上（不需要另外执行命令去查）：

- **Claude Code** 或 **DeepSeek Harness** → 用本目录的 `comfy.py` 调本地 ComfyUI（下文 A 部分）。
- **Codex** → 用 Codex 内建的图片生成/编辑功能（下文 B 部分），不要调用 comfy.py。

无论哪种方式，交付的图片都放在 `outputs/`，主人给的图片通常在 `inputs/`。

## 通用流程

1. **理解需求**：主体、风格/媒介、构图与画幅、色调、氛围、必须保留/避免的东西。需求模糊时自己做合理的审美决定，画完再说明，不要连环提问。
2. **写提示词**（英文为主，中文也可）：
   - 文生图：一段连贯的自然语言描述，按「主体与动作 → 关键视觉锚点 → 构图/镜头/视角 → 光线 → 配色 → 材质与细节 → 背景与空间层次 → 媒介与画风」的顺序，把最重要的放在前面。需要画面里出现文字时，把文字放在英文双引号里。
   - 改图：**只描述要改的地方**，一两句话、明确具体（例如 `Replace the background with a cherry-blossom park on a sunny afternoon`）。不要写一长串「保持不变」清单，那会让模型画成设定图；需要强调保留时，最多加一句 `Keep the character and pose unchanged.`
3. **生成** → **检查**：生成后用 Read 打开图片亲自看一眼（主体对不对、手和脸有没有崩、有没有多余文字/水印）。明显失败就调整提示词或换个 seed 重画一次，最多重试 2 次。
4. **汇报**：一两句话 + 用反引号写出图片路径（例如 `outputs/橘猫晒太阳.png`，聊天窗口会直接显示缩略图）+ 最终提示词 + seed（方便复现）。

## A. Claude Code / DeepSeek Harness：通过 ComfyUI

脚本：`python .claude/skills/painting/comfy.py <命令> ...`（Windows 上 `python` 不可用时试 `py`，其他系统试 `python3`）。只用标准库，ComfyUI 地址取自环境变量 `COMFYUI_URL`。

**这些命令要跑 1–5 分钟，调用 Bash 时一定要把超时设到 600000（10 分钟；DeepSeek Harness 的 bash 参数是 `timeoutMs`）。** 脚本最后一行输出一个 JSON：`{"ok": true, "files": [...], "seed": ...}` 或 `{"ok": false, "error": "..."}`。如果 Bash 超时而任务还在跑，用 `comfy.py wait <prompt_id> --out <同一个路径>` 继续取结果（prompt_id 在 stderr 的「已提交」那行里）。

先确认连得上（每段对话第一次画图前跑一次即可；命令要原样以 `python .claude/skills/painting/comfy.py`/`python3 ...`/`py ...` 开头，用相对路径，不要加 `cd`、`echo` 或 `&&` 前缀，否则不在免确认名单里会被拦下）：

```bash
python .claude/skills/painting/comfy.py check
```

### 文生图 `t2i`（Qwen-Image 2.1）

```bash
python .claude/skills/painting/comfy.py t2i --prompt "<prompt>" --aspect 3:4 --out "outputs/<名字>.png"
```

- `--aspect`：`1:1`（默认）`2:3` `3:2` `3:4` `4:3` `9:16` `16:9` `21:9`；`--mp` 总像素（百万），默认 1.0，海报/壁纸可用 2.0，最高 4.0（越大越慢）。
- `--negative "<...>"` 负面提示词；`--count 2` 一次出几张（最多 4）；`--seed N` 复现。
- `--enhance`：主人只给了很短的一句话、你也不打算细化时，可让 Qwen 提示词增强器扩写；你已经写了详细提示词时不要开。

### 改图 `edit`（Qwen-Image 2.1 Edit）

```bash
python .claude/skills/painting/comfy.py edit --image "inputs/<原图>" --prompt "<要改什么>" --out "outputs/<名字>.png"
```

- `--image2 "<第二张图>"`：参考图，例如「把图 1 人物的衣服换成图 2 的衣服」——提示词里用 image 1 / image 2 指代。
- 默认开启编辑提示词增强器（效果更稳）；你的提示词已经非常精确时可加 `--no-enhance`。
- 输出默认保持原图尺寸（超过约 240 万像素会自动缩到 1536 级别）；`--resolution 1024` 可以更快。
- 多步修改（先换背景再换衣服）就把上一步的输出当下一步的 `--image`，比一句话塞很多改动更可控。

### 拆图层 `layers`（See-through）

```bash
python .claude/skills/painting/comfy.py layers --image "inputs/<角色图>" --out-dir "outputs/<名字>-图层"
```

适合单个动漫/插画角色（白底或透明底最好），耗时 2–5 分钟。输出目录里：

- `01_xxx.png`、`02_xxx.png`…：按从后到前排序的图层（头发、脸、眼睛、衣服、手臂…），是**裁剪过的**小图，位置偏移记录在 `layers.json`。
- 如果本机 Python 装了 Pillow：还会有 `full/`（与画布同尺寸、可直接叠放的图层）和 `composite.png`（合成预览）；再装了 psd-tools 就会多一个 `layers.psd`。脚本输出的 JSON 会列出实际生成了哪些。

汇报时说明图层数量，用反引号写出 `composite.png`（有的话）和 `layers.psd`（有的话）或输出目录的路径。

### 图片识别 `describe`（Qwen3-VL，给反推提示词当参考）

```bash
python .claude/skills/painting/comfy.py describe --image "inputs/<图>" --mode ultra
```

`--mode`：`tags` `simple` `detailed` `ultra`（默认）`cinematic` `analysis`；`--ask "<问题>"` 自定义提问。你自己能直接看图（用 Read 打开图片），所以这只是第二意见：反推提示词时可以先跑一次，再结合你亲眼看到的内容，按 image-prompt-reverse 技能输出。

### 常见问题

- `连不上 ComfyUI`：告诉主人确认 ComfyUI 已启动，并在「客厅设置 → ComfyUI」检查地址。不要改用其他方式出图。
- `HTTP 400` / 工作流校验失败：多半是 ComfyUI 上缺少模型或节点，把错误原文转告主人。
- 显存不足（OOM）：降低 `--mp` / `--resolution`，或一次只生成一张。

## B. Codex：内建画图功能

- 用 Codex 内建的图片生成工具（image generation）出图；改图时把 `inputs/` 里的原图作为输入图片交给它。
- 提示词写法同上「通用流程」。
- 生成的图片如果不在工作目录里，把它复制到 `outputs/<有意义的名字>.png`，再用反引号写出这个路径汇报。
- 如果内建画图功能不可用（例如被关闭），如实告诉主人，并建议在「关于她」里把 harness 切换到 Claude Code（会改用 ComfyUI）。
- 拆图层依赖 ComfyUI，Codex 下不提供。
