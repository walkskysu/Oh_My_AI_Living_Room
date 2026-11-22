---
name: music-composing
description: 作曲：根据主人的要求（风格、心情、场景、主题）或主人给的歌词，写歌词、写编曲描述，并用本地 ComfyUI 的 MiniMax Music 3 生成完整歌曲；也能做没有人声的纯音乐 / BGM。当主人说「写一首歌」「帮我作曲」「把这段歌词唱出来」「做一段纯音乐 / 背景音乐 / BGM」「来首 lo-fi」时使用。
---

# 作曲（Melody 的做法）

先看系统提示 / AGENTS.md 里「作曲工具」一节，确认你现在运行在哪个 harness 上。
**Claude Code** 和 **DeepSeek Harness** 都用本目录的 `music.py` 调本地 ComfyUI（MiniMax Music 3）。**Codex** 也调用同一个 `music.py`（Codex 没有内建作曲功能）；如果 Codex 的沙箱不让连 ComfyUI（报连接被拒/网络不可用），如实告诉主人可以在「关于她」里把 harness 换成 Claude Code。

交付的歌曲、歌词都放在 `outputs/`，主人给的歌词文件通常在 `inputs/`。

## 流程

1. **理解需求**：风格/流派、情绪和起伏、场景（学习、开车、睡前、生日…）、人声（男声/女声/合唱/不要人声）、语言、长度。主人没说的你自己做合理的音乐决定，做完再说明，不要连环提问。
   - 主人只给了要求 → 你来写歌词。
   - 主人给了歌词 → **原样使用主人的歌词**，只加段落标签；明显需要时（太短、没有副歌）可以建议补写，但先按原词做。
   - 主人说「纯音乐」「BGM」「不要人声」「伴奏」 → 用 `--instrumental`。
2. **写两个文件**（用 Write 工具，文件名用歌名）：
   - `outputs/<歌名>.caption.txt`：编曲描述（英文，写法见下文）。
   - `outputs/<歌名>.lyrics.txt`：带段落标签的歌词（纯音乐可省略，或只写标签）。
3. **生成**（见下面的命令）。脚本最后一行输出 JSON，里面有 `file`（音频）、`seconds`（实际时长）、`seed`。
4. **检查**：`ok` 是否为 true；`seconds` 是否大致合理（明显比要求短很多，比如要 2 分钟只出了 20 秒，就换个 seed 重做一次）。你听不到声音，所以不要描述「听起来」怎么样，只说你是怎么设计的。
5. **汇报**：一两句角色口吻的话 + 用反引号写出音频路径（例如 `outputs/晴天的猫.mp3`，聊天窗口会直接出现播放器）+ 歌名、风格、时长、seed；有歌词就把歌词贴出来（去掉标签也行）。告诉主人不满意可以「换个 seed 再来一版」或者说哪里想改。

## 命令

脚本：`python .claude/skills/music-composing/music.py <命令> ...`（Windows 上 `python` 不可用时试 `py`，其他系统试 `python3`）。只用标准库，ComfyUI 地址取自环境变量 `COMFYUI_URL`。
命令要原样以 `python .claude/skills/music-composing/music.py`/`python3 ...`/`py ...` 开头，用相对路径，**不要**加 `cd`、`echo` 或 `&&`、`||` 组合，否则不在免确认名单里会被拦下。

先确认连得上（每段对话第一次作曲前跑一次即可）：

```bash
python .claude/skills/music-composing/music.py check
```

`minimax_music3_nodes` 为 false 说明 ComfyUI 上没有 MiniMax Music 3 节点，如实告诉主人。

### 歌曲

```bash
python .claude/skills/music-composing/music.py compose --caption-file "outputs/<歌名>.caption.txt" --lyrics-file "outputs/<歌名>.lyrics.txt" --duration 150 --out "outputs/<歌名>.mp3"
```

### 纯音乐

```bash
python .claude/skills/music-composing/music.py compose --caption-file "outputs/<曲名>.caption.txt" --instrumental --duration 120 --out "outputs/<曲名>.mp3"
```

纯音乐不给 `--lyrics-file` 时，脚本按时长自动排段落标签（`[Intro]`、若干 `[Instrumental]` / `[Solo]`、`[Outro]`，大约每 15 秒一段；段落太少模型容易提前收尾）。想要别的结构就写一个只有标签、没有句子的歌词文件一起传，同样按每段约 15 秒来估。

### 参数与耗时

- `--duration`：最长秒数（10–300），模型可能提前收尾。默认 120。主人没说长度时：歌曲 120–180，BGM 60–120，铃声/片头 20–40。
- `--seed N`：复现同一版；换 seed = 换一版。`--format flac` 无损（默认 mp3 320k）。
- 生成大约要歌曲时长的 1.5–3 倍时间（2 分钟的歌约 3–5 分钟）。**调用 Bash 时一定把超时设到 600000（10 分钟；DeepSeek Harness 的 bash 参数是 `timeoutMs`）。** 脚本默认最多等 560 秒；如果超时，输出里会给出 prompt_id，运行：
  ```bash
  python .claude/skills/music-composing/music.py wait <prompt_id> --out "outputs/<歌名>.mp3"
  ```
  继续等待并取回结果（可以重复运行直到拿到）。
