# 交接：接手一个 Anki + Zotero 英语单词学习插件

你在一个开发了一半的项目上接手。**不要重写，不要假设"之前说完成了"就是真的完成。先读，再动，再验证。**

## 0. 你的用户

周，时序预测研究者，同时做抖音知识视频。他要证据、结论先行、整段委托。

- **回复极短**：只说他问的事——做没做成、证据在哪。不要一次输出一大篇。
- 只在确实需要他拍板、登录授权或存在不可逆影响时才问；其余自主完成并验证。
- 他会明确强调学习记录是他自己的。任何写操作先只读核对、留可回滚记录、一次只做一个破坏性动作。

## 1. 工作区

```
D:\Users\Admin\Documents\ChatGPT\Tools\zotero-vocab-review-branch
```

git worktree，分支 `feat/review-acceptance`，已推 origin。**原目录不要动**，所有工作在 worktree 里做。

Anki 26.9.3 装在 `D:\Program Files (x86)\Anki`，自带 PyQt6 在 `app_packages`；离屏 Qt 检查靠这个路径。

> **文档分层（2026-11-12）**：通用流程见 `plugin-development` skill（`C:\Users\Admin\.sclaw\agent\skills\plugin-development\SKILL.md`）；本项目路径、命令、基线、例外见仓库根目录 `PROJECT_PLUGIN_PROFILE.md`。HANDOFF 只保留交接状态，不再复制整套流程。

## 2. 第一条命令

```
python tools/verify-state.py
```

它输出五层：`source / deployed / loaded / config / on-screen`。

部署之后要重启 Anki 才算「已加载」，重启由 `tools/restart-anki.py` 做（用户 2026-11-02 授权）：

```
python tools/restart-anki.py --wait 300   # 等到空闲（没有卡片在屏 + 日志静默 25 秒）再关→开→自检
```

它只在空闲时动手，并在重启前后比对卡片计数，数据变了就报错退出。不空闲时它什么都不做，退出码 2。

### 部署顺序（固定，2026-11-12）

1. `python tools/pre-deploy-check.py --apply` —— 生成完整回滚快照（`deployment-backups/pre-deploy-<stamp>/`）并记录当前计数基线；只写备份，不动安装目录。
2. `python tools/pre-deploy-check.py --check` —— 必须 `EXIT=0`；备份不完整、未加载、计数不可读都算未通过，不进入部署。
3. 拷贝本次变更文件到 `%APPDATA%\Anki2\addons21\zotero_global_capture`（只拷变更，保留 `config.json` / `meta.json` / 词库）。
4. `python tools/restart-anki.py --wait 300` —— 看 `closed politely in N s`，不要强杀。
5. `python tools/verify-state.py` —— 五层；手动核 `lexicon/syllables_supplement.txt` 哈希，并确认重启前后计数 unchanged。

`--check` 的 `counts.baseline` 来自第 1 步；部署后复跑 `--check` 可直接看 `counts.changed` 是否为空。

> **2026-11-17 当前状态**：85158043 已禁用（备份见 §2.1），无复习卡时点 X 已实测直接退出；以下关于托盘的说明保留为禁用前的历史/兼容记录。

**退出方式（2026-11-04 更正，见 AUDIT §9.36）**：这台机器装着 **Minimize to Tray 2**（`addons21/85158043`），它把 `mw.closeEvent` 改成"收进托盘"，所以 **点 X、WM_CLOSE、AnkiConnect 的 `guiExitAnki` 全都不是退出**（实测 `guiExitAnki` 只会隐藏，最后仍要强杀）。真退出只有一个协议：`mw.closeEventFromAction = True` 然后 `mw.close()`。restart 工具因此改成：往 `%TEMP%\zvr-quit-request` 写请求 → 插件 5 秒内认领并按上述协议退出（实测 **3.9 秒干净退出、`profile_will_close` 首次触发、不再强杀**）→ 45 秒没人认领才回落到旧的 WM_CLOSE→强杀。看到 `closed politely in N s` 才说明这条路通了。

两条自己判断的规则（用户 2026-11-02 明确授权，不必再问；17:40 又补一句「我不想手动关，你自动给我重启」）：

- **没人管的卡片**：日志静默 ≥90 秒还开着卡，就当作 abandoned，用 WM_CLOSE 关掉它再重启。这等于按「不评分，结束」：不写评分、不改复习历史，那张卡仍留在队列里。发关闭前再查一次卡片——提醒卡可能正是在"空闲判定"和"发关闭"之间冒出来的。
- **60 秒就自己升级，不再麻烦用户**：Anki 的 `closeEvent` 本来就 `event.ignore()` 后异步收尾（反编译确认），所以"窗口还在"不等于被拒。规则：**屏幕上没有卡片窗口**却 60 秒没退出 → 自动 `taskkill /F` 把重启做完（评分即时提交、每小时 `.colpkg` 备份，没有可丢的东西）；**只有还开着卡片才拒绝强杀**。`taskkill /PID` 只达可见窗口，所以 20 秒没人应答时先 `ShowWindow(SW_SHOW)` 再补 WM_CLOSE，**只认 `<profile> - Anki` 的主窗口**——Qt 的 `_q_titlebar` / 标题就叫 `Anki` 的隐藏辅助窗口不能碰（会凭空多出任务栏，退出时留 `Anki2/crash.log` dump）。

**规则：源码已改、测试通过、文件已部署、Anki 已加载、真屏已验证——五件事，不许混为一谈。** 报告进度必须分层说，说清卡在哪一层。

## 2.1 本轮提交说明（2026-11-17，已提交；其余工作区文件未提交）

- **新增工具** `tools/count-revlog-time.py`：只读调用 AnkiConnect `findCards` / `getReviewsOfCards`，统计指定时间窗内 `revlog.time` 的 0 / 非 0 条数；不写复习记录，不改设置。
  - `--limit N`：取最新 N 条，默认 30；`0` 表示全部。
  - `--since ...`：支持 ISO 日期时间、本地日期、epoch 秒/毫秒；按 review id 过滤。
  - 输出 `total / zero / nonzero / distinct_cards / time_ms_min/max`；不足 N 条时额外输出 `shortfall`。
- **自检**：新增 `tests/test_count_revlog_time.py`，8 条离线 unittest，覆盖时间解析、窗口扩展、`getReviewsOfCards` 分批、since 过滤和报表；`python -B -m unittest discover -s tests -p 'test_count_revlog_time.py' -v` 全绿。整仓 unittest 481 条全绿（运行时显式设置 `APPDATA=C:\Users\Admin\AppData\Roaming`）。
- **实测**：`--limit 30` 为 `zero=0 / nonzero=30`；`--limit 0 --since 2026-11-17T17:16:49+08:00` 为 `total=101 / zero=0 / nonzero=101`（验证时数据；工具本身不写 revlog）。
- **托盘插件**：`85158043`「Minimize to Tray 2」已禁用，原 `meta.json` 备份在 `anki-authority-audit/deployment-backups/tray-addon-85158043-meta-20261117.json`；无复习卡时点 X 已实测 `ANKI_EXITED`，随后重启成功。建议 git 提交信息：`tools: add revlog time audit and self-check`。
- **部署状态**：本工具与测试属于源码/自检，不改 addon 安装目录，无需部署或重启。

## 2.2 本轮提交说明（2026-11-19，已提交并推送）

三个提交 `e143548` → `8591e7d` → `336aa23`，`origin/feat/review-acceptance` 已同步（ahead 0）。

- **`e143548` 揭晓只改一次高**。病根不是插件的 `resize`，而是 Qt `QLayout` 默认的 `SetDefaultConstraint` 把布局最小高度压到顶层窗口上：真实揭晓时 `answer_scroll.show()` 把下限抬到 583、`grade_widget.show()` 再抬，Qt 自己撑大窗口，最后才是 `fit_card_height()` 的 687。实测 `setMinimumHeight(0)` **无效**（下次布局激活就把最小高度写回：0→173→471）；在 `reveal()` 里对布局设 `SetNoConstraint` 才有效。
- **证据工具** `tools/probe-answer-reflow.py`（新增）：同时记录 Python 层 `resize` 调用栈、Resize 事件、布局 `minimumSize` / `sizeHint` / `heightForWidth`。同一张卡从 477 起揭晓，基线 3 次改高（499→546→677，前两次无 Python 调用），`SetNoConstraint` 后 1 次（677）。
- **真机前后对比**（`probe-card-switch`；before `zvr-switch-20261119-092347.jsonl`，after `zvr-switch-20261119-100850.jsonl`）：before 抓到 `477→583→687`；after 10 次揭晓全部单步（486/537/542/543/477/512→687、571/607/661→725），19 次改高 `dy=0`，y 恒 256，中间态未复现。
- **`8591e7d` 三项修复**：静默后台同步（`sync_background` / `sync_silent` / `sync_background_minutes=5`）、未捕获异常进运行日志（串联而非替换 `sys` / `threading.excepthook`）、评分写入校验（`STALE_TOKEN_MESSAGE` + revlog 前后比对，仅 stale 拒绝重试一次）。
- **`336aa23` 重建 dist，红线：dist 只能从干净工作区重建**。重建前 dist 与任何提交都不一致——`review_popup.py` 落后一版、`__init__.py` 落后两版、`config.json` 等于工作区而非 HEAD，因为它是从带未提交改动的工作区打的。重建后 `.zip` 47 条 / `.ankiaddon` 48 条与同提交源码逐字节一致，`SHA256SUMS` 核对通过，`tests/test_build.py` 4 条通过。以后顺序固定：先提交源码 → 再 `python anki-global-addon/build.py` → dist 单独一个提交。
- **闸门**：492 unittest 全绿（**`APPDATA` 已不需显式设置**，空环境下也能跑，见 §2.3 的 `02432f5`；上面 §2.1 那句“显式设置 `APPDATA`”是当轮记录，已不适用）；离屏 Qt 33/34，唯一失败 `windows-judgment-rows.py` 是已知计时抖动，单跑 1/1。
- **本轮部署**（`e143548`）：`pre-deploy-20261119-095500`（49 文件，fingerprint `c954692976c99cbe`）；`review_popup.py` `3E4A4FA4 → C0F84D38`；重启 `closed politely in 6.4 s`，计数 `5215/1312/284/6889` unchanged；`--check` exit 0，loaded 09:56:12 晚于安装 09:52:25。

