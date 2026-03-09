# paper-digest-obsidian 中文说明

`paper-digest-obsidian` 是一个本地优先的论文阅读工程，目标是把论文检索、PDF 下载、正文提取、结构化总结和 Obsidian 落盘做成一套可维护、可扩展的 Python 项目。

它保留了 `evil-read-arxiv` 一类工作流里真正有价值的部分，但不是脚本堆砌式复刻，而是按模块重新组织：

- `paper_sources`：论文数据源
- `paper_fetcher`：元数据和 PDF 下载、缓存
- `paper_parser`：PDF 文本提取
- `summarizer`：规则总结和 LLM 总结抽象
- `obsidian_writer`：Obsidian Markdown 输出
- `services`：整体工作流编排
- `cli`：命令行入口

## 当前能力

- 按 arXiv URL / id 总结单篇论文
- 按标题搜索并总结单篇论文
- 按主题检索并生成专题索引
- 提取论文图片到 Obsidian 资源目录
- 生成每日推荐
- 扫描并链接已有 Obsidian 笔记
- 同步原始 PDF 到 vault，直接在 Obsidian 里读原文
- 可选生成“全文查看”笔记，把 PDF 和解析出的正文一起写进 vault

## 安装

### 方式一：`uv`

```bash
uv sync --extra dev
```

### 方式二：`venv + pip`

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .[dev]
```

## 基础配置

先复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

然后修改 `.env`：

```env
OBSIDIAN_VAULT_PATH=F:/你的Obsidian仓库
LITERATURE_DIR_NAME=文献库
PAPERS_DIR_NAME=论文笔记
FULL_TEXT_DIR_NAME=论文全文
PDF_DIR_NAME=原文PDF
ASSETS_DIR_NAME=图片素材
SUMMARY_BACKEND=heuristic
SUMMARY_AUDIENCE=beginner
SUMMARY_DETAIL_LEVEL=detailed
```

检查配置是否正常：

```powershell
.\.venv\Scripts\paper-digest.exe doctor
```

## 常用命令

### 1. 总结单篇论文

按 arXiv URL：

```powershell
.\.venv\Scripts\summarize-paper.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

按标题：

```powershell
.\.venv\Scripts\summarize-paper.exe --title "Attention Is All You Need" --topic transformer
```

### 2. 生成专题索引

```powershell
.\.venv\Scripts\summarize-topic.exe "retrieval augmented generation" --limit 10 --topic rag
```

### 3. 直接阅读完整论文原文

```powershell
.\.venv\Scripts\view-paper.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

这个命令不会生成笔记，而是直接把原始 PDF 同步到：

```text
文献库/<topic>/原文PDF/<paper-slug>.pdf
```

你在 Obsidian 左侧文件树里直接点开这个 PDF，就是真正的原论文阅读。

### 4. 生成辅助用的全文查看笔记

```powershell
.\.venv\Scripts\view-paper-note.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

这个命令会做三件事：

1. 下载并缓存 PDF
2. 把 PDF 同步到你的 Obsidian `图片素材/<paper-slug>/` 目录
3. 生成一篇 `论文全文/<paper-slug>.md`，其中包含：
   - 专题入口
   - 摘要笔记入口
   - Obsidian 内嵌 PDF
   - 提取到的摘要
   - 提取到的章节正文
   - 参考文献摘录
   - 提取警告

如果 PDF 解析不完整，全文笔记里会明确保留警告，并仍然提供 PDF 原文入口。

### 5. 提取图片

```powershell
.\.venv\Scripts\extract-images.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

### 6. 每日推荐

```powershell
.\.venv\Scripts\recommend-daily.exe --top-n 10 --analyze-top-n 3
```

### 7. 搜索已有笔记

```powershell
.\.venv\Scripts\search-notes.exe "vector database"
```

## Obsidian 输出目录

默认输出结构：

```text
<vault>/
  文献库/
    <topic-slug>/
      index.md
      论文笔记/
        <paper-slug>.md
      原文PDF/
        <paper-slug>.pdf
      论文全文/
        <paper-slug>.md
      图片素材/
        <paper-slug>/
          <paper-slug>.pdf
          <image files...>
```

说明：

- `论文笔记/`：适合快速理解的摘要版笔记
- `原文PDF/`：适合直接阅读完整原论文
- `论文全文/`：适合完整阅读和查原文的全文版笔记
- `图片素材/`：PDF 副本和抽取的图片资源

## LLM 总结模式

默认是规则总结，不依赖外部模型。

如果你想接入 OpenAI 兼容接口：

```env
SUMMARY_BACKEND=openai-compatible
SUMMARY_AUDIENCE=beginner
SUMMARY_DETAIL_LEVEL=detailed
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=你的_KEY
LLM_MODEL=gpt-5.2
```

设计原则：

- 先跑规则总结，保证没有模型也能工作
- 再用 LLM 覆盖关键字段
- LLM 失败时自动退回规则总结，不让整条流程崩溃

## 开发与测试

```powershell
.\.venv\Scripts\python -m black --check src tests
.\.venv\Scripts\python -m ruff check src tests
.\.venv\Scripts\pytest -q --basetemp=test-output\pytest_tmp_run --override-ini cache_dir=test-output\pytest_cache_run
.\.venv\Scripts\python -m build
```

## 适合后续扩展的方向

- 接入更完整的 Semantic Scholar / OpenAlex 多源检索
- 为 Obsidian 增加概念页、数据集页和谱系图入口
- 增强表格和图片说明抽取
- 为总结结果增加更严格的 JSON schema 校验
