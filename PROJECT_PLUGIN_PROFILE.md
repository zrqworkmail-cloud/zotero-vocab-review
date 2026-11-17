# 项目插件档案：zotero_global_capture

本文件只记录**这个项目**的事实：宿主版本、路径、命令、基线、例外和当前状态。  
通用流程不写在这里，见 `plugin-development` skill（`C:\Users\Admin\.sclaw\agent\skills\plugin-development\SKILL.md`）。

> 规则：改代码时如果改变了路径、命令、基线或部署方式，同一个改动里更新本文件；不要把本项目路径写回通用 skill。

## 1. 身份

| 项 | 值 |
|---|---|
| 项目 | Anki 全局划词入卡 / 单词随身复习插件 |
| 仓库 | `D:\Users\Admin\Documents\ChatGPT\Tools\zotero-vocab-review-branch` |
| 分支 | `feat/review-acceptance` |
| 当前 HEAD | `9395704 Divide long words by real syllables, and stop the post-rating stall` |
| 宿主 | Anki 26.9.3，`D:\Program Files (x86)\Anki\Anki.exe` |
| 插件安装目录 | `C:\Users\Admin\AppData\Roaming\Anki2\addons21\zotero_global_capture` |
| 用户 profile | 「账户 1」；词书 `cet6_full`（六级全表） |
| 宿主 API | AnkiConnect v6，`http://127.0.0.1:8765` |
| 运行日志 | `%TEMP%\zotero_global_capture_runtime.log` |
| 最后更新 | 2026-11-17 |

## 2. 命令

| 用途 | 命令 | 证据 |
|---|---|---|
| 单元测试 | `python -m unittest discover -s tests -p "test_*.py"` | `Ran 467 tests ... OK`（2026-11-17） |
| Node 测试 | `node --test tests/plugin.test.cjs` | `pass/fail` 汇总 |
| 离屏 Qt | `python tests/run-windows-checks.py` | 最后一行汇总 |
| 回滚快照 + 计数基线 | `python tools/pre-deploy-check.py --apply` | JSON：`backup`、`manifest_sha256`、`baseline_counts` |
| 部署前门禁 | `python tools/pre-deploy-check.py --check` | 必须 `ok: true`、`EXIT=0` |
| 重启宿主 | `python tools/restart-anki.py --wait 300` | `closed politely in N s`；前后计数 unchanged |
| 五层状态 | `python tools/verify-state.py` | source / deployed / loaded / config / on-screen |
| 性能探针 | `python tools/probe-prepare-question.py --runs 12 --warm-captures` | p50/p90、round trips、actions |
| 回滚 | 见 §7 | 恢复后 `verify-state` + 计数一致 |

## 3. 部署顺序（固定）

1. `python tools/pre-deploy-check.py --apply` —— 生成完整回滚快照，记录当前计数基线；只写 `deployment-backups/`，不动安装目录。
2. `python tools/pre-deploy-check.py --check` —— 必须 `EXIT=0`；备份不完整、未加载、计数不可读都不部署。
3. 拷贝本轮变更到安装目录；只拷变更，保留 `config.json` / `meta.json` / 词库。
4. `python tools/restart-anki.py --wait 300` —— 托盘退出协议；看到 `closed politely in N s`，不要强杀。
5. `python tools/verify-state.py` —— 五层；手动核 `lexicon/syllables_supplement.txt` 哈希；确认重启前后计数 unchanged。
6. 复跑 `python tools/pre-deploy-check.py --check` —— `counts.changed` 为空才算计数未变。

本轮（#65 + #66）需要部署的文件：`morphology.py`、`review_logic.py`、`review_popup.py`、`lexicon/syllables_supplement.txt`。`kyle_enrich.py` 永远不部署。

## 4. 数据与基线

2026-11-12 11:37 快照（`--apply` 时写入 manifest）：

| 指标 | 值 |
|---|---:|
| book cards | 5211 |
| book learned | 1117 |
| mastered | 284 |
| total notes | 6886 |
| fingerprint | `fc57d23d07fba5da` |

- 计数是用户学习进度，会随正常复习变化；只用于**同一次部署前后**对比，不把旧快照当永久真值。
- 回滚快照：`deployment-backups/pre-deploy-20261112-113708/`，manifest `de66d3d32c7951ba`，39 个文件，覆盖 37/37 个安装文件。
- 不直接读写 `collection.anki2`；运行中用 AnkiConnect 读，避免 WAL 旧视图。
- 不伪造 FSRS/复习记录，不覆盖用户学习历史；写入前先备份，一次只做一个破坏性动作。

## 5. 性能预算