## 2.3 CI：runner 上的两个环境坑（2026-11-19）

PR #26 的 Checks 在 `e143548` 变红：`Ran 481 tests ... FAILED (failures=1, errors=1)`。两个都不是业务逻辑错，是**只在本机 Windows 成立的环境假设**。

1. **runner 没有 `APPDATA`**（`KeyError`，记为 error）。`tools/verify-state.py` 的 `appdata()` 原来写 `Path(os.environ['APPDATA'])`，ubuntu runner 直接抛异常，`test_every_layer_returns_lines` 在 deployed 层就断。还有第二处被它挡住：`layer_onscreen()` 走 `ctypes.windll`，Linux 上是 `AttributeError`。改法（`02432f5`）：`appdata()` 退化成 `Path.home()/'AppData'/'Roaming'`（与 `tools/pre-deploy-check.py` 已有写法一致），`desktop_is_visible()` 开头加 `sys.platform` 守卫。现在在没装 Anki 的机器上五层照样出字：`deployed` 给 `NOT INSTALLED: …`、`config` 给 `no meta.json`、`on-screen` 给 `SCREEN NOT VISIBLE (no Win32 desktop on linux)`。
2. **runner 是 UTC，测试钉的是 +08:00**（failure）。`tools/count-revlog-time.py` 的 `parse_since()` 结尾 `return int(...), parsed.astimezone()` 把结果归一化到**机器时区**，于是 `2026-11-17T17:16:49+08:00` 在 UTC runner 上返回 `utcoffset()+00:00`，断言 `== 8h` 红。这不只是测试问题：同一命令在 UTC 机器上会落在**不同的日历日**，`window_days_for_since()` 跟着偏。改法：直接返回 `parsed`，保留用户写进去的偏移，epoch 毫秒不变。

**复现捷径**：agent shell 里 `APPDATA` 本来就是空的，等价于 runner 条件——`python -B -m unittest discover -s tests -p 'test_*.py'` 当场就能看到同一个 KeyError，不必上 Linux。

**action 升级（`5f8097d`）**：`checks.yml` 与 `release.yml` 里的 `checkout@v4` / `setup-node@v4` / `setup-python@v5` 全部改成 `@v7`（各自最新 release：checkout v7.0.1、setup-node v7.1.0、setup-python v7.1.0）。旧版本会在 job 里留一条 `Node.js 20 is deprecated … forced to run on Node.js 24`；升级后 `repos/<owner>/<repo>/check-runs/<job>/annotations` 返回 `count=0`。两个 workflow 都要改，只改 checks.yml 的话发版时 release.yml 还会再报一次。

**证据**：run `44449553382`（`02432f5`）全绿，之前被 skip 的两个 `build.py` 步骤首次真正执行；run `44471541804`（`5f8097d`）全绿且 annotations 清零；本地 492 unittest OK（`APPDATA` 为空条件下）。

**接手注意**：这个 clone 没有全局 git 身份，提交前先 `git config user.name/user.email`（本项目用 `Ruoquan Zhou <239778096+zrqworkmail-cloud@users.noreply.github.com>`）；远端会前进，`push` 前先 `git fetch` + `rebase`——本轮两次推送都撞到过新提交。

**升级 action 后必须多看一步**：Checks 变绿只能证明 `checks.yml` 还能跑，`release.yml` 平时不触发，改坏了也不会泛红。用 `gh workflow list --repo <owner>/<repo> --all` 确认 `Checks` 与 `Release` 都是 `active`（本轮两个都 active）；工作流文件语法坏掉时 GitHub 会直接不认这个 workflow，这是最省事的一道闸。发版前如果没跑过 `release.yml`，至少先看一眼它还在列表里。
- **通用经验**（与宿主无关）：方法论沉淀在仓库内 `docs/插件开发全流程执行手册_v1.0.md` **§19 通用经验**（先量后改、框架也会动手、改动要先证明生效、包=安装目录=运行中代码、写后校验、钩子串联、只读探针、同口径对比、部署受控、规则带出处），上线前清单见 **§19.13**；`plugin-development` skill 的 `## General Experience` 只保留指向本文件的指针，不重复维护。手册是唯一副本（2026-11-19 从 SCNet 工作区移入仓库，工作区那份已删）。
- **文档归位（2026-11-19）**：`插件开发全流程执行手册_v1.0.md` 从 SCNet 工作区移入本仓库 `docs/`，成为唯一副本（工作区那份已删除）；HANDOFF 用仓库相对路径 `docs/插件开发全流程执行手册_v1.0.md`，`plugin-development` skill 用绝对路径并注明「按仓库相对名解析，不按盘符」；随提交 `3a5df41` 入库（`5c80677..3a5df41` 推送，网络中断后由 HTTPS 重试成功）。

## 3. 现在的真实状态（2026-11-13；历史基线 2026-11-10，AUDIT §9.11 与 §9.13–§9.51；最新兼容验证见开头）

> **2026-11-17 复核**：#65/#66 的部署已完成；`verify-state` 为 **46/46 文件匹配**安装目录，插件已于 **20:55:34** 加载。下面「文件未部署 / 部署 baseline / 接手后第一步」均为当时的交接记录，不代表当前状态。

### 26.9.3 兼容验证（2026-11-13，已完成）

- **结论：Anki 26.9.3 兼容边界成立。** 干净 base 为 `...\workspace\anki-compat-26.9.3\base`，profile `User 1`，`ANKI_SINGLE_INSTANCE_KEY=anki-compat-260903`；用 `Tools → Add-ons → Install from file...` 安装 `anki-global-addon\dist\zotero_global_capture.ankiaddon`，Add-ons 列表出现“单词随身复习与全局划词”。启动提示 `26.09.4` 更新时选择 **No**，未升级。
- `meta.json` 回读：`human_version=0.4.0-beta.10`、`min_point_version=260903`、`max_point_version=-260903`、`disabled=false`。
- 加载证据：重启后顶部工具栏出现“开始学习 · 未选词书”（`zvr-desktop-review`），安装前无此入口；启动无“不兼容/加载失败”对话框，说明已实际加载执行。
- 文件核对：归档 **39 个文件条目**；安装后 **40 个文件 = 39 个包内文件 + Anki 运行时生成的 `meta.json`**。其余 39 项逐项比对 SHA256 与大小全部一致，无缺失、无不匹配；`kyle_enrich.py` 与 `kyle_books.py` 均不存在。
- 收尾：干净实例用 `File → Exit` 退出；活动实例未参与安装、未写入。**当前 `min=max=260903` 仍只声明 26.9.3，未实测版本不冒充兼容。**
- 详细证据见 `PROJECT_PLUGIN_PROFILE.md` §6。

