# CLAUDE.md — 改动检查表

这个文件是给 Claude 看的：每次改完程序，先在下表找到对应行，把“必须同步”的
文件全部检查一遍，再提交。不要只改代码就结束。

## 每次改动都做

```bat
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pyright
git status --short
```

- 用户可见文案改动：`src/mediafilter/i18n/locales/zh.json` 和 `en.json` 必须同时改。
- 提交信息不要加 `Co-Authored-By` / `Generated with`。
- 不要为了追新数字去改历史发布说明（`docs/releases/v0.1.1.md`、`v0.2.0.md`）；
  新版本另建 `docs/releases/vX.Y.Z.md`。
- `docs/index.html` 和 README 的下载链接用 `releases/latest`，通常不需要改版本号。

## 改动类型 → 必须同步

| 你改了什么 | 必须检查/更新 | 顺手检查 | 验证 |
|---|---|---|---|
| 界面、交互、功能行为 | `README.md` 功能列表 + How to use；`使用文档.md` 对应章节；`docs/index.html` 首屏/功能卡/规格行/meta+og；`docs/screenshots/*.png` + `demo.gif` | `packaging/build.py` 的 `readme_text()`；`CHANGELOG.md`；新版本 `docs/releases/vX.Y.Z.md` | 截图/GIF 脚本；`tools/build_doc_pdf.py` |
| 新增/删除内置标签 | `core/vocabulary.py`；`core/tagger.py`；`tests/test_vocabulary.py`；`tests/test_tagger.py`；README 的“本地 8 类 / 云端 26 类”（中英）；`docs/index.html` 标签卡；`使用文档.md` 标签章节；i18n `tag.*` | `.interface-design/settings.md`（本地设计文档，git 忽略） | pytest；手动看本地/云端标签边界 |
| 更换本地模型 | `.github/workflows/release.yml` 的 `MODEL_URL` / `MODEL_SHA256`；`THIRD_PARTY_NOTICES.md`；README 模型说明；`packaging/build.py` 的模型说明；新版本发布说明 | `docs/index.html` 的 8/26 文案；`使用文档.md` 本地识别章节 | 用真实视频跑一轮本地识别 |
| 批量处理/编码器/容器 | `core/batch.py`；`core/batch_exec.py`；`tests/test_batch.py`；`tests/test_batch_exec.py`；README 编码器表和批量处理章节；`docs/index.html` Batch 卡片；`使用文档.md` 批量处理 + 故障排查 | `packaging/build.py` 功能列表 | pytest；真实 FFmpeg 跑一次输出 |
| 更换 FFmpeg 构建 | `.github/workflows/release.yml` 的 `FFMPEG_URL` / `FFMPEG_SHA256`；`THIRD_PARTY_NOTICES.md`；`packaging/README.md`；README 环境要求 | `docs/index.html` 平台/许可文案；`使用说明.txt` | 校验 SHA-256；打一次 zip 看内容 |
| 依赖、extras、许可证 | `pyproject.toml`；`THIRD_PARTY_NOTICES.md`；`packaging/build.py` 的复制清单和 `readme_text()`；`packaging/README.md`；README 安装/许可段；`docs/index.html` 底部许可/体积 | `docs/releases/vX.Y.Z.md` | `pip install -e ".[dev,ai]"`；打包 dry run |
| 便携包内容变化 | `packaging/build.py` 的 `assemble()` 复制清单；`packaging/build.py` 的 `readme_text()`；README 的 `MediaFilter-<version>-win64.zip` 内容表；`packaging/README.md` | `使用说明.txt` | `packaging/build.py --skip-build --no-zip` 后检查目录 |
| 平台/启动方式/CLI | README 环境要求 + 安装 + 使用；`使用文档.md` 环境要求；`docs/index.html` hero/spec；`packaging/build.py` 的 `readme_text()` | `core/secret_store.py`（DPAPI 平台限制）；`packaging/README.md` | 在目标平台启动一次 |
| 发版 | `pyproject.toml` 的 `version`；`packaging/version_info.txt`（FileVersion / ProductVersion / filevers / prodvers）；`CHANGELOG.md` 新段；`docs/releases/vX.Y.Z.md`；`packaging/scoop/media-filter.json`（version/url/extract_dir）；winget 清单（`scripts/winget_submit.py`）；`git tag vX.Y.Z` | README/使用文档测试数量；`docs/index.html` 的 `~168 MB ZIP` | CI release dry run；release notes 生成 |
| 测试数量变化 | README 3 行 4 处：`198 pytest cases` / `共 198 个用例` / `198 pytest cases`（英文 2 处、中文 2 处）；`使用文档.md` 2 处：`pytest 用例（198 个）` 和 `当前 198 个用例` | 不要改历史 `docs/releases/v0.1.1.md`（128）和 `v0.2.0.md`（196） | `rg -n "\\b196\\b|\\b197\\b|\\b198\\b" README.md 使用文档.md docs/releases` |
| 截图/GIF 变化 | `docs/screenshots/main-light.png`、`main-dark.png`、`batch.png`、`settings.png`、`demo.gif`；README 图片链接/alt/说明；`docs/index.html` gallery/alt | README 的 `14 demo files` / `11 tagged`；`docs/index.html` 的 `14 demo files` 文案 | `capture_screenshots.py`、`capture_gif.py` |
| 删除功能 | 全仓库搜功能名：`rg -n "旧功能名" README.md 使用文档.md docs packaging src tests`；清理 README/官网/使用文档/截图/i18n/测试 | 历史 release notes 只保留历史，不删 | pytest；截图脚本 |

