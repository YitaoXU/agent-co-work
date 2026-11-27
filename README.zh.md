[English](README.md) | 中文 | [概览网页](https://yitaoxu.github.io/agent-co-work/)

# agent-co-work

一套可移植的多智能体协作套件，适用于类 Unix 主机（macOS/Linux）上的任意项目目录，基于 Herdr（`hc`）与单个标准库 Python CLI（`cw`）构建。
你与协调员商定方向、批准每个任务、裁决重大问题，并审阅协调员给出的结论优先摘要；顾问按需提供审阅。
任意席位都可运行任意受支持的 agent CLI（`claude`、`codex`、`agy`）；三 agent 配置仅作示例，权威协作规则以 [cowork 技能](skills/cowork/SKILL.md#task-loop) 为准。

## 开始之前

使用 macOS 或 Linux。**你无需自己运行 `cw` 或 Python**：与协调员讨论工作、审阅计划并确认修改即可。

1. **安装 [Herdr](https://herdr.dev/download/)。** Apple silicon macOS 可下载 [DMG](https://releases.herdr.dev/app/Herdr.dmg)，将 Herdr 拖入 Applications。macOS 或 Linux 也可运行安装器：

   ```sh
   curl -fsSL https://releases.herdr.dev/app/install.sh | sh
   ```

   打开 Herdr 终端，检查 `hc --version`，确保 `~/.local/bin` 在 `PATH` 中（或使用自定义的 `HC_INSTALL_DIR`）。macOS 的终端隐私权限应授予 **Herdr Core**；已有 Herdr.app 权限不会自动转移。
2. **安装并登录至少一个 agent CLI：** `claude`、`codex` 或 `agy`。它就是你的协调员；只装一个也可以，协调员会检测已安装 CLI，再从可用项中推荐席位。
3. **安装 `python3` 3.9+ 和 `git`**（macOS 可通过 `xcode-select --install` 获取）。
4. **GitHub 访问：** 仓库公开后无需额外凭据（公开 kit 使用 HTTPS `git clone`，不需要 GitHub 密钥）；仓库私有期间需要你自己的常规 GitHub 凭据。

## 启动第一个协调员

打开 Herdr，点击标签栏的 **`+`**，选择项目文件夹。在新标签页中启动协调员 CLI：

```sh
claude
```

要用其他 CLI，把 `claude` 换成 `codex` 或 `agy` 即可。会话命名可选（Claude Code：`claude -n yyyymmdd-coordinator`）。然后粘贴下方协调员提示词，填写 `<project description>`。

### 协调员提示词

```text
在这个项目中安装或升级 agent-co-work。首次安装时，若 ~/.agent-co-work
不存在，运行：
git clone https://github.com/YitaoXU/agent-co-work.git ~/.agent-co-work
否则用 git -C ~/.agent-co-work pull --ff-only 更新发布 clone。
已有安装使用 cowork/cw upgrade 拉取并显示计划；若没有此命令，按
cowork-init 的旧版引导流程操作。
阅读 ~/.agent-co-work/skills/cowork-init/SKILL.md。检测已安装的 agent CLI
和模型，只用可用项提出推荐席位表，然后问我保留默认值 / 调整席位。
需要调整时，每个席位问一个问题：默认配置 / 自填 agent model effort [life]。
展示完整席位表、文件计划和 kit SHA。等我确认后再应用，然后运行
cowork/cw lint 核对 SHA。使用以下描述准备项目的 Direction 和 Plan。

<project description>
目标：
当前状态：
关键文件夹与文档：
首先要做的事：
```

## 接下来做什么

- **确认席位与安装计划（新项目）：** 审阅协调员根据已安装 CLI 给出的推荐席位（包含 `discussion`）。选择**保留全部默认值**或**调整席位**（每个待调整席位选择默认配置，或根据列出的合法值填写 `agent model effort [life]`）。然后确认完整席位表、文件计划和 kit SHA，待协调员应用后再对照计划核对安装 SHA。
- **升级已有项目：** 告诉现有项目的协调员**升级（upgrade）**，审阅它展示的升级计划与 kit SHA，确认后再应用，并核对安装后的 SHA 与已确认计划一致。
- **请求讨论席位：** 请协调员打开一个讨论席位（可指定希望使用的 agent），切换到它告知的 Herdr 标签页直接讨论。需要它编辑项目文件时明确提出；结束讨论时告知它，由它向协调员汇报结论和未决问题。
- **批准 Brief 与决策：** 向协调员提供项目描述，讨论 Direction 和 Plan，在每个任务启动前批准 Brief，裁决上报的重大问题，并审阅协调员简短的结论优先 Wrap-up 摘要以确定下一步。
- **离开期间继续工作：** 告诉协调员你大约会离开多久，回答它的问题，然后说 **go** 批准[离开计划](skills/cowork-away/SKILL.md)；回来后阅读摘要。

## 席位配置

任意席位都可运行任意受支持的 CLI（`claude`、`codex` 或 `agy`）；Claude、Codex 或 agy 均可单独使用，协调员会只用你已安装的 CLI 提出推荐席位表。每格依次列出 `agent model effort life`。

| seat | 纯 Claude | 纯 Codex | Claude + Codex | Claude + agy + Codex（默认配置） |
|---|---|---|---|---|
| `coordinator` | `claude claude-opus-5-5 high long` | `codex gpt-6-astra high long` | `claude claude-opus-5-5 high long` | `claude claude-opus-5-5 high long` |
| `coordinator-alt` | `claude claude-opus-5-5 high long` | `codex gpt-6-astra high long` | `claude claude-opus-5-5 high long` | `agy gemini-4-neon-xhigh xhigh long` |
| `advisor` | `claude claude-opus-5-5 high short` | `codex gpt-6-astra high short` | `claude claude-opus-5-5 high short` | `agy gemini-4-neon-xhigh xhigh short` |
| `worker-heavy` | `claude claude-opus-5-5 high long` | `codex gpt-6-astra high long` | `codex gpt-6-astra high long` | `codex gpt-6-astra high long` |
| `worker-light` | `claude claude-opus-5-5 high long` | `codex gpt-6.1-sol max long` | `codex gpt-6.1-sol max long` | `codex gpt-6.1-sol max long` |
| `auditor` | `claude claude-opus-5-5 high long` | `codex gpt-6-astra high long` | `codex gpt-6-astra high long` | `codex gpt-6-astra high long` |
| `discussion` | `claude claude-opus-5-5 high long` | `codex gpt-6-astra high long` | `claude claude-opus-5-5 high long` | `claude claude-opus-5-5 high long` |

> **提示：** `codex` 或 `agy` 协调员需要在沙盒外运行 `hc` 和 `git`，弹出相应权限提示时请批准。

## 工作原理

<details>
<summary>核心概念、运行流程图与默认项目布局</summary>

### 核心概念

- **项目（Project）**：记录在 `cowork/projects/<name>.md` 中的长期工作（`status: active|closed`，包含 `Direction`、`Plan`、`Resources`、`Decisions`），由协调员维护。独立任务可不关联项目。
- **任务（`kind: task`）**：以用户决策收尾的工作单元，运行在 `main` 或 `side` 线上（或 `-`）。每个任务启动前都必须获得用户批准，多个已批准任务可并行推进。
- **步骤（`kind: step`）**：任务内部的具体工作（评审、实现、审计、修复、检查），可记录在任务的 `State` 中，也可新建带 `parent: <task>` 的独立步骤文件。协调员会话使用 `kind: seat`。
- **席位（Seats）**：`cowork/seats.tsv` 中定义的命名角色（`coordinator`、`coordinator-alt`、`advisor`、`worker-heavy`、`worker-light`、`auditor`、`discussion`），将各角色映射到受支持的 agent CLI、模型、推理强度（effort）、生命周期（`short` 子终端或 `long` 无父终端），以及可选的带引号额外 CLI `args`。
- **`cowork/` 文件**：`cowork/cw`（内嵌独立 CLI）、`kit-version`（已安装 kit 的提交和来源）、`seats.tsv`（席位表）、`coordinator.addr`（当前活跃协调员终端 ID）、`README.md`（自动生成的总览）、`projects/<name>.md`、路径永不迁移的每日任务记录 `yyyymmdd/<task>.md`、`locks/<resource>` 与 `lessons/`。

### 运行流程

```mermaid
flowchart TD
  D["商定 Direction"] --> P["协调员起草 Plan / Brief；按需由顾问审阅"]
  P --> U["用户批准任务"]
  U --> W["执行任务；优先分离修改范围，文件重叠时用 worktree"]
  W --> R["汇报与证据；协调员选择审查层级"]
  W -.->|"重大问题"| Q["用户决策"]
  Q -.-> W
  R --> L["记录 / 文档：协调员检查"]
  R --> O["普通代码：执行席位测试 + 差异审阅"]
  R --> A["关键路径：新会话审计员运行检查"]
  R --> G["计算实验：启动前审阅 + 执行席位早期验收"]
  L --> K["协调员验收；需要时按明确路径提交"]
  O --> K
  A --> K
  G --> K
  K --> S["简短 Wrap-up 摘要；用户决策；调整 Plan"]
  S --> P
```

`cw start` 检查任务及父任务的批准关卡；`cw new --worktree` 创建 `.worktrees/<task>` 和任务分支，通过 `COWORK_ROOT` 将记录保留在主检出中；详见技能中的 [审查与 Git 规则](skills/cowork/SKILL.md#escalation-and-review)。

### 默认项目布局

项目可在 `AGENTS.md` 中声明文件存放覆盖规则，安装不会搬动现有文件。忽略的证据是本地文件，备份由项目负责。

| 路径 | 内容 | 首次安装时 Git 跟踪 | 持久证据 |
|---|---|---|---|
| `docs/` | 日常指南、设计、已接受结论 | 跟踪 | 是 |
| `docs/plans/` | 编号计划、长 Brief、README 索引和 Brief 模板 | 跟踪 | 是 |
| `docs/archive/` | 过时文字稿的带日期汇编 | 跟踪 | 是 |
| `cowork/` | 每日记录、项目、席位、锁、教训 | 忽略 | 是，本地记录 |
| `output/<yyyymmdd>/<task>/` | 结果、审计发现、日志、汇总的 `log.md` | 忽略 | 是，保护引用路径 |
| `.scratch/` | 主机本地操作回执、调度文件 | 忽略 | 仅操作回执 |
| `.tmp/` | 可丢弃的克隆、沙箱、探测 | 忽略 | 否，先导出必要证据 |
| `.worktrees/` | 可选的隔离检出 | 忽略 | 否，合并或结项后清理 |

各类文件的生命周期、建议长度和历史位置见 [归纳技能](skills/cowork-consolidate/SKILL.md)。

</details>

## Agent 参考

<details>
<summary>协调员命令、安装与升级细节、席位参数、讨论席位机制、资源与锁、记录与交接、无 Herdr 模式、故障排查、命令参考与已知限制</summary>

### 协调员执行的命令

这些是协调员的命令参考：在项目根目录，以沙盒外的正常权限运行。你只需审阅并确认产生的计划。

```sh
# 首次安装：仅克隆一次；已有固定发布 clone 时更新。
git clone https://github.com/YitaoXU/agent-co-work.git ~/.agent-co-work
git -C ~/.agent-co-work pull --ff-only
python3 ~/.agent-co-work/bin/cw init --seat worker-heavy=codex:gpt-6-astra:high:long
# 确认席位表与计划后，原样重复选定的 --seat 参数：
python3 ~/.agent-co-work/bin/cw init --seat worker-heavy=codex:gpt-6-astra:high:long --apply
cowork/cw lint

# 已有安装：先生成计划，确认后再应用。
cowork/cw upgrade
cowork/cw upgrade --apply

# 仅在旧 cw 没有 upgrade 命令时使用旧版引导：
git -C ~/.agent-co-work pull --ff-only
python3 ~/.agent-co-work/bin/cw init --upgrade
# 确认后：
python3 ~/.agent-co-work/bin/cw init --upgrade --apply
cowork/cw lint
```

`upgrade --kit <dir>` 可指定其他发布 clone（默认 `~/.agent-co-work`）；计划与应用需使用同一选项。`--seat` 的 `=` 后恰好接四个字段。可选 `args` 在安装后用 `cw seat set --args='...'` 配置；不得在整个席位上设置 `-a never`。

### 安装细节

固定在 `~/.agent-co-work` 的发布 clone 供所有目标项目共用。新项目中，协调员会在 `~/.agent-co-work` 克隆或更新发布版、阅读 `cowork-init` 技能、检测可用 CLI 和模型、使用 `python3 ~/.agent-co-work/bin/cw` 安装，并用 `cowork/cw lint` 检查安装版本。升级使用 `cowork/cw upgrade`，后者调用发布 clone 当前的 CLI 和资源。

**席位**：根据已安装的 CLI 查看[选择席位](#选择席位)与[席位配置](#席位配置)，其中包含单 CLI 示例。首次安装前，可向 `init` 传入 `--seat <seat>=<agent>:<model>:<effort>:<life>`（可重复指定）覆盖默认席位；检查新计划后，在完全相同的命令中追加 `--apply`。使用 `cowork/cw seats` 查看已安装的席位表。

**Kit 版本**：首次安装的计划显示 `kit: to <sha>`，版本有变化的升级显示 `kit: from <old|unknown> to <sha>`。首次安装或升级会写入 `cowork/kit-version`，内容为一行 clone 的完整 HEAD 提交和 origin URL（移除 HTTPS 凭据）。`cowork/cw lint` 会输出已安装版本，供你与计划核对。仅在无告警和错误时输出 `Caps OK.`；长度或重复行提示则显示 `Validation OK; <n> over guideline.`。版本未变时不输出版本变更行。普通 `init` 保留旧项目的版本状态，包括缺失的版本文件；使用 `--upgrade` 才会记录安装的发布版本。`init` 对 kit 未提交改动和开发仓库仍仅告警；`upgrade` 则拒绝这些 clone。

**`init` 会触及的内容**：创建 `cowork/cw`、`cowork/kit-version`（仅首次安装）、`cowork/seats.tsv`、`cowork/coordinator.addr`、`cowork/<today>/coordinator.md`、`cowork/README.md` 和 `cowork/lessons/README.md`；将五个技能（`cowork`、`cowork-init`、`cowork-seat`、`cowork-consolidate`、`cowork-away`）复制到 `.claude/skills/` 和 `.agents/skills/`；首次安装时向 `.gitignore` 追加缺失的 `/cowork/`、`/output/`、`/.scratch/`、`/.tmp/`、`/.worktrees/`（计划中列出；去除行尾空白后，带或不带根目录锚点的已有行均算存在），向 `AGENTS.md` 追加带标记区块，并向 `CLAUDE.md` 添加 `@AGENTS.md`。已有安装的普通 init 和 `--upgrade` 逐字节保留 `.gitignore`，缺少默认项时提示。在改用锚点默认项之前安装的项目可能写的是不带锚点的 `cowork/`，它也会忽略 `.agents/skills/cowork/` 和 `.claude/skills/cowork/`；如需跟踪已安装的技能，请手动改为 `/cowork/`。普通 init 保留其他已有内容（包括标记指令块以外的已有项目文字），对已更新的安装重复运行会打印 `nothing to do`。执行 `python3 ~/.agent-co-work/bin/cw init --upgrade`（随后 `--upgrade --apply`）仅刷新 `cowork/cw`、`cowork/kit-version`、复制的技能和 `AGENTS.md` 的标记区块。

首次安装还会在计划中列出并用随附模板创建 `docs/plans/README.md` 和 `docs/plans/brief-template.md`，前提是不存在 plans 目录（检查不区分大小写，包括 `Docs/plans/`）。已有 plans 目录绝不覆盖或合并。安装后的普通 init 和 `--upgrade` 不创建也不触及这两个文件；缺少 plans 目录时打印一条提示。

**使用服务器的项目**：如果项目在服务器上运行作业，`cowork-init` 的可选步骤会询问 [templates/server.md](templates/server.md) 中的每个占位符，填好规则供用户确认后，保存到 `docs/server.md`（或项目声明的文档路径）。已有服务器指南绝不覆盖，并在 `AGENTS.md` 的标记区块之外添加指针。硬件信息在沙箱外探测前保持未验证状态。

#### 环境要求

- **宿主系统（macOS / Linux / POSIX）**：`bin/cw` 无条件导入 `fcntl` 并使用 `fcntl.flock` 串行化资源锁；不支持原生 Windows Python。
- **Python 3.9+**：仅使用标准库；`bin/cw` 无第三方依赖。
- **Herdr（`hc`，已测试 0.1.22）**：用于实时启动、审批、状态查看、汇报与交接；离线记录管理与命令预览时不强制要求。
- **Agent CLI（`claude`、`codex`、`agy`）**：只需安装 `cowork/seats.tsv` 或单任务覆盖配置中实际用到的 CLI，不要求全部安装——纯 Claude 配置只需 `PATH` 中有 `claude`（纯 Codex 配置只需 `codex`）。
- **`git`**：用于克隆和更新 GitHub 发布仓库、识别发布版本，以及通过 `cw new --worktree` 创建隔离工作树。安装后的记录管理命令无需 Git。

#### 升级细节

- `cowork/cw upgrade` 检查发布 clone、执行 `--ff-only` 拉取，并展示升级计划与 SHA。
- 用户确认后，协调员运行 `cowork/cw upgrade --apply`，**不再次拉取**，直接应用当前 clone，然后运行新安装的 lint。审阅至应用期间应保持共享 clone 不变；若其他项目更新了它，先重新审阅计划。
- 对照确认的计划核对安装 SHA。升级刷新 CLI、内嵌模板、复制的技能、版本记录和 `AGENTS.md` 标记块。席位、任务记录、协调员地址、`.gitignore` 及标记块以外的项目文字保持原样。
- kit 文件缺失、kit 不是 Git 仓库根目录、使用开发仓库、有任何未提交或未跟踪文件、项目安装不完整或拉取失败，都会停止升级。若旧 CLI 不支持 `upgrade`，协调员先执行上方旧版命令一次，此后使用短命令。

#### 使用 Herdr 应用

打开 Herdr，用标签栏的 `+` 在项目文件夹打开终端。在其中启动协调员 CLI，粘贴[协调员提示词](#协调员提示词)。

启动席位时，`cowork/cw start` 把调用方的 `herdr.space=<id>` 标签传给 `hc run`，不设置 `herdr.tab`，请求在同一空间创建新标签页。长席位使用 `--no-parent`，短席位使用 `--parent <caller t-id>`。

### 选择席位

`templates/seats.tsv` 中的默认三 agent 配置仅作示例（单 CLI 与多 CLI 预设见[席位配置](#席位配置)）。任何席位都可以使用任意受支持的适配器（`claude`、`codex`、`agy`）及该 CLI 接受的任意模型与推理强度。可选的第六列带引号 `args`（`-` 或留空表示无）用于提供额外适配器 CLI 参数，按 shell 风格引号规则拆分（内层引号可保留空格，不执行 shell 展开）并原样追加到适配器 argv 末尾。

协调员先在沙盒外检测已安装 CLI 和模型（`command -v claude codex agy`、`agy models`、`codex debug models`、Claude 别名），再只用已安装项提出推荐表（包含 `discussion`），提示缺失的 CLI 并提供单 CLI 配置。选择保留默认值 / 调整席位；每个调整问题提供默认配置 / 自填 `agent model effort [life]`。Claude 协调员使用问题工具（每次最多四问），其他协调员在聊天中询问。应用前确认完整表格。Claude、Codex 或 agy 均可单独使用。

Claude 的 effort 为 `low`、`medium`、`high`、`xhigh`、`max`；agy 列出相同级别，并将 effort 放在模型名中（如 `gemini-4-neon-xhigh`），因此应保持二者一致。Codex 的 effort 取决于模型，以本机模型列表为准。不要选择 `ultra`（自动委派子 agent）；未列出的值保持未验证。这些是探测指南，不是 CLI 内硬编码的校验规则。

已有项目保留旧 `coder-heavy` / `coder-light` 行及记录；升级不会迁移席位。项目缺少某个模板默认席位时，会回退到内嵌默认行，后续可用 `cw seat set` 将自定义行追加到旧项目。

- **修改席位默认值**：初始化阶段可传 `--seat <seat>=<agent>:<model>:<effort>:<life>`（`args` 在初始化后配置）；初始化完成后运行 `cowork/cw seat set [--args='...'] <seat> <agent> <model> <effort> [short|long]`（更新 `cowork/seats.tsv`、保留注释，并在调用方记录中追加一行 `State`）。`--args='...'` 替换额外适配器选项（例如 `--args='--sandbox workspace-write'` 或 `'--config "label=two words"'`），省略 `--args` 则保留现有 `args`，`--args=-` 用于清空；切换适配器时请清空或替换不兼容的选项。
- **为单个任务指定 agent**：向 `cowork/cw new` 传入 `--agent <agent>:<model>:<effort>[:<life>]`，或运行 `cowork/cw set <taskfile> agent=<agent>:<model>:<effort>[:<life>]`（`agent=-` 恢复席位默认值）。省略 `life` 时沿用席位设置。同一适配器的覆盖保留席位 `args`；切换适配器时省略席位 `args`，任务 `args:` 仍然生效。席位的角色和命名规则保持不变。
- **单任务额外参数**：`cw new ... --args='-a never'` 或 `cw set <taskfile> 'args=-a never'` 将任务参数追加在席位参数之后，三种适配器一致。`args=-` 仅清空任务参数；旧记录缺少该字段时视为空。使用 shell 风格引号但不执行 shell 展开；`args: --label "run # 1" # comment` 保留引号中的井号。无人值守选项只放在需要它的任务上。

### 讨论席位

当用户请求打开讨论席位时（可指定希望使用的 agent），协调员准备含 Goal 和上下文文件列表的独立 step，启动后告诉用户标签页名称。讨论席位会先打招呼并等待，用户直接在该标签页讨论。只有用户明确要求时才编辑项目文件，绝不暂存或提交；用户结束讨论时，它才汇报结论和未决问题。协调员阅读总结、记录决策并关闭记录。

### 资源与锁

- **参考预计时间**：`cowork/cw lock expect <resource> <time>` 通知后继任务与协调员，不写入 `State` 行。
- **释放与过期恢复**：持锁方运行 `cowork/cw lock release <resource> [--evidence <path>] [--note <text>]`，先释放锁再发送通知，保留队首设置，并写入一条 `State` 行。`cowork/cw status` 会为已关闭、缺失或已退出的持锁方标出 `! stale holder`（绝不自动释放）；仅协调员席位可使用 `--force --holder <yyyymmdd/task>` 强制恢复。预期持有者在锁内校验和比较；缺失、格式错误或不匹配时退出码为 1，锁不改变。
- **存储方式**：以无扩展名 TSV 文件存于 `cowork/locks/<resource>`，记录 `yyyymmdd/<task>` 标识，通过 `cowork/locks/.flock` 上的 `fcntl.flock` 串行化，并借助 `COWORK_ROOT` 在各 worktree 间共享。

锁命令在变更前失败时返回 1，变更后通知或回执写入失败时返回 3（包括 `expect`）。遇到 3 或结果不明确时，重试前先用 `cw status` 检查 holder/since。`--holder` 能保护其他任务的获取，但不能区分同一任务后来再次获取。详见 [资源规则](skills/cowork/SKILL.md#resources)。

### 记录、Wrap-up 与经验教训

[记录规则](skills/cowork/SKILL.md#records-and-messages) 定义写入归属与不可变证据；[cowork-consolidate](skills/cowork-consolidate/SKILL.md) 覆盖 State、Decisions/Plan、教训、概览/交接、归档、输出/临时文件和记忆。

短 Brief 留在任务记录中。超过约 20 行、跨多个任务或需要作为项目文档保留的 Brief 放在 `docs/plans/`，任务记录引用它。计划使用 `NNN-<slug>.md`，Brief 使用 `NNN-<slug>-brief.md`，三位编号永不复用。可按工作线设子目录，各自维护 README 索引和编号，除非父索引声明共用编号。协调员在命名阶段转换和 Wrap-up/结项时更新计划 README 的 State 单元格，每格只写一句简短状态；执行细节保留在任务 State 和 `output/<yyyymmdd>/<task>/log.md`。

- `cw report "<conclusion>; <path>"` 向协调员发送带任务前缀的消息。`--to <task>` 优先解析发送方同日记录，否则使用最新同名记录，发送给活跃目标并抄送协调员；目标缺失则只通知协调员。每个直接收件方都有送达回执。
- 报告发送最多尝试三次，每次约 180 秒，整条命令共用 10 分钟预算（含 `--to` 的两个收件方）。每次重试前读取目标屏幕；正文已显示则视为送达，不再重发。进度写入 stderr，仅最终结果产生回执。任务投递、按键、启动及其他通知保持原有行为。
- 协调员报告失败时追加 `REPORT (undelivered):`；随后相同正文和目的地送达时追加 `REPORT (delivered):`，保留失败记录。协调员从 State 读完报告后运行 `cw ack <taskfile>`，为每个未解决的正文/目的地追加 `REPORT (read):` 并保留历史；命令打印确认项，无待确认项时不输出。普通首次成功不新增 State 行。`cw status` 标记未解决回执，包括已关闭或未分配终端的任务；不同正文/目的地互不消除，再次失败会重新标记。
- `cw index` 生成以 60 行为建议长度的概览：按项目/线路分组的活跃 task/seat，以及近 7 天关闭的记录。step 汇总为父任务行上的计数（同日父任务优先，否则最新）；无父任务的 step 留在每日记录中。超出时仍写入概览并告警；应进行整理。
- `cw lessons [yyyymmdd]` 从 Wrap-up/旧 Debrief 刷新每日 From tasks，保留 Takeaways。
- `cw lint` 打印安装版本、校验头部和项目状态，并检查非空节行数：Goal <=3、State <=10、Handover <=20、项目 Decisions <=20。文件建议长度为教训 README <=40、概览 <=60；项目历史归档不受 Decisions 检查。长度超出与超过 40 字符的完全重复行输出 `over guideline: ...; consider cowork-consolidate`，退出码为 0。已关闭的任务记录不参与长度和重复行建议检查。保持简洁，超出时整理。项目/任务头部、名称、席位格式与路径/符号链接越界仍以退出码 1 失败。

任务模板包含 `args: -`，旧 `size:` 和 `debrief` / `## Debrief` 仍可读取。用 `cw set` 修改头部。

### 协调员交接

- 运行 `cowork/cw handover context` 启动全新的 `coordinator`，`cowork/cw handover tokens` 切换到 `coordinator-alt`（或切回），或 `cowork/cw handover --accept` 接管；详见 [交接规则](skills/cowork/SKILL.md#size-limits-consolidation-and-handover)。
- `--accept` 会将继任者的终端 ID 写入 `cowork/coordinator.addr`、向前任协调员发送接管确认并在自己的 `State` 中记录送达情况；离任方的 `cw handover` 会轮询 `coordinator.addr` 以确认交接完成。

### 无 Herdr 模式

- 未设置 `HC_TERMINAL_ID` 时，`cw init --apply` 会将 `cowork/coordinator.addr` 设为 `- -`；记录类命令（`project new`、`new`、`set`、`seat set`、`index`、`lessons`、`lint` 以及锁状态操作）均可离线运行。
- `cowork/cw start <taskfile>`（或随时加上 `--print`）会打印准确的 `hc` 启动命令，不实际启动也不修改记录；`cowork/cw check <taskfile>` 会打印 `hc get` 命令及最后 3 条 `State` 行。
- `cowork/cw status` 列出活跃且已分配终端的任务，以及任何有未解决报告回执的任务，显示 `Herdr unavailable`，同时仍会标出其 `State` 中的 `BLOCKED:` 以及已关闭或缺失的过期锁持有者。
- `cowork/cw report` 会向 `State` 追加 `REPORT (undelivered): ...`、打印供人工转发的 `Relay to coordinator:` 行并以退出码 1 退出；`cowork/cw handover` 必须依赖 `HC_TERMINAL_ID`。

### 故障排查

- **恢复 Claude Code 后终端身份错误**：恢复的会话可能使用另一个会话的 `HC_TERMINAL_ID` 运行工具。用 `echo $HC_TERMINAL_ID` 与 `cowork/coordinator.addr` 核对；若你确实是记录中的协调员，请固定正确值，例如 `HC_TERMINAL_ID=t22 cowork/cw start <taskfile>`。未设置 `COWORK_TASK` 的调用方会在 `start`、`lock next`、协调员的 `lock take` / `release --force`、`handover context|tokens` 和 `seat set` 前接受身份检查。席位调用方、`handover --accept`、`report` 及无 Herdr 的操作不受影响。
- **信任与权限提示**：`cw start` 和 `cw handover` 仅在以下两种情况调用 `cw approve`：(a) 路径与项目根目录精确匹配的文件夹信任提示（`cw start` 中也可为任务指定的 worktree）；(b) `agy` 对普通 `cowork/cw ...` 命令的权限提示（选择 "always allow in this conversation"）。独立 `cw approve` 仍只接受根目录，同级目录不获准。其他任何提示或重复出现的不匹配提示都会输出屏幕末尾内容并以退出码 2 中止，不会按键；可用 `hc read <t> --lines 0` 查看并手动处理，或对可识别提示运行 `cowork/cw approve <t>`。
- **Codex 启动因账号错误退出**：若 Codex（或其他 agent）在任务确认尚未送达时提前退出（例如启动时出现账号或路由错误），`cw start` 会读取并打印屏幕末尾内容、移除该失败终端记录，并在原 120 秒启动时限内以相同名称重新启动一次。若第二次仍提前退出（或清理失败），则会打印屏幕末尾并停止，不更新任务头部；请检查打印的尾部输出（若第二个终端仍在，也可运行 `hc read <name> --lines 0`）、排查 Codex 登录/账号状态，再重新执行 `cowork/cw start <taskfile>`。已送达或送达状态不明确的任务绝不会自动重启，且 `cw handover` 不会自动重启。
- **嵌套项目询问是否允许外部 `CLAUDE.md` 导入**：`cw init` 会向 `CLAUDE.md` 写入 `@AGENTS.md`。在嵌套项目中，Claude Code 可能会询问是否允许导入外部 `CLAUDE.md`；由于这不属于可识别的根目录文件夹信任提示，`cw approve` 会刻意拒绝按键（输出屏幕末尾并以退出码 2 退出），请在 Herdr 中手动确认或拒绝该对话框。
- **agy 状态滞后**：Herdr 可能在生成结束前就把 `agy` 报告为 `done`。请以席位发出的 `cw report` 消息为准，不要仅凭终端状态判断，并可通过 `cowork/cw check <taskfile>` 查看进展。

### 命令参考

全部 `cw` 命令（全局参数：`--root <dir>`）：

| 命令 | 用途 |
|---|---|
| `python3 ~/.agent-co-work/bin/cw init [--seat seat=agent:model:effort:life] [--upgrade] [--apply]` | 从固定 GitHub 发布 clone 安装或升级；规划版本，并在首次安装或升级时写入 `cowork/kit-version` |
| `cw upgrade [--kit <dir>] [--apply]` | 拉取并显示发布计划/SHA；应用时不拉取，随后运行新 lint |
| `cw seats` | 打印 `cowork/seats.tsv` |
| `cw seat set [--args='...'] <seat> <agent> <model> <effort> [life]` | 更新单个席位配置（省略 `--args` 保留原值，`--args=-` 清空）并追加一行 `State` |
| `cw project new <name>` | 创建 `cowork/projects/<name>.md` |
| `cw new <task> --seat <seat> (--kind task\|step \| --size large\|small) [--project <name>] [--line main\|side\|-] [--parent <task>] [--agent agent:model:effort[:life]] [--args='...'] [--worktree]` | 创建 `cowork/<today>/<task>.md`（及可选的 `.worktrees/<task>`） |
| `cw set <taskfile> key=value ...` | 编辑经校验的任务 frontmatter 字段 |
| `cw start <taskfile> [--print]` | 在 Herdr 中启动经关卡检查的任务/步骤，或仅打印启动命令 |
| `cw check <taskfile>` | 显示终端 `hc get` 状态及最后 3 条 `State` 行 |
| `cw approve <terminal>` | 自动响应可识别的根目录信任或 `agy` 的 `cowork/cw` 提示（否则退出码 2） |
| `cw status` | 列出活跃已分配终端和未解决报告（`blocked`、`error`、`exited`、`BLOCKED:`、`undelivered report`）及锁状态（`! stale holder`） |
| `cw lock next <resource> <task\|->` | 协调员设置或清空唯一队首 |
| `cw lock take <resource>` | 为调用方任务获取空闲或排队就绪的锁 |
| `cw lock expect <resource> <time>` | 向后继任务与协调员发送参考释放时间 |
| `cw lock release <resource> [--evidence <path>] [--note <text>] [--force --holder <yyyymmdd/task>]` | 释放锁、通知后继任务与协调员并写入一条 `State` 行（`--force --holder` 仅限协调员；变更后失败返回 3） |
| `cw report [--to <task>] "<conclusion>; <path>"` | 向协调员汇报（可选同时发给活跃任务终端） |
| `cw ack <taskfile>` | 协调员确认已从 State 读过的未解决报告，保留回执历史 |
| `cw handover [context\|tokens \| --accept]` | 启动继任协调员或接管 `coordinator.addr` |
| `cw index` | 重新生成 `cowork/README.md` |
| `cw lessons [yyyymmdd]` | 将 Wrap-up/Debrief 中的 `- lesson:` 汇总到 `cowork/lessons/<date>.md` |
| `cw lint` | 输出已安装的 `cowork/kit-version`；校验项目/任务/席位结构，提示长度与重复行 |

### 已知限制

- **固定适配器集合**：内置启动与审批适配器仅支持 `claude`、`codex` 和 `agy`；未知 agent 会报错。
- **严格限定的自动审批**：仅自动处理可识别的提示，详见 [故障排查](#故障排查)。
- **无加密级强约束**：`approved: user, yyyy-mm-dd` 与席位角色只做格式/日期校验，不构成防止手动篡改的安全边界。
- **有界启动重试与人工恢复**：启动恢复详见 [故障排查](#故障排查)；过期锁只会标记（`! stale holder`），永不自动释放。
- **命名与可见性上限**：名称限 1–20 字符（`[a-z0-9]([a-z0-9-]{0,18}[a-z0-9])?`），冲突后缀最多到 `-9`，调用方无 `herdr.space` 标签时会发出警告并以隐藏终端启动。
- **单元测试范围**：`tests/` 使用隔离的模拟 `hc`/`git` 二进制、本地 Git clone 测试仓库、捕获的提示界面文本以及真实的并发锁竞争进程；实机多 agent 交接未纳入自动化测试套件。

</details>

## 维护者

<details>
<summary>目录结构、日常校验与维护者发布</summary>

### 开发说明

- **目录结构**：`bin/cw`（单个纯标准库 Python 3 脚本）、`skills/`（`cowork`、`cowork-init`、`cowork-seat`、`cowork-consolidate`、`cowork-away`）、`templates/`（包含用于目标项目 `docs/plans/` 的 `plans-readme.md` 和 `brief-template.md`）、`tests/`、`index.html`（公开概览页）与 `.nojekyll`（GitHub Pages 原样提供文件）。
- **单一规则来源**：协作规则只维护在 [skills/cowork/SKILL.md](skills/cowork/SKILL.md)（建议不超过 150 行）；其余四个技能仅链接至此，不重复陈述规则。
- **日常校验**：在 kit 仓库中运行 `python3 -m unittest discover tests`；在已初始化的项目中运行 `cowork/cw lint`，校验该项目的协作记录。

### 维护者发布

只有选择 SSH 发布的维护者才需要 SSH（例如 `git@github.com:YitaoXU/agent-co-work.git`）。已有 SSH clone 仍然可用，版本记录保留其实际 origin。用户通过 HTTPS 安装公开发布版。

</details>