- **这一轮（§9.50 / §9.51，#65 + #66）：代码完成、闸门全绿。当时记录为「文件未部署」；该说法已过时——2026-11-17 核实已部署并加载，详见上方复核。** 两件事：
  - **#65 分词改造**：用户「去掉机械分块，我希望按照音节分」。做法是**书面音节划分**（不是按发音算、不是词根词缀）。删掉 `morphology.spelling_chunks` 的 4 字母机械兜底，查不到音节来源就 `return None`（不显示分段，绝不显示假分段）。数据三层：随包 2.5 万词表 + 补充文件第 1 段（完整版 Moby Hyphenator II 187,175 条公有领域里挑的 66 词）+ 第 2 段（37 个词典核对词 = 32 个 MW 词头点分 + 5 个写在文件头的派生）。复测：20082 键、词书缺词 104→覆盖 103（`strength` 单音节有意不分）。**MW 抓取只有 `mcp__windows_mcp__Scrape` 能过（WebFetch/curl 都 403），词头中点后带零宽空格 U+200B**；死掉 agent 的核对结果从 jsonl 顶层 `toolUseResult` 抢救（脚本 `tmp/salvage_agent_evidence.py`）。详见 §9.50。
  - **#66 评分后卡顿**：根因是 `_next_result` 30+ 次串行往返 + `_flip` 的 `ready.wait(0.4)` 超时后**重算一遍**。修法：`_flip` 最多等 15s（死锁阀）绝不重算、预取 `try/finally` 保证 ready 被 set、`_multi` 把独立只读合并成一次 AnkiConnect `multi`（按序返回纯结果，不是 [result,error] 对）。**同一活合集复测：旧 3983ms/35 往返 → 新 ~2960–3200ms/16–17 往返**；后续批量化实测已把 `prepare_question` 压到冷 **874 ms / 8 次往返**、warm **645 ms / 7 次往返**（见下条）。「不卡」靠预取把读时藏到看答案那段时间背后，不是消成 0。详见 §9.51。
  - **§9.51 补充：`prepare_question` 冷/热缓存实测（2026-11-18，只读探针，live 账户 `1` / `cet6_full`，各 8 次）**：
    - 冷缓存：中位数 **874 ms / 8 次往返 / 164 actions**；范围 798–1720 ms、8–9 次往返、163–165 actions；P90 **1035 ms**。
    - `--warm-captures`：中位数 **645 ms / 7 次往返 / 17 actions**；范围 440–915 ms、6–8 次往返、16–164 actions；P90 **716 ms**。
    - warm 第 1 次仍是冷启动（**915 ms / 8 次往返 / 164 actions**）；第 2–8 次为 **440–716 ms**，中位数 **642 ms**，每次 **16–17 actions**。
    - 剩余独立往返主要是 `cardsInfo`（约 103–109 ms）与 `getDeckStats`（约 60–63 ms，仍单独占一个 `multi`）；`findCards` 已合并进少量 `multi`。真实连续会话表现为首卡冷、后续约 **0.64 s**。
  - **§9.51 二次优化（2026-11-18，源码未提交、未部署）**：
    - `getDeckStats` 不再单独发：它和候选 `findCards` 同批；新词/到期两条队列一次取回，采集命中查询按 deck 合并（不再按队列各查一次）。空牌组仍不会被统计查询。
    - `cardsInfo` 与独立的学习状态查询同批；状态查询覆盖整批候选，选中卡直接查表，不再在选项批里多读一次。`_cards` 的干扰项 `cardsInfo` 仍单独发，因为它依赖 base 采样结果，无法前置到候选批。
    - 最终热缓存 8 次（`--warm-captures`）：中位 **577 ms / 5 次往返 / 18 actions**，P90 **837 ms**；其中 5 次往返的运行 **462–595 ms**；第 1 次仍是冷启动 1131 ms。连续复测中位数在 392–612 ms 之间浮动，系统负载有波动；未再出现 `getDeckStats` 或初始 `cardsInfo` 单独占往返。
    - 冷缓存 8 次：中位 **899 ms / 7 次往返 / 166 actions**，P90 **1056 ms**，范围 717–1064 ms。历史记录是 874 ms；同机从 HEAD `5080294` 重跑为冷 **1078 ms / 8 往返**、热 **722 ms / 6.5 往返**，所以热缓存下降明确，冷缓存受采集缓存和机器负载影响，不能单独当作提速证明。
    - **481 unittest 全绿**；`review_logic.py`、`tests/test_batch_reads.py`、`tests/test_review_logic.py` 仍是工作区改动。probe 读的是仓库源码、live 合集的只读数据。
    - **真机部署（2026-11-18 11:35–11:42）**：先重建 `dist`（zip 47 项、ankiaddon 48 项；包内 `review_logic.py` 与源码 SHA256 一致）。拷贝前的 `pre-deploy-check --check` 不可能归零：deployed 层必然报本次预期的 `review_logic.py` 差异，且旧备份计数 1241 已过期；因此按工具设计先 `--apply` 刷新回滚点 `pre-deploy-20261118-113925`（48 文件、baseline 1291、fingerprint `4dc1329bf10664b7`），再拷贝 `review_logic.py`（旧/新 SHA256 `EE608DDA…` → `FB5319C0…`）并 `restart-anki --wait 300`。重启 `closed politely in 6.1 s`、AnkiConnect 2 s 后应答、计数 `5211/1291/284/6889` unchanged；随后 `pre-deploy-check --check` exit 0（deployed 45/45 匹配，loaded 11:40:49），`verify-state` 五层：source dirty 7、deployed **46/46**、loaded 真机新码、config 正常、on-screen visible。
  - **闸门**：428 unittest / 26 node / 34/34 离屏 Qt 全绿（`windows-judgment-rows` 在全量里偶发一次 33/34，单跑 3/3 与全量复跑都绿，是计时敏感的旧检查，与本轮无关）。
  - **部署 baseline（历史：verify-state，2026-11-10）**：19/23 文件匹配；DRIFT = `morphology.py` `review_logic.py` `review_popup.py`；`kyle_enrich.py` ABSENT（旧有、从未部署、真题合规未定，别顺手部署）；真机仍跑旧码（插件启动 2026-11-10 09:50:30）。**`verify-state` 部署层只哈希顶层 `*.py`，不查 `lexicon/`——部署后必须手动比对 `syllables_supplement.txt` 哈希，否则假绿。**
  - **当时的接手后第一步（已完成）**：按 §2「部署顺序」：`--apply` 生成完整快照 → `--check` 必须 0 → 拷贝本轮变更（当前是 `morphology.py` `review_logic.py` `review_popup.py` + `lexicon/syllables_supplement.txt`）→ `restart-anki.py --wait 300` → `verify-state.py` 五层 + 手动核词典哈希 + 重启前后计数 unchanged → 真机验收「分词是否合理」「评分后是否还卡」。

- 这一轮（§9.48）：**「本组结束」不再猜原因，取卡顺序改成今日新词在前，多选词组的引擎落地（设计文档第 1–4 步）**。先量再解释：《六级核心》在架 269 张里 0 新 0 到期，合集另有 38 张到期不在书内——旧文案那句"已选题型下没有可学的卡，可能是牌组当日新词额度已用完"**两个猜测都不成立**，病根是把算出来的 0 用模糊话包装。`end_of_session_reason()` 现为六条各报自己数字的分支（含新的"所选词组已学完 + 合集里另有 N 张到期"）。队列从 `due→new` 换成 `new→due`，**同时必须把内层 `break` 改 `continue`**，否则到期词永远进不了卡。选取模型换成有序条目列表 `{book, tags}`，`tags: []` 读作"整本"，旧单本键自动折成一条（没碰新控件的人学的东西一字不变），指向不存在词书的条目丢弃不猜（§9.4a 的形状）；标签子集用 **OR**（勾第二个标签绝不让词池变小），跨条目片段**必须加显式括号**（反证过：去掉就红）。`prepare_question` 外层按条目循环 + `_selection_index` 盖章 → **顺序接续是引擎自带的**（反证过：缩成 `range(1)` 红三条）。两个自伤值得记住：`review_logic.py` 里一度有**两个同名 `def resolve_book_decks`**，旧版静默覆盖新版，Python 不报错 → 新增 AST 顶层重名检查；`_book_decks_by_book` 曾把缓存写在**调用方的 cfg** 上，两条 plan 测试其实是靠共享 CFG 污染才"通过"的。**新查出来没修的**：那本词书剩下 104 张新词全在 170 张挂起里，而 170 挂起 = 170 `zvr_mastered`（差集两侧都是 0，就是用户自己按 E 的结果），所以"没有未学的新词"只对"在架"成立——该分支要把挂起数报出来，且绝不替用户取消挂起。301 unittest / 26 node / 24/24 离屏 Qt 全绿；11:46:36 部署 `review_logic.py` `review_popup.py`（`pre-deploy-20261105-114636/`）、11:46:43 加载、`closed in 3.9 s`，重启后 269/269/175/6885 **逐项 unchanged: True**。**可见变化只有两条**（那句话现在说真话、新词先于到期）；第 5 步（设置页多行 + 每本勾标签）做完之前，UI 造不出多条目选取。

- 这一轮（§9.47）：**输入法实验做完并把有效杠杆装进拼写框**。三代探测各有 bug：手动版被中途 Shift 污染（但 ① 对照两次出中文、② 关 `WA_InputMethodEnabled` 两次出字面 `ceshi` 这一对可用）；自动版先崩在 `Qt.FocusReason.StrongFocus`（该成员不存在，StrongFocus 是 FocusPolicy），再栽在 `INPUT` 联合体缺 `MOUSEINPUT` → `sizeof` 28/32 而非 40 → `SendInput` 返回 0、四框全空，**差点把"我的注入坏了"读成"输入法没合成"**；第三次 90 秒没人点，安全阀正确地一个键都没发。改读 API（`ImmGetContext`）后四种配置都 `attached`，但探测窗口从未活动，**只能算"这个测法测不出来"，不是否定**。最终决定不再探测：`input_mode.make_latin_only()` 设 Qt 的 `WA_InputMethodEnabled=False`（PyQt6 延迟导入以保持纯测试无依赖），`LetterBox.__init__` 调用；`ImhLatinOnly` hint 保留但注释写明已被证明不是修复点；`ReviewInputMode`（IMM32）降级为 legacy best effort 保留（发布给非 TSF 机器要用）。新增 `tests/windows-input-method.py`，反证过（删一行立刻红）。281 unittest / 26 node / 24/24 离屏 Qt 全绿；10:33:48 部署（`pre-deploy-20261105-103348/`）、10:33:56 加载、4.0s 礼貌重启。**唯一没证明的是"真机上不再出候选"——离屏没有输入法，必须由用户在下一张真卡上确认。**