- 每首歌旁边会自动写一个 `outputs/<歌名>.json`，记着 caption、歌词和 seed。

## 编曲描述（caption）怎么写

**用英文写**（即使歌词是中文），分三段，每段以标题开头，共约 150–350 词。具体、有音乐性，少堆砌形容词：

```
Global Metadata: <流派与子流派>. <速度：约 xx BPM 或 slow / mid-tempo / fast>. <调性，可省略>. <整首的情绪走向：开头→中段→结尾>. <使用场景与画面>. <制作质感：混音、空间、年代感>.

Vocal Details: <主唱性别、音色、音域、唱法>; <和声/伴唱>; <克制的人声效果>. <如果是中文歌："Sung in Mandarin Chinese.">

Arrangement: <主要乐器与律动>. Intro: <…>. Verse: <…>. Chorus: <…>. Bridge: <…>. Outro: <…>.
```

- 纯音乐：Vocal Details 写 `Instrumental, no vocals. The <乐器> carries the lead melody.`，并且整段 caption 不要出现 singer / vocal harmony 之类会引出人声的词。
- Arrangement 按你歌词里的段落顺序写，说清每段乐器怎么进、怎么变、怎么退，能量怎么起伏。
- 不要把歌词、歌名写进 caption；不确定的就别编精确数字（BPM、调性给范围或省略即可）。
- 不要模仿或点名在世的真实歌手（写 `a warm female pop voice`，不写某某歌手的名字）。

## 歌词怎么写

- 每段以标签开头，标签单独一行：`[Intro]` `[Verse]` `[Pre-Chorus]` `[Chorus]` `[Post-Chorus]` `[Bridge]` `[Instrumental]` `[Solo]` `[Outro]`。标签是模型唯一会执行的结构指令。
- 中文歌词直接写中文；每行一句，一句别太长（7–14 个字比较好唱），主歌和副歌的字数节奏尽量整齐，副歌要有记忆点并重复。
- 伴唱/和声习惯写在括号里，例如 `(oh-oh)`、`(take your time)`；纯语气词可以写 `Mmm…` `Ooh…`。
- 结构参考（约 2–3 分钟）：`[Intro]` → `[Verse]` → `[Pre-Chorus]` → `[Chorus]` → `[Verse]` → `[Chorus]` → `[Bridge]` → `[Chorus]` → `[Outro]`。时长短就少写几段：歌词越多，需要的时长越长；歌词太长而 `--duration` 太短，歌会被截断。
- `[Instrumental]` / `[Solo]` 段下面不写字，用来放间奏、乐器独奏。

## 示例（只示范格式，不要照搬里面的句子和配器）

`outputs/夏夜单车.caption.txt`：

```
Global Metadata: Upbeat indie pop with a city-pop shimmer, around 112 BPM. Breezy and carefree in the verses, lifting into a bright, open chorus, ending with a warm, wistful fade. Riding a bike through a summer night, streetlights and cicadas, warm wind. Clean, punchy modern mix with a little retro 80s sparkle.

Vocal Details: Sung in Mandarin Chinese. A bright, youthful female voice, light and rhythmic in the verses, fuller and soaring in the chorus. Stacked harmonies and a few "oh-oh" backing vocals in the final chorus.

Arrangement: Intro: chorus-drenched clean electric guitar riff over a soft synth pad. Verse: tight drums with a crisp snare, bouncy fingered bass, muted guitar chops. Pre-Chorus: the drums build with open hi-hats, a synth arpeggio rises. Chorus: full band, bright synth lead answering the vocal, wide guitars. Bridge: half-time feel, just bass, pad and voice, then a drum fill back in. Final Chorus: everything plus handclaps and harmonies. Outro: the intro riff returns and fades with distant cicadas.
```

`outputs/夏夜单车.lyrics.txt`：

```
[Intro]

[Verse]
晚风吹乱了刘海
单车铃声叮当响
...

[Chorus]
...

[Instrumental]

[Outro]
```

## 常见问题

- `连不上 ComfyUI`：告诉主人确认 ComfyUI 已启动，并在「客厅设置 → ComfyUI」检查地址。不要改用其他方式出歌。
- `HTTP 400` / 工作流校验失败：多半是 ComfyUI 上缺少 MiniMax Music 3 的模型（`minimax_music3_dit_fp16`、`minimax_music3_text_encoder_pruned_int8_convrot`、`minimax_music3_dav`）或节点，把错误原文转告主人。
- 显存不足（OOM）：缩短 `--duration` 再试。
