---
name: reading-notes
description: 把长文、文档、网页、PDF 或一本书整理成结构化读书笔记/摘要。当主人要求「总结」「读一下」「整理笔记」「帮我看看这篇文章」时使用。
---

# 读书笔记（Iris 的做法）

1. **先通读**：完整读取材料（文件用 Read，网页用 WebFetch）。材料很长时分段读，不要只读开头。
2. **判断类型**：论述文 / 报告 / 小说 / 教程 / 新闻，选择对应重点：
   - 论述/报告：核心论点、论据、数据、结论与局限
   - 小说：人物、情节脉络、主题、印象深刻的句子
   - 教程：步骤、前提条件、易错点
3. **按下面结构写笔记**（主人只是随口一问时可以直接在回复里给简版，不必生成文件）：
   - 标题
   - 一句话概括
   - 核心要点：编号列表，每条不超过两行
   - 细节与证据：保留关键数字、人名、出处
   - 金句摘录：「……」
   - Iris 的读后感：两三句真诚的个人看法，以及可能的疑问或值得延伸阅读的方向
4. **输出为 PDF**：
   1. 复制本目录的 `template.html`（即 `.claude/skills/reading-notes/template.html`），把 `{{…}}` 占位处换成笔记内容（列表项按需增减，正文里的 `<`、`>`、`&` 要转义），保存为 `outputs/读书笔记-<标题>.html`。
   2. 运行 `python .claude/skills/reading-notes/to_pdf.py "outputs/读书笔记-<标题>.html" "outputs/读书笔记-<标题>.pdf"`（Windows 上 `python` 不可用时试 `py`，其他系统试 `python3`）。脚本会用本机的 Edge / Chrome 无头打印成 A4 PDF。
   3. 若脚本不可用，直接调用浏览器：`msedge --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="<绝对路径>.pdf" "file:///<绝对路径>.html"`（或 chrome / chromium）。
   4. 确认 PDF 已生成后删除中间的 `.html` 文件。实在无法生成 PDF 时，保留 HTML 并如实告诉主人原因。
5. 回复主人时：先给一句话结论 + 3 条以内要点，再告诉主人 PDF 文件路径（如 `outputs/读书笔记-<标题>.pdf`，写实际文件名）。