- 这一轮（§9.46）：**两个动效开关的分工核实完毕，并查出一条"只有数据、没有实现"的步骤**。分工（从代码反查，不是照标签念）：`review_motion_hop` → 只作用在字母框（打对跳 11px、打错抖 5px，`review_popup.py:263`）；`review_motion_celebration` → 只作用在庆祝覆盖层（`review_popup.py:1514`）。**问题**：`TIMING['word']`（单词上移 9px/420ms）没有任何代码读取，而 `timeline()` 列出它、测试还断言 `steps['word']['duration']==420` —— 测试把"数据里有一项"当成了"软件有这个行为"；§9.37 那句"折成上移 9px"描述的是从没落地的实现，已就地加更正块。**教训：记录动效落地要写"谁读了这个数、在哪个控件上看到位移"，不能写时序表条目。** 用户选择删掉空步骤（不补实现），于是 `TIMING` 只剩 letter/slip/badge/confetti，`timeline` 只剩 letter + badge(+confetti)，`slip` 保持不在 timeline（按按键触发）。新增 `test_no_step_is_advertised_that_nothing_plays` 钉住集合，并如实标注 **confetti 只有标志位与绘制路径被见证、没有像素级见证**。设置页说明改为明写分工。279 unittest / 26 node / 23/23 离屏 Qt 全绿；10:05:39 部署 `card_motion.py` `__init__.py`（`pre-deploy-20261105-100539/`）、10:05:47 加载，`closed politely in 4.0 s`，计数 276/272/163/6885 与用户自己进度一致。**对用户可见行为零变化**（删的是本来就不播放的数据）。

- 这一轮（§9.45）：**规则读对了——约束对象是徽章内部零件 vs 它自己的英文单词，四个档位一律；卡片内容被短暂盖住是用户接受的代价，不是问题**（用户原话「不是说下面的卡片上的内容不可以被挡住」，我 §9.44 把两件事混写过）。做法升级成安全框：`geometry()` 算 `word_box`（字面 + 挤出 + 半个奶白描边）与每个零件矩形，`overlaps_word()` 返回相交的零件名，空才算干净。缎带间隙改为**实测导出** `gap = outline + stroke + pixel*0.06`——原来写死的 `pixel*0.06`（2.8px）比描边半宽 3.2px 还小，四档都残留 0.1–0.4px 压字，肉眼看不出、几何断言一跑全报；两颗闪光的 dy 从 +0.52/+0.48 移到字上方。**反证这次逐字复制原行**（改回 `pixel*0.06` → 3d 立刻红 `['ribbon']`）；3c 的 verdict 行断言没被反证过，只是前向守卫，别当已验证。278/26/23 全绿，09:50:26 部署（`pre-deploy-20261105-095026/`）、09:50:32 加载，2.7s 礼貌重启且**未关闭在屏卡片**。真屏复验由 `tools/catch-live-motion.py` 后台监听中。

- 这一轮（§9.44）：**庆祝字被自己的缎带咬掉下半截，已按单词实测边界重排**。病根是 `_ribbon` 用魔法分数 `centre.y() + height*0.80` 定位，而单词实测底边不在那个分数上——旧缎带顶弧盖掉字母 **17.8–26.2px**（字面总高才 33–46px）。新增 `candy_badge.geometry()` 返回各部件垂直位置，缎带从 `bounds.bottom()+depth+gap` 起放，缎带半高 0.34→0.22、宝石随缎带一起滑入，顺带让「回答正确」行也不再被宝石盖。`windows-card-motion.py` 3c 增加 verdict 行，新增 3d 断言 `ribbon_top >= word_bottom` 与"弹冲 1.14 倍下宝石不碰评分行、星簇不碰单词行"。**反证的教训（别删）**：第一次反证我把旧写法"等价改写"成 `+ band`，断言没红，差点当成检查有效；逐字照抄出事那一行才红（`284.5 < 296.5`）。**反证不红＝检查没咬住，不给没咬住的检查记功**；3c 的 verdict 行在 harness 那张 6 字母卡上两种尺寸都没被碰到，所以它只是前向守卫、**没有被反证过**。278 unittest / 26 node / 23/23 离屏 Qt 全绿。**分层**：08:58:47 已部署（`pre-deploy-20261105-085847/`），但 `restart-anki.py` 判定"用户正在学习"**拒绝重启**，真机仍跑 22:41 版；该工具的 90 秒无操作规则把用户放着没动的 `exist` 卡关掉且未评分（卡回队列，无排程写入，计数 293/146 与用户自己的进度一致）。

- 这一轮（§9.43）：**庆祝窗锚点改到卡片正中央**（`BADGE_TOP_FRACTION` 0.60→0.50），并且第一次把"哪两排不许被盖住"变成逐像素断言——`windows-card-motion.py` 3c 段比对单词行 QLabel 与评分按钮行在庆祝期间与无庆祝时是否逐字节相同，另钉"锚点等于 height × 常数"。**代价要说明白**：中央位置遮住解释框下沿与例句框中部（例句关键词这一秒会被盖，动画结束即恢复），单词行含音标和评分按钮行都干净。踩到的坑：最初拿 `letter_boxes` 当单词行，那是题目面控件、答案面上隐藏、几何是陈的，断言在 y 313-353 报了个错原因——**隐藏控件的几何不能当判据**。样片工具里硬编码的锚点数字也改成读常量。278 unittest / 26 node / 23/23 离屏 Qt 全绿，22:41:08 部署 `motion_view.py`（`pre-deploy-20261104-224108/`）、22:41:16 加载，`closed politely in 5.0 s`，计数 296/253/143/6885 一致。真屏未验。

- 这一轮（§9.42）：**庆祝窗内不再出现汉字**（缎带留空，`TIER_LABELS`/`tier_label()` 直接删掉而不是传空串），**设置页把三档单选钮换成两个独立开关**「拼写时字母跳动」/「答对时弹出庆祝特效」（新键 `review_motion_hop`、`review_motion_celebration`；`timeline(tier, cfg)` 按布尔拼步骤）。旧 `review_motion` 只在两个新键从未写过时兜底：`off`→全关，其余→全开，**不许悄悄关掉别人已经选过的安静**。保存不再写 `review_motion`，harness 同时钉住"旧单选钮不许回来"。踩到两个坑：`shows_celebration` 曾拿 `bool(timeline(...))` 回答，"只开跳动"也谎称有庆祝；`windows-core-settings.py` 是 AST 抠函数单独 exec 的，`__init__.py` 的模块级 import 不在它命名空间里，新依赖必须同步喂进 harness scope。278 unittest / 26 node / 23/23 离屏 Qt 全绿，22:25:09 部署五文件（`pre-deploy-20261104-222509/`）、22:25:58 加载，`closed politely in 3.8 s`，计数 296/253/143/6885 一致。**本轮改动后真屏未验**（当日窗口已过 22:00，下一次排程约 10 小时后）。

- 这一轮（§9.41）：**庆祝徽章按用户给的六张三消游戏素材重画**（前四版——药丸/贴纸/缎带/朱批印章——全被否）。新 `candy_badge.py`：金色三段渐变字面 + 向右下挤出的洋红侧壁 + 面与侧壁共用一条奶白轮廓，配放射光、四角星闪光、三星簇、缎带压宝石；大字改成等级英文。三件必须记住的事：① **透明是量出来的**——最后一个渐变色标强制 alpha=0、光晕缩放画笔而非形状、放射从 0.34 半径起画，`windows-card-motion.py` 现在逐像素断言四档位的六个边角 alpha 必须为 0；② **档位阶梯一度写反**（`tier >= 3`），现在装饰判定归 `card_motion.shows_rays/shows_stars/sparkle_count`；③ **动效拆成纯算术** `card_motion.badge_pose()`，Qt 层不发明任何数字。内置 `ImageGen` 本轮不可用（两次 `No healthy endpoint candidates`），全部代码绘制。275 unittest / 26 node / 23/23 离屏 Qt 全绿，21:49:53 部署（新增 `candy_badge.py`，`pre-deploy-20261104-214944/`）、21:50:05 加载，`closed politely in 2.6 s`，计数 300/237/139/6885 一致。**真屏抓到过一次**（`%TEMP%\zvr-motion-live-1793800656.png`，T3 GREAT 绿缎带），用户看完这一张才提出 §9.42 那两条。

- 这一轮（§9.40）：**判断题/选择题的选项不再被窗口拉成 190px 大块**（量出来 sizeHint 37px、实得 190px；原因是 `addWidget(row, 1)` 的 stretch + `_ChoiceRow` 默认 Preferred 垂直策略）。修法是选项不带 stretch + 显式 `QSizePolicy` 垂直 Fixed，选项高度从此与窗口高度无关。**同时记录一次主动撤回**：顺手让内嵌卡收缩宿主窗口以消除下方空白带，立刻撞红 `windows-next-card-transition.py` 的 `old.geometry()==before`（"换卡不跳窗口"是既定行为），故回退，只留选项修复；空白带要不要消，交给用户判。267 unittest / 26 node / 23 离屏 Qt 全绿，19:54:25 部署、19:54:32 加载，计数 308/226/131/6885 一致。

- 这一轮（§9.39）：**庆祝从"只有 typing"扩到 typing/cloze/listening，速度门槛 3s→6s，星芒 T1-T3、彩带 T1-T2**（真机量出来全天 134 张只弹 6 次庆祝、T1 与彩带从未出现）。同时**真机抓取推翻了我的离屏自评**：徽章原锚点 0.24 在真卡高度下正好盖住被庆祝的单词，已改到 0.68（"回答正确"那一行上面），并把离屏渲染的高度对齐真卡、新增"单词带必须逐像素不变"的断言。庆祝扩题型**只扩徽章，不动评分建议**（`suggests_mastering` 仍只给 typing 免时钟）。267 unittest / 26 node / 22 离屏 Qt 全绿，17:05:49 部署、17:05:58 加载，计数 313/205/126/6885 一致。