## 固定的“漂移点”

改完用这条命令扫一遍：

```bat
rg -n "\b196\b|\b197\b|\b198\b|168 MB|14 demo|8 of the 26|26 个|0\.2\.0" README.md 使用文档.md docs/index.html packaging/scoop packaging/README.md .github/workflows/release.yml
```

当前基准：

- README：`198` 出现 3 处（英文 2 + 中文 1）。
- `使用文档.md`：`198` 出现 2 处。
- `docs/releases/v0.2.0.md`：`196` 是历史发布说明，**不要改**。
- `docs/index.html`：`~168 MB ZIP`；0.2.0 实际 zip 为 176,284,923 字节（约 168 MiB）。
- 截图说明：`14 demo files` / `11 tagged` / `0 failures`，换演示素材后一起改。

## 文档与截图命令

```bat
# 截图（需要演示素材目录和 models\yolov8n_fp32.onnx）
.venv\Scripts\python.exe scripts\capture_screenshots.py <演示素材目录> docs\screenshots
.venv\Scripts\python.exe scripts\capture_gif.py <演示素材目录> docs\screenshots\demo.gif

# 使用文档 PDF
.venv\Scripts\python.exe tools\build_doc_pdf.py

# 便携包内容检查（需要 dist\MediaFilter.exe）
.venv\Scripts\python.exe packaging\build.py --skip-build --no-zip
```

便携包目录必须包含：

```text
MediaFilter.exe
ffmpeg\bin\
LICENSE
THIRD_PARTY_NOTICES.md
使用说明.txt
```

## i18n 检查

没有独立脚本时，用这段确认中英 key 一致：

```bat
.venv\Scripts\python.exe -c "import json; a=json.load(open('src/mediafilter/i18n/locales/zh.json',encoding='utf-8')); b=json.load(open('src/mediafilter/i18n/locales/en.json',encoding='utf-8')); print('zh-only', sorted(set(a)-set(b))); print('en-only', sorted(set(b)-set(a)))"
```

两边都应为空。

## 不要动

- `docs/releases/v0.1.1.md`、`docs/releases/v0.2.0.md`：历史发布说明。
- `.interface-design/`、`_inspect/`、`build/`、`dist/`、`release/`、`使用文档.pdf`、`models/*.onnx`：本地/生成产物，按需重建。
- 提交和 PR 不加 Claude 署名。

新增文档面、发布步骤或打包产物时，把新面补进本表，别让检查表自己过期。