| 指标 | 预算 | 说明 |
|---|---|---|
| `prepare_question` p50 | ≤ 800 ms | 同一合集、warm captures、12 次 |
| `prepare_question` p90 | ≤ 1200 ms | 同上 |
| round trips | ≤ 8 | probe 计数 |
| 冷启动第一张 | ≤ 1.5 s | 清缓存后 |
| 主线程阻塞 | 无 > 300 ms | 日志 + 手动观察 |

最近一次记录：p50 约 763 ms、6–7 次往返；冷启动第一张约 1483 ms / 8 次往返。改动后必须用同一 probe 复测并保留 before/after。

## 6. 兼容与例外

- 宿主：Anki 26.9.3；升级 Anki 后先跑启动自检 + `restart-anki.py` + `verify-state.py`。
- 发布 manifest：`human_version=0.4.0-beta.10`，`min_point_version=260903`，`max_point_version=-260903`。Anki 用 `YYMMPP` 整数表示版本（26.9.3 → `260903`）；负的 max 是硬上限，当前只声明已验证的 26.9.3，未测试的版本不冒充兼容。
- 发布包排除 `kyle_enrich.py`（版权未定）和 `kyle_books.py`（只被前者使用）；`tests/test_anki_installer.py` 会同时断言两个归档都不含这两个文件。
- `kyle_enrich.py`：只在源码里，真题合规未定，**不部署**；`verify-state` 会报 ABSENT，这是预期。
- `kyle_books.py`：只被 `kyle_enrich.py` 使用，和前者一起归入 `pre-deploy-check.py` 的 `INTENTIONALLY_ABSENT`，即使安装目录仍有旧副本也不参与部署比对。`--apply` 的 `manifest.json` 会记录 `new_files`（本次新增、旧备份不可能包含的模块）；`--check` 不再把这些文件误报为备份缺失，回滚步骤会先删除它们。
- `verify-state.py` 的 deployed 层只哈希顶层 `*.py`，**不查 `lexicon/`**；部署后必须手动比对 `lexicon/syllables_supplement.txt` 哈希，否则会假绿。
- 退出方式：这台机器装有 Minimize to Tray 2，点 X/WM_CLOSE 只会收进托盘；`restart-anki.py` 用 `%TEMP%\zvr-quit-request` 让插件按 `mw.closeEventFromAction=True; mw.close()` 真退出。看到 `closed politely in N s` 才算成功。
- 卡片在屏时不要强杀；`restart-anki.py` 只有在没有卡片窗口时才允许升级关闭。

### 26.9.3 兼容验证（2026-11-13）

- 宿主与隔离：`Anki.exe` 文件/产品版本均为 `26.9.3`；干净 base 为 `...\workspace\anki-compat-26.9.3\base`，profile `User 1`，`ANKI_SINGLE_INSTANCE_KEY=anki-compat-260903`。启动时提示 `26.09.4` 更新，选择 **No**，未升级。
- 安装入口：`Tools → Add-ons → Install from file...`，安装 `...\anki-global-addon\dist\zotero_global_capture.ankiaddon`；Add-ons 列表出现“单词随身复习与全局划词”。
- `meta.json` 回读（`addons21\zotero_global_capture\meta.json`）：

| 字段 | 回读值 | 判定 |
|---|---|---|
| `human_version` | `0.4.0-beta.10` | 与包一致 |
| `min_point_version` | `260903` | 等于 26.9.3 |
| `max_point_version` | `-260903` | 硬上限，仅 26.9.3 |
| `disabled` | `false` | 已启用 |

- 加载证据：重启干净实例后，顶部工具栏新增“开始学习 · 未选词书”（`zvr-desktop-review`）；安装前无此入口，且启动无“不兼容/加载失败”对话框，证明 Anki 不仅解包，还实际执行了插件入口。
- 包内容回读：归档共 **39 个文件条目**；安装后 **40 个文件 = 39 个包内文件 + Anki 运行时生成的 `meta.json`**。其余 39 项逐项比对 SHA256 与大小全部一致，无缺失、无额外文件；`__init__.py`、`manifest.json` 存在，`kyle_enrich.py` 与 `kyle_books.py` 均不存在。
- 收尾：干净实例用 `File → Exit` 退出；活动实例未参与安装、未写入。
- 结论：**26.9.3 兼容边界成立**。`min=max` 当前仍只覆盖 `260903`；未实测版本不声明兼容。

## 7. 回滚

1. 停止 Anki（托盘协议；有卡片在屏时不动）。
2. 整目录还原 `deployment-backups/pre-deploy-<stamp>/` 到安装目录，不挑文件。
3. 按 `manifest.json` 逐个校验 sha256/size。
4. 启动 Anki，跑 `python tools/verify-state.py`，确认 deployed/loaded 两层。
5. 复跑计数，必须与 manifest 的 `baseline_counts` 一致；异常则停止并保留现场。

`pre-deploy-20261112-105839` 这类只含 1 个文件的旧目录是**部分备份**，不是完整回滚点；`--check` 会拒绝它们。