- 这一轮（§9.37）：**拼写题动效落地**（用户「做吧」批准 2026-11-02 的样稿）。新 `card_motion.py`（档位判定 + 时序 + 三档开关，纯算术可测）与新 `motion_view.py`（`Celebration` 覆盖层 + `hop()`/`shake()`）。与样稿三处不同：徽章文案**中文**、**取消整卡震动**、单词"放大跳出"折成**上移 9px**（Qt 缩放布局内控件会触发重排，把刚修好的行宽算术全打回去）。硬规则：庆祝层必须是 raise 起来的**子控件**（画在 QDialog 的 paintEvent 里会被单词和按钮盖住）；`hideEvent` 必须 `stop()`（否则就是 §9.32 那种重影）；覆盖层 `WA_TransparentForMouseEvents` + `NoFocus`，所以庆祝中按回车照样翻页。设置页「卡片动效」= 全部动效 / 只要庆祝 / 关闭动效。266 unittest / 26 node / 22 离屏 Qt 全绿；11:28:00 部署、11:29:28 加载；**重启走托盘协议 `closed politely in 4.0 s`（第二次，无强杀）**；计数 332/167/107/6885 一致。待真屏验收（跳得是否过火、中文徽章、有没有挡回车）。

- 这一轮（§9.36）：**§9.34 那个"Anki 退不掉"的病根找到了——不是 bug，是用户装的 Minimize to Tray 2**（`addons21/85158043`：`setQuitOnLastWindowClosed(False)` + 重写 `mw.closeEvent`，真退出要 `mw.closeEventFromAction=True`）。三处改动：① 关闭主窗口时若托盘在场且没有卡片 → **交还给托盘、两个定时器都不停**（停表就是"闷着一小时不弹卡"的成因）；② 卡片菜单「退出 Anki」以前在这台机器上只会收进托盘，现在按托盘协议真退；③ `restart-anki.py` 改成 `%TEMP%\zvr-quit-request` → 插件 5 秒轮询认领 → 真退出。**实测：`closed politely in 3.9 s`，日志第一次出现由我们触发的 `profile_will_close`，不再强杀、不再跳过退出备份。** 249 unittest / 26 node / 21 离屏 Qt 全绿，10:42:13 部署、10:43:5x 加载，计数 338/157/101/6885 一致。§9.34 的"看门狗"方案作废。

- 这一轮（§9.35）：**拼写题的建议评分改成按提示的种类与位置计**——一次写对无提示 = Mastered（本来就在，E 键即已掌握）；1 次发音 = Easy、2 次 = Good、≥3 = Hard；空格字母提示按 `1/(i+1)` 位置加权算"已给出多少"，≤20% Easy / ≤40% Good / ≤70% Hard / 更多 Again（characteristic 首字母 31% → Good，drive 首字母 44% → Hard，advantage 末字母 4% → Easy）；释义/例句仍按 Hard 地板；只有 `typing` 走新算术，其他题型不变。**组间倒计时**改成大字 `按 Enter 进入下一组学习`（`QLabel#breakHint` 20px 粗体），并修掉"字母框还活着会吃掉 Enter"的隐患（面板出现时禁用 letter_boxes + 抢焦点）。242 unittest / 26 node / 21 离屏 Qt 全绿，10:26:48 部署、10:27:29 加载，计数一致（338 / 157 / 101 / 6885）。**待真屏验收**：状态行是否说清了建议依据、倒计时大字与 Enter。
- **2026-11-04 早：自动弹卡停摆过一次**（§9.34）。08:56 用户关掉 Anki 主窗口 → 插件按设计停掉复习与后台同步定时器让 Anki 退出，而 Anki 的退出**从来没走完过**（`profile_will_close` 不触发，§9.22）→ 结果是一个没窗口、进程仍活、AnkiConnect 仍应答、但所有 QTimer 全死的僵尸，54 分钟一张卡都没弹，用户完全看不出来。当时弹卡条件全满足（`review_enabled=True`、窗口 08:30–11:40、15 张到期）。已用 `tools/restart-anki.py` 恢复（09:55:05 定时器重新排程，计数 346/154/93/6885 前后一致）。**看门狗修复尚未实施，需用户批准**；现场只读探针是 `tools/probe-live-anki.py`（看进程是否还能应答、词书里还剩多少到期/新卡；注意搜索里"新卡"是 `is:new`，`prop:isNew` 无效）。
- **235 unittest / 26 node / 20 离屏 Qt 全绿**，`verify-state` 的 **loaded 层绿**：安装目录 20:25:51，插件 20:26:27 启动。
- 这一轮（§9.33）：Anki「工具」菜单里插件的 **11 条收成 2 条** —— 顶层留「全局划词入 Anki 设置…」，其余进「单词随身复习」子菜单（立即弹出一张 / 切换词书 / 六级听力 + 分隔线 + 「词书与词表管理」二级菜单装 7 项低频）。**功能一个没删，只挪层**；新离屏检查逐条断言 7 项都还在。
- 这一轮（§9.32）：按 F 出现重影 —— 用户看到的卡是**内嵌**在上一张卡窗口里的，而 `fit_card_height()` 拿 `self` 改尺寸，把内嵌卡片缩得比 host 小，两个面的像素叠在一起。新增 `card_window()`：内嵌时一律操作 `self.window()`，`fit_card_height()` 对内嵌直接返回，宽度兜底也改成加宽 host 并重绘。离屏加了 6b 用例（host+内嵌+按 F），去掉保护会立刻红，证明钉得住。
- **宽度已真屏验收通过**（用户原话「现在可以完整显示了」）：按钮策略 `Ignored`→`Minimum`、评分行居中（A 左空档 = E 右空档）、`row_demand()` 用控件自己 polish 后的字体量、`ensure_row_fits()` 上屏后复核并按需加宽。离屏 19 条检查里有专门钉这几件事的断言。
- 这一轮（§9.31）：① 音量改成**提亮 2.8 kHz + 让出 180 Hz 以下 + 静态幂曲线（drive 上限 1.4）**——真实 SAPI 实测：整体比"被嫌难听"那版低 5.7 dB，而高频相对突出几乎相同（听清而非轰耳）；② 新增 **F 看回题目**（答案仍算已翻面，题目面隐藏评分行）与 **P 回看上一张 / B 更早 / Esc 退出**（只回看、不评分、不动排程，当前卡只 hide 不 close 所以输入状态不丢）；③ 记下硬坑：在 `eventFilter` 里读到尚未赋值的实例属性会**直接 0xC0000409 静默崩进程**，`review_note`/`suppress_speech` 已提到类属性。
- 这一轮（§9.30）：宽度第三轮。真机日志证明**出生时量出来的宽度一定偏小 ~50 px**（隐藏控件的 sizeHint 还没吃到样式表字体）。改三条：按钮策略 `Ignored`→`Minimum`（sizeHint 真正进入布局算术）、评分行**居中**（A 左空档 = E 右空档，用户点名的等距）、`ensure_row_fits()` 在**上屏后**重测并按需加宽（挂在 showEvent，所以翻页不再跳宽）。日志记 `row fit for …` / `card widened at reveal …` 三个数，等用户下次弹卡判定；若 hint 仍偏小就走"按像素反推固定宽度"的确定性路线。
- 这一轮（§9.29）：取证日志把病根钉死了 —— `card sized … width=510 row=492 layout-min=466`，而截图量出评分行真实需要 ~467 px、内容区只有 452 px。原因是宽度用 `self.font()+13px` 量，样式表却用另一套字族画按钮（少算 35 px，离屏永远复现不出来）。现在 `row_demand()` 用**每个控件自己 polish 后的字体**量，且揭晓后再复核一次、装不下就当场加宽（= 用户要的自适应宽度）；离屏新增"故意压窄到 360 px 再翻页，窗口必须长回来"的硬检查。
- 这一轮（§9.28）：评分行在真机仍被裁（离屏复现不出来）→ 宽度不再只靠字号估算：建卡时取 `max(…, Qt 的布局最小值)`，揭晓后 `ensure_row_fits()` 再复核一次，只在真的不够时当场加宽；日志新增 `card sized for …` / `card widened at reveal …` 取证。**用户已把朗读音量存回 100%（= 完全不改，所以现在又回到最初的小声）**，需要 >100% 才生效，实测 240% 与视频对白齐平。
- 这一轮（§9.27）：用户说「新的发音好难听」——原因是渲染级把单词推到满刻度后，mpv 又叠了 ×3 + 限幅。改成**一个信号只有一个杠杆**：本机由渲染级负责（播放器保持 100%，日志 `player 100%, via-file=True`），只有 Anki 本来用 mpv 播语音时才用播放器增益；压缩量改为跟着旋钮（drive 1→2.6，上限是量出来的）。真实 SAPI 渲染实测：240% → RMS -16.1 dBFS（与视频对白齐平）、300% → -14.8（略过），全程零削波。附带好处：不再影响你自己牌组的音频。
- 这一轮（§9.26）：量了插件自己渲染出的真实 wav —— 单词 **RMS -39.1 dBFS**，比视频对白（≈ -16）低约 23 dB，所以只加 mpv 增益根本追不上。现在渲染后本地做「峰值归一到 0.95 + tanh drive 3」，实测单词到 **RMS -13.8 dBFS、峰值 -0.1、零削波（+25.3 dB）**。排版按用户要求再改：答案面「不评分，结束」整行去掉（动作进 ⋯ 菜单，Esc 仍等价），详情区最小高度 120→240 且独占全部拉伸高度。
- 这一轮（§9.25）：找到"音量旋钮空转"的病根——本机单词由 **SAPI 直接对声卡说话**（`chosen=WindowsTTSPlayer`，WinRT 文件语音 rank=None），mpv 滤镜够不到它。现在增益 ≠100% 时插件**用同一个 SAPI 把单词渲染成 wav，再交给 Anki 的文件播放器**，词才真的吃到 `lavfi=[volume=…]`；渲染在后台线程，换卡后过期请求按令牌丢弃。同时修掉三处排版：胶囊不再漂在卡片底部、答案面不再留死高、`E. Mastered` 不再被等分裁字。
- 这一轮（§9.24）：**朗读音量**能调了——Anki 没有音量设置，但它的 TTS 会先写成 wav 再交给每次新起的 `mpv.exe` 播，插件给那条命令行加 `lavfi=[volume=G,alimiter=limit=0.95]`（实测 ×2.50 精确线性、零削波）。设置页「朗读音量」50–300 %，默认 180 %，拖动即时生效 + 「试听」按钮，取消会还原；只改当前会话，不落盘。卡片底部词表归属改成**每本书一个小胶囊**（无中间点、`setIndent(0)` 后 62 px 装 48 px 文字），来源挂到各自胶囊的鼠标提示。**待用户耳朵验收**：真屏上单词是否真的变大了、三个小框是否满意。
- 这一轮（§9.21）：建议评分按题型加权，拼写一次全对 → 建议 E 且回车即 Mastered（选择/听力/填空/反向要 3 秒内，判断题永不）；组间倒计时改成卡片窗口内的覆盖面板；每组 10 张的硬上限全部去掉（固定 1–999，自动按剩余量算），`capacity_shortfall` 改按 Anki 真会给的张数算；选项垂直居中、喇叭 `setIconSize` 并按文字高度定档、卡片宽度按 A–E 与词书标签自动算、`E. Mastered` / 提示 `A–E`。
- 数据事件：16:30→17:05 之间本机删掉 42 条笔记（`graves` usn=-1 证明未上传），我先停后台同步并导出被删笔记，用户确认是自己手动删的，同步已恢复。计数现为 421 / 79 / 18 / 6885。
- 这一轮（§9.19）：后台同步**不再可能弹模态框**——失败只记日志 + 一次非模态提示，并且一次失败就停表；顺带修掉「没登录也照同步」的老 bug 和「只剩引用的卡也算在屏 → 关闭变隐藏 → 僵尸」，重启工具学会唤醒并关闭被隐藏的主窗口（15:02 那次 22.6 秒正常退出，未用 `/F`）。
- 这一轮（§9.20）：卡片从 `Qt.Tool` 改成普通窗口（任务栏两个独立条目、点别处不再消失）；取消置顶显式改 Windows 的 topmost band；图钉改成 45° 实心/空心两态；按钮 `E. Mastered`、提示 `A–E`；置顶不再写回设置（每张新卡默认置顶）；`verify-state` 的 on-screen 层改成真采样像素（原来查 LogonUI 进程会误报锁屏）。
- 重启由 `tools/restart-anki.py` 完成（用户已授权 AI 自己判断，不必再问）。第一次真跑：先关掉一张 122 秒没人动的卡，然后 WM_CLOSE **1.7 秒**退出，重启后卡片计数一字不变（470 / 103 / 11 / 6927）。
- 备份：`pre-deploy-20261102-144909/`（同步静默）、`pre-deploy-20261102-150052/`（可见性判定）、`pre-deploy-20261102-154939/`（窗口与图钉）。
- 待用户真屏看一眼的：任务栏是否出现两条独立窗口、点别处卡片是否还在、图钉实心/空心两态、`E. Mastered`、圆形喇叭、隐藏主窗口、组间 3 秒倒计时。
- D 剩下的：窗口拖动吸附屏幕顶/任务栏自适应高度；听写第 3 遍显示音标。（E「TTS 音量」已做，见 §9.24，不再需要用户同意。）
- 之前几轮已做完并部署：已掌握原地换卡（不关窗再弹）；后台静默同步（关掉 Anki 的开/关时同步，空闲时每 N 分钟走 `mw.on_sync_button_clicked()`，原值记在 `anki_auto_sync_remembered`）；卡片在屏时点主窗口关闭只隐藏（设置「关闭主窗口」，卡片菜单「隐藏 Anki 主窗口 / 退出 Anki」）；选项框靠 `WA_StyledBackground`。
- 这一轮：评分行改 `A. Again / B. Hard / C. Good / D. Easy / E. Mastered`（折叠时 `A. Again 并继续 / B. 继续学习`），并修掉「加字母后答案面把卡片从 510 撑到 661」；所有小喇叭把圆盘画进图标（CSS 圆角在这套 Qt 上不生效）；「已掌握」颜色与其他按钮一致；真关闭前先停提醒定时器（否则关窗期间弹卡会把 Anki 卡在半关状态）。

## 4. 产品方向（已拍板，别再改）

用户原话："我只是希望选择一个词组，比如我想学六级词汇……学习过程中我是知道当前的学的是哪一部分的单词的。"

- **词书 = 视图**。菜单里 6 个具名词书（`review_logic.STUDY_BOOKS`）：六级核心 / 六级全表 / 四级核心 / 四级全表 / 六级词表(KyleBing) / 文献单词。
- 一张卡只能属于一个牌组，所以**嵌套关系（核心 ⊂ 全表）用标签，独立范围用牌组**。
- 设置页是一个单选列表（`studyBookList`），只列当前账户里真实存在的词书。
- 工具栏与菜单项都显示"开始学习 · <词书名>"；卡片眉标显示 `词书 · 已学/总数 · 新词/到期复习`。
- 用户明确拒绝过"牌组+标签拼接"（原话"不要拼，给我菜单"），**不要退回**。
- **熟练词的处理已拍板**（2026-11-02，2026-11-04 细化）：卡片底部「已掌握，不再学」= 挂起 + `zvr_mastered` 标签，不写评分。**拼写题（typing）**：零提示一次写对 → 建议「已掌握」，E/回车即标记；用过提示才按提示种类分档 —— 1 次发音 = Easy、2 次 = Good、≥3 = Hard；空格字母提示按 `1/(i+1)` 位置加权算"已给出比例"，≤20% Easy / ≤40% Good / ≤70% Hard / 更多 Again；释义或例句提示仍 = Hard。其他题型维持"用过提示即 Hard"，答对零提示仍是 Easy。**不要把建议分上限改回「记住了」，也不要回到"任何提示一律 Hard"。**
- **组间必须问一句**（2026-11-02，2026-11-04 改版）：一组结束弹 3 秒倒计时，面板上写大字 **`按 Enter 进入下一组学习`**（20px 粗体 `#breakHint`），回车/点击进下一组，不按就结束。不要恢复"自动进入下一组"的静默翻页。面板出现时必须**禁用底下的字母框**——`QLineEdit` 会吃掉 Enter，否则那句提示对刚打完字的人不成立。
- **同步走后台**（2026-11-02）：本插件把 Anki 的「打开/关闭时同步」关掉，改在空闲时后台同步；恢复时只还原我们亲眼看到的那个值。不要把它改回开/关时同步，也不要在未登录同步账号时弹登录框。
- **动效只在拼写题、只往前不挡手**（2026-11-04，AUDIT §9.37）：中文徽章（不可思议/完美/很棒/不错），答错与其他题型一律不庆祝；**不要**改回英文大喊，**不要**恢复整卡 ±2px 震动，**不要**为了"放大单词"去改布局内控件的 geometry（会触发重排，把 §9.29–§9.30 的行宽算术全打回去）。庆祝层是 raise 起来的子控件，卡片 `hideEvent` 必须停它。总时长 ≤980ms，翻页不等动画。
- **2026-11-17 当前状态**：85158043 已禁用；无复习卡时点 X 已实测真正退出。下面这条「关主窗口 ≠ 退出」保留为禁用前的历史规则；`restart-anki.py` 的 quit-request 路径继续兼容旧环境。
- **关主窗口 ≠ 退出**（2026-11-02 定，2026-11-04 由用户更正）：用户装了 Minimize to Tray 2，**就是要 Anki 在后台常驻**。所以：卡片在屏时我们自己隐藏主窗口并留住卡片；没有卡片时把关闭交还给托盘插件，**两个定时器都不许停**（停了就是"闷着不弹卡"一小时那次事故）。真退出只有托盘那套协议：`mw.closeEventFromAction = True` + `mw.close()`（我们的「退出 Anki」菜单项和 restart 工具都走它；`guiExitAnki` 无效，别再试）。
- **任何换卡都必须是原地换卡**（评分、已掌握都一样）：新卡嵌在同一个窗口里，不允许"关掉再隔一秒开一扇新窗"。
- **内嵌的卡片不许改自己的尺寸**（2026-11-03，按 F 出现重影）：用户看到的卡通常 `setParent(host, Widget)` 嵌在上一张的窗口里，尺寸归 host 管；要改窗口大小必须走 `card_window()`（内嵌时是 `self.window()`），否则卡片会比它的窗口小，两个面的像素叠成重影。改高度/宽度的任何新代码都要先问"这张卡是不是内嵌的"。
- **卡片是普通窗口，不是 Qt 工具窗口**（2026-11-02）：`Qt.Tool` 没有任务栏按钮、且应用一失焦就被 Windows 藏掉，用户会"找不到弹窗"。主窗口与卡片必须是任务栏上两个独立条目。
- **置顶只作用于当前窗口，不写回设置**（2026-11-02）：每张新卡默认置顶；取消置顶保持到本窗口结束。清掉 `WindowStaysOnTopHint` 还不够，必须显式 `SetWindowPos(HWND_NOTOPMOST)`，否则 Windows 仍把它留在 topmost 带里。
- **评分行用 Anki 原生英文 + 字母**：`A. Again / B. Hard / C. Good / D. Easy / E. Mastered`，提示语写 `A–E`。
- **每组张数不设上限**（2026-11-02）：固定模式 1–999 由用户填，代码里不许再 `min(10, …)`；自动计划按「今日剩余 ÷ 学习时段」算。真正的天花板是牌组的 `new/day`（实测五个牌组都是 40），要动它必须先问用户。
- **Mastered 的判定按题型难度**（2026-11-02，用户原话"拼写出来应该是最难的一类的""三秒内选择出了正确答案"）：拼写全对不限时；选择/反向/听力/口语/填空要 3 秒内；判断题永不。命中时回车即执行 Mastered。
- **组间倒计时必须在卡片窗口内**（2026-11-02，用户原话"沿用我们的原来的卡片窗口……实现无感切换"）：不许再弹第二个窗口。
- **音量靠给 Anki 自己的播放器加增益，不动系统**（2026-11-02，用户原话"声音太小了…可以调节音量大小"）：旋钮是"朗读音量 %"，100% = 完全不加滤镜。不许改 Windows 系统/单应用音量、不许写 `Anki2/mpv.conf` 之类的用户配置文件、不许伪造 per-file 音量。高于 100% 必须带限幅器防削波。已知副作用：增益挂在播放器上，对本会话播放的所有音频生效（README 已写明）。
- **先问 Anki 谁在说话，再决定怎么放大**（2026-11-02，用户原话"没有感觉音量变大，不够大"）：这台机器 `chosen=WindowsTTSPlayer`（SAPI 直接发声，Volume 已顶在 100%），所以增益必须靠"渲染成 wav → 走文件播放器"才落地。以后换机器/换 Anki 版本，先看日志 `tts routing:` 那行的 `chosen=` 与 `via-file-speech=`，不要假设单词一定经过 mpv。
- **音量目标 = 压过系统里其他声音，不是"相对 Anki 变大"**（2026-11-02，用户原话"我希望 anki 的发音超过视频的声音"）：SAPI 的单词只有 RMS -39 dBFS，靠播放器增益追不上，必须在渲染阶段把语音推到接近满刻度。不许用提高系统音量的办法糊弄，也不许硬削波。
- **一个信号只能有一个放大杠杆**（2026-11-03，用户原话"新的发音好难听啊"）：渲染级负责响度时播放器必须留在 100%，反之亦然；两级叠加会把满刻度信号再顶给限幅器，听感发扁。压缩量跟着"朗读音量"旋钮走（drive 1.0→2.6，上限是实测出现削波之前），不许写死最大值。
- **响度换清晰度，不换压缩**（2026-11-03，用户在两个选项里明确选了"提亮语音高频，不加大压缩"）：2.8 kHz 提亮 + 180 Hz 以下让路 + 静态幂曲线，drive 上限降到 1.4。不许再用"压得更狠换更高 RMS"的路子；要更响只能让用户自己调旋钮，不许偷偷提高上限。
- **回看只看不改评分**（2026-11-03，用户在"只回看 / 撤销评分重做"里选了只回看）：已评分的卡上不许出现评分行，回看不发声音、不动 Anki 排程；当前卡只 `hide()` 不 `close()`，输入状态不许丢。"撤销评分重做"这条**没有获得授权**，不要实现。
- **卡片按键表**：A–E 评分 / Enter 继续 / Space（口语与听写）/ Esc 不评分结束 / Ctrl+V / Backspace / 左右键 / **F 看回题目** / **P 回看上一张** / **B 回看更早**。F、P、B 只在答案面接受——拼写题在题目面必须把字母留给输入。
- **词表归属 = 每本书一个小胶囊**（2026-11-02，用户原话"四级词表应该使用一个小框……中间的那个点去掉，框小一点，比文字适量大一些就可以了"）：不要长标签、不要分隔点、不要为省地方截断；来源信息进各自胶囊的鼠标提示，不印在卡片上。
- **庆祝长什么样，由用户给的参照物定，不由我猜**（2026-11-04，用户在否掉四版之后甩来六张真实三消素材 +「可以参考这种，你做好弹出动效和有的地方需要透明处理」）：金色立体挤出字 + 奶白轮廓 + 放射光 + 三星 + 缎带压宝石。**庆祝窗内只有一个等级英文词，不许有汉字**（2026-11-04 用户看完真屏后原话「弹出的庆祝窗口不要汉字」）——缎带留空，`TIER_LABELS`/`tier_label()` 已删除，别再把它加回来；卡片自己的「回答正确」和建议说明行是另一段文字，仍是中文，不属于庆祝。这两条一起推翻了 §9.37 里"徽章必须中文"的旧决定，旧决定已就地改写，不要拿它当现行规则。月桂花环实现了但暂时不画（和放射+三星+缎带同开会散成沙粒），`_laurel` 注释里写了什么时候该放回来。
- **动效是两个独立开关，不是一组单选钮**（2026-11-04，用户原话「在设置里增加开关是否使用弹出庆祝特效」）：`review_motion_hop`（字母跳动）与 `review_motion_celebration`（弹出庆祝）各自决定 `timeline()` 里有没有那几步。三档单选钮表达不了"字母别跳但庆祝留着"和"庆祝关掉字母照跳"，所以整组删掉，`MODES`/`DEFAULT_MODE`/`motion_mode()` 一并删除。**兼容不许变成惊喜**：两个新键从未写过时回落到读旧 `review_motion`（`off`→全关，其余→全开），保存时不再写 `review_motion`，`windows-core-settings.py` 钉住这两条以及"旧单选钮文字不许再出现在设置页"。
- **庆祝层不许覆盖卡片信息**（2026-11-04，用户原话"有的地方需要透明处理"）：只画形状，四周一个像素都不许吃。三条硬规矩——径向渐变最后一个色标必须 alpha=0；扁椭圆里的圆渐变要缩放 painter 而不是缩放形状；放射楔形不许从正圆心起画。验收不许靠"看着没有"，`windows-card-motion.py` 逐像素断言四档位六个边角 alpha==0、字心不透明、被画面积小于半张卡。锚点 0.60（卡片高度六成）来自 `tools/probe-card-geometry.py` 的逐行占用扫描，不许凭感觉挪回去。
- **动效的数字全部留在 `card_motion`**（2026-11-04）：`badge_pose(progress, tier)` 是唯一出口，Qt 层只负责 apply。理由：能不带窗口测，且"太闪""挡回车"这类抱怨有地方钉住。新增装饰档位判定同样归 `card_motion`（`shows_rays`/`shows_stars`/`sparkle_count`），因为 tier 1 是最高档、4 是最低档，绘制层自己写比较号已经反过一次。
- **庆祝窗放在卡片正中央，位置由用户定，代价要写出来**（2026-11-04 原话「弹出的庆祝窗口的位置应该在我们的卡片的中央位置」）：`BADGE_TOP_FRACTION = 0.50`。这个数翻过三次（0.24 盖住被庆祝的单词 → 0.68/0.60 移到报告行 → 0.50 中央），前两次都只有"看着不对"没有断言，所以这次同时钉住**单词行与评分按钮行在庆祝期间必须逐字节不变**（`windows-card-motion.py` 3c）。中央的已知代价：解释框下沿和例句框中部会被盖约一秒，例句关键词也在内——这是用户选"中央"时接受的，别再自作主张挪回下三分之一。**判据只能用可见控件**：字母框 `letter_boxes` 属于题目面，在答案面上隐藏、几何是陈的，拿它当"单词在哪"会在错误的行上报错。样片/探针工具不许抄一份锚点数字，必须读 `motion_view.BADGE_TOP_FRACTION`。
- 设计锚点：`spark-output/context/frame.json`；决策与理由：`AUDIT-2026-10-30.md` §9。