## 8. 当前状态（2026-11-17 14:44）

| 层 | 状态 | 证据 |
|---|---|---|
| 源码 | 已改，未提交 | 本轮提交前 22 个 dirty 路径（含 `pre-deploy-check.py`、`test_pre_deploy_check.py`） |
| 测试 | 467 unittest | `Ran 467 tests ... OK` |
| 已部署 | 46/46 匹配 | `verify-state.py`；`pre-deploy-check.py --check` 为 `ok: true` / `EXIT=0` |
| 已加载 | 是 | 插件启动 14:37:25 > 最新文件 14:30:15 |
| 屏幕 | 托盘修复未手工验收 | 需在卡片在屏时按主窗口 X，再点托盘图标确认主窗口恢复 |

已知未验证项：
- 托盘图标点击恢复主窗口的真机操作未手工验收。
- 长词音节划分在真实卡片上的视觉与边界（`strength` 等单音节词有意不分）。
- 评分后下一张的实际手感（探针已量化，屏幕未确认）。
- `kyle_enrich.py` 的合规结论未定。

## 9. 验收脚本

- 冷启动 → 打开复习 → 评分 → 下一张 → 关闭重开。
- 边界：空牌组、缺字段、超长单词、断网、Anki 升级。
- 性能：连续 10 张，记录 p50/p90 与往返数。
- 数据：评分后计数与历史符合预期，不重复、不丢失。
- 视觉：长词分音节、弹窗不遮挡、深浅色主题正常。

## 10. 同类项目对标（2026-11-12 快照）

检索：GitHub Search API，`sort=stars`；剔除清单仓库、宿主主程序、MCP 服务和算法仓库。

### Anki 插件 Top 5

| # | 项目 | Stars | 语言 | 许可 |
|---|---|---:|---|---|
| 1 | FooSoft/anki-connect | 2,084 | Python | 未标注 |
| 2 | glutanimate/review-heatmap | 1,316 | Python | NOASSERTION |
| 3 | Stvad/CrowdAnki | 644 | Python | MIT |
| 4 | AwesomeTTS/awesometts-anki-addon | 503 | Python | GPL-3.0 |
| 5 | thepeacemonk/Onigiri | 495 | Python | GPL-3.0 |

### Zotero 插件 Top 5

| # | 项目 | Stars | 语言 | 许可 |
|---|---|---:|---|---|
| 1 | windingwind/zotero-pdf-translate | 12,272 | TypeScript | AGPL-3.0 |
| 2 | windingwind/zotero-better-notes | 8,444 | TypeScript | AGPL-3.0 |
| 3 | MuiseDestiny/zotero-gpt | 7,520 | TypeScript | AGPL-3.0 |
| 4 | l0o0/jasminum | 7,375 | TypeScript | AGPL-3.0 |
| 5 | MuiseDestiny/zotero-style | 5,355 | JavaScript | AGPL-3.0 |

Stars 是流行度，不是质量证明；复用代码前先看许可。

## 11. 变更记录

| 日期 | 变更 | 到达层 | 证据 |
|---|---|---|---|
| 2026-11-12 | 新增 `tools/pre-deploy-check.py`；生成完整回滚快照 | 备份/部署前 | `--check` EXIT=0；37/37；baseline `fc57d23d07fba5da` |
| 2026-11-12 | #65 音节划分 + #66 评分后停顿修复 | 已部署/已加载 | 启动 10:58:55；探针 p50 ~763 ms |
| 2026-11-12 | 优化 Anki 单词卡片模板/CSS：唯一区块 id、缩小音频图标、响应式与夜间模式；不改笔记内容 | Anki 模型层 | `cardsInfo` 渲染通过；6888 条笔记未变；备份 `deployment-backups/anki-model-20261112-153145.json` |
| 2026-11-12 | 发布包排除 `kyle_enrich.py` / `kyle_books.py`；manifest 加 `human_version` 与 26.9.3 兼容边界；新增包内容断言 | 源码/测试 | `test_anki_installer.py` 新增断言；后续全量测试 431/431 OK、打包验证完成 |
| 2026-11-13 | 完成 26.9.3 干净配置安装/加载验证；确认发布包不含两个源码模块 | 安装/加载层 | `meta.json` 回读 `0.4.0-beta.10` / `260903` / `-260903` / `disabled=false`；顶部工具栏 `zvr-desktop-review`；40 文件（39 包内 + `meta.json`），`kyle_enrich.py` 与 `kyle_books.py` 不存在 |
| 2026-11-17 | `pre-deploy-check` 将 `kyle_books.py` 归入 `INTENTIONALLY_ABSENT`；`--apply` 记录待部署 `new_files`，`--check` 归零 | 工具/测试 | 全量 467/467 OK；`--check` `ok: true` / `EXIT=0`；快照 `pre-deploy-20261117-144410` |