## 5. 待办（严格按顺序）

**0. 先部署本轮（#65 + #66，代码已绿、未部署）** —— 备份并拷贝 `morphology.py` `review_logic.py` `review_popup.py` + `lexicon/syllables_supplement.txt` 到安装目录 → `python tools/restart-anki.py --wait 300` → verify-state 五层全绿 + **手动核 `syllables_supplement.txt` 哈希**（面板不查词典）+ 重启前后卡片计数 unchanged → 真机验收分词与评分手感。`kyle_enrich.py` 仍 ABSENT，真题合规未定，**不要顺手部署**。后续可继续批 `prepare_question`（仍 ~2.4s/11–12 次）。

**A. 先收尾** —— 已真屏验收通过（2026-11-02 截图 + 日志）。只剩重启后复验眉标「已学/总数」在每组第二张之后也在。

**B. 视觉** —— 四条已做并部署：选项改成字母独占一列 + 释义换行的悬挂缩进（不再 45 字截断）；听写页重播按钮换成同款 32×32 圆形扬声器；选择题单词与音标居中；词表归属改成卡片底部小圆标签、卡片上不印「来源」（来源进鼠标提示）。**待重启真屏验收**，看用户是否认可换行后卡片变高。

**C. 节奏** —— 已做并部署：换卡/关卡片立即停语音；评分后立即翻页、后台保存、成功静默、失败才报错。**待重启后真屏验收翻页手感。**

**D. 新功能（都已批准）**
窗口上下拖动时吸附屏幕顶部/任务栏自适应高度；卡片右上角"置顶"开关；听写第 3 遍回车后显示音标；~~听写与填空考**动词原形**~~ —— **填空已改为考原形并全库审计完（2026-11-02，见 AUDIT §9.23：6885 条里 1420 条例句用变形，清单在 `design/cloze-inflected-forms.tsv`）**；听写（listening）本来就按原形判，无需改。剩下的：~~拼写题动效样稿已交付待批~~ —— **已批准并实施（2026-11-04，AUDIT §9.37）**。

**E. 阻塞，需先问**
TTS 音量偏小。Anki 没有音量参数（`aqt/tts.py`、`aqt/sound.py` 均无），唯一路径是 Windows 单应用音量，属系统改动——先问，不要自己改。

## 6. 踩过的坑（别重踩）

- AnkiConnect 只认 `127.0.0.1:8765` 的 **camelCase** action，且要绕开 `HTTP_PROXY=127.0.0.1:7890`。
- Anki 的 `tags` 表**没有 `name` 列**（是 `n`）。用 `mw.col.tags.all()`。直接写 SQL 查会 DBError——之前就是这么把设置里的标签列表弄空的。
- `front:` 别名**不认中文字段名**（正面），静默返回 0 条。按真实字段名写。
- `deleteDecks` 的参数是 **`cardsToo`**，不是 `cards`。`notesInfo` 返回 **`noteId`**。
- 不要跑 `clearUnusedTags`：账户里有 9 个 0 笔记标签，其中 5 个是用户自己的。
- Anki 关不掉时（`WM_CLOSE` 只隐藏窗口、WAL 不落盘），先确认 AnkiConnect 仍活着、牌组计数未变，再考虑强杀。**不要自己决定重启用户的 Anki。**
- PyQt6 离屏测试：必须先预载字体、只建一个 `QApplication`、stub 掉 TTS，否则段错误或静默 abort。
- Anki 的 `prop` 条件只有一个冒号：`prop:reps>0`。`prop:reps:>0` 是解析错误，假 api 测不出来。
- **Python 里调 `tasklist` 要写 `/FI`，不是 `//FI`**：后者是 Git Bash 的转义习惯，传给子进程会让 tasklist 失败，看起来像「Anki 没在跑」。
- **ctypes 枚举窗口必须先设 `argtypes`/`restype`**，否则 64 位下 HWND 被截断，`EnumWindows` 报告「一个窗口都没有」，空闲检查就废了。
- **AnkiConnect 的 `guiExitAnki` 在 Anki 26 上是空操作**；能关的是 WM_CLOSE（`taskkill /PID`）。而关闭慢的原因是 Anki 自己的「关闭时同步」——本插件已把它关掉（见 AUDIT §9.15）。关窗期间到点的自动弹卡会把 Anki 卡在「主窗口没了、进程还在、只剩卡片」，所以真关闭前必须先停提醒定时器。
- **样式表的 `border-radius` 在 Anki 26 自带的 PyQt6 + Windows 原生 style 上对 32px 的 QPushButton 不生效**（最小复现：角上像素仍是填充色，改 padding/border 都没用）。要圆形就把圆画进图标位图，别指望 CSS。
- **翻页后的卡片是 `setParent(host, Widget)` 的子控件**，对子控件设窗口标志是空操作；置顶这类开关必须作用在 `self.window()` 上。
- 离屏检查里 mock 出来的 plan 必须带全真代码要读的字段。`windows-dynamic-plan.py` 过去只给 `{'batch':6}`，真代码在 `current_plan['new_remaining']` 上抛 KeyError、被它自己的 `except` 吞掉，于是“下一张卡”这条路径从来没跑到，测试却一直绿。改这条路径前先确认 mock 返回值能让代码走到你要验的那一行。
- 想把分数写成“后台保存”，就必须先拆掉 `_answer_on_main` 里 `self.dialog is not dialog` 这道闸：卡面已经翻页，这道闸会让每一次后台保存都失败。防重复写靠 generation、账户对象、卡片快照三层，不靠“当前显示的是不是这张卡”。
- 翻页比保存快，Anki 的当日额度就会慢一拍：不扣掉“正在写的那一张”，下一张会照常发出来，等用户答完才被 `submit_review` 以「今天的复习额度已用完」退回。`prepare_question` 用 `_review_inflight_new/_review_inflight_due` 两个键把这一张预先扣掉。
- **绝对不要在 Qt 的信号槽里同步调 AnkiConnect 的写操作。** UI 线程会卡在 HTTP 应答上，而 Anki 要等 UI 线程空出来才能处理那个写请求——自己锁死自己（点「已掌握」卡死就是这么来的）。写操作放工作线程，用信号回到主线程收尾。
- **抓 Merriam-Webster 只有 `mcp__windows_mcp__Scrape` 能过**（WebFetch 和 curl 都 403）。MW 词头每个中点 U+00B7 后带一个零宽空格 U+200B；Cambridge / dictionary.com 词头不带点（只有 IPA 带点），Collins curl 403。抠带点词头时正则要把 `\u200b?` 算进去。
- **死掉 agent 的工具结果还能抢救**：完整输出在 jsonl user 行的顶层 `toolUseResult` 字段（`message.content` 的 tool_result 可能是截断副本）。JSON 转义的 `\n` 会把字母 n 粘到下一个 token 头上，分词前先 `blob.replace('\\n',' ')`（用 lookbehind 挡字母反而更糟）。脚本 `tmp/salvage_agent_evidence.py`。
- **AnkiConnect `multi` 按序返回纯结果列表，不是 `[result, error]` 对**；批量只读用它，异常或结果数不够要回落串行。`_multi` 在 `review_logic.py`。
- **`verify-state` 部署层只哈希顶层 `*.py`，不查 `lexicon/` 数据文件**：新增/改词典补充文件后面板会假绿，部署后必须手动比对哈希。
- **`windows-judgment-rows.py` 是计时敏感的离屏检查，全量里偶发一次红**（单跑与复跑都绿）。看到 33/34 先单跑这一条复现，别当成回归。

- **推 GitHub 失败有三种形态，都不是凭证问题**：`Failed to connect ... Could not connect to server`（连不上）、`the remote end hung up unexpectedly`（能握手、传到一半断）、`Recv failure: Connection was reset`（握手中断）。同一天内三种会交替出现，说明是链路对 GitHub 的间歇干扰。`http.postBuffer` 对 reset 无效（2026-11-20 实测）。
- **推送重试才是正解**：每 2 分钟一次、最多 5 次，2026-11-20 两次都是前 4 次失败、第 5 次通过；判据只看 `git rev-list --count origin/<branch>..HEAD` 是否为 0，**不要相信输出里的 `Everything up-to-date`**（它曾与 fatal 同时出现，实际 ahead=1）。本机 SSH 备选已排除：`github.com:22` TCP 不通；`ssh.github.com:443` 虽 TCP 可达，`ssh -p 443 -T git@ssh.github.com` 仍 `exit=255` 且无输出 —— 遇到推送失败别浪费时间切 remote。

## 7. 红线（用户原话，逐条遵守）

- 源码工作区有大量未提交和未跟踪的项目文件，请保留，不要直接清理、重置或覆盖。
- 不要自行关闭或重启用户正在使用的 Anki；安装代码前备份受影响的插件文件。需要重启才能加载新代码时，明确告知。
  - **2026-11-02 更新（用户原话「关闭并且重启anki的操作能不能由你进行，以后」→「不需要我手动给你说，你自己判断」）**：重启由 AI 负责并且**自己判断时机**，不要再问。协议见 `tools/restart-anki.py`：空闲（没有卡片在屏 + 日志静默 ≥25 秒）就动手；卡片 90 秒没人动就当作 abandoned，先按「不评分」关掉它再重启；只发 WM_CLOSE，只有 150 秒无效且一个窗口都不剩才允许 `/F`；重启前后比对卡片计数。- 调试时区分：源码已修改、测试通过、文件已部署、真实 Anki 已加载、真实界面已验证。这些不是同一件事。
- 使用 AnkiConnect 或 Anki API 修改用户数据前，先只读核对当前账户和笔记类型；记录新增与标签变更。不能覆盖已有卡片释义、复习历史或个人配置。
- 外部词表和真题要保留来源与许可信息。不要把本地下载的第三方真题音频或未经核实授权的材料打包公开发布。
- 复习评分和后续复习时间由 Anki 原生调度器负责；不要自行伪造 FSRS 排程。不要未经确认改动全局 FSRS 或其他账户级设置。
- 不要擅自调整用户牌组或账户级排程；应先检查并清楚呈现限制。
- 不要为了测试随意更改用户真实学习记录，可先用隔离测试账户或临时测试牌组。
- 用户偏好你自主完成已经授权的本地配置、修改和验证；只有确实需要用户做出选择、登录授权或存在不可逆影响时才询问。
- 完成后简洁说明：改了什么、原因、测试结果、实际部署状态、仍未验证的部分和用户如何使用。

## 8. 第一次回复的要求

不要长。说清三件事：`verify-state` 现在显示什么（当前应是 3 个 DRIFT 文件 + 真机跑旧码、闸门已绿）、本轮 #65/#66 卡在哪一层（源码已改/测试通过/未部署）、你打算先动哪一件（按 §5 第 0 步：备份→部署→重启→五层验证+手动核词典哈希→真机验收）。然后开工。

现状只认一个入口：`AUDIT-2026-10-30.md` 的 **§9**（§1–§8 是历史），最新两条是 **§9.50（分词）/ §9.51（卡顿）**。动手前读完 §9。
