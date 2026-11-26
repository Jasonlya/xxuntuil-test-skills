[简体中文](./README.md) | [English](./README.en.md)

<p align="center">
  <img src="./assets/banner.svg" alt="xxuntuil-test-skills —— 可单装的测试 Skill 合集，一个目录一个 skill" width="820">
</p>

<h1 align="center">xxuntuil-test-skills</h1>

<p align="center"><strong>可单装的测试 Skill 合集。装一个是一个。</strong></p>

<p align="center">一个目录一个 skill，拷进宿主的 skills 目录就生效，不动你的仓库。<br>各自带产出格式、红线与能机判的闸门，互不依赖。</p>

<p align="center">
  <a href="https://github.com/Jasonlya/xxuntuil-test-skills/actions/workflows/check.yml"><img src="https://github.com/Jasonlya/xxuntuil-test-skills/actions/workflows/check.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="./skills/"><img src="https://img.shields.io/badge/skills-1-blue" alt="Skills"></a>
  <img src="https://img.shields.io/badge/deps-0-brightgreen" alt="零第三方依赖">
  <img src="https://img.shields.io/badge/python-3.8%2B-3776AB" alt="Python 3.8+">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT"></a>
</p>

---

这里不收提示词，也不做「装齐一套才跑得动」的框架。每个 skill 是独立的：拷一个目录过去就能用，不引用兄弟 skill，不改你宿主仓库的代码，卸掉也不留残渣。

三个入选标准，缺一不进：**产出有固定格式**、**完成标准可判定**、**至少一处红线能机判**。第三条是硬门槛，理由是规则只写在散文里，模型会跳过；写成脚本，退出码才是结论。所以这里的闸门都自带负向样例——只证明「能通过」不算数，得先证明「能拦住」。

[技能清单](#技能清单) · [一个 skill 长什么样](#一个-skill-长什么样) · [仓库级闸门](#仓库级闸门) · [安装](#安装) · [新增一个 skill](#新增一个-skill) · [兼容性](#兼容性) · [实测记录](#实测记录)

## 技能清单

| Skill | 解决什么 | 触发词 | 版本 |
|---|---|---|---|
| [c2d-case-writing](./skills/c2d-case-writing/README.md) | C2D（设计稿转代码）图片校验用例：每条强制挂真实图片直链，并声明这张图为何能触发该规则 | C2D 图片校验、MasterGo 图片填充 / 导出、设计稿转代码图片测试 | `v0.1.0` |

规划中（还没写，不列进上表）：需求建模、测试策略、用例审查、接口契约测试、flaky 治理。

合集的设计取向是**少而硬**。与其塞十个「看着完整」的 skill，不如让每一个都带实测记录和闸门。新增一个的完整规矩见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 一个 skill 长什么样

<p align="center">
  <img src="./assets/anatomy.svg" alt="每个 skill 的结构：元数据常驻上下文，SKILL.md 正文触发后加载，references / assets / scripts 按需加载" width="780">
</p>

三层加载决定了怎么写才划算：元数据（`name` + `description`）常驻上下文，所以它是**唯一决定触发的地方**，写虚了就不会被用；正文只在触发后加载，所以只留骨架；规范、模板、脚本按需读，所以细则全往外放。

两条硬约束：

- **目录名 == frontmatter `name`**。不一致会静默不加载，这是最高频的失败原因。
- **每个 skill 有自己的 `README.md` 详情页**。合集首页只做索引，不堆单 skill 的细节——否则仓库看起来就只为那一个 skill 而建。

## 仓库级闸门

`scripts/check_repo.py` 检查的是「装不上」那类问题，与具体 skill 的业务逻辑无关：

| 级别 | 检查项 | 退出码 |
|---|---|---|
| E | 缺 `SKILL.md`、frontmatter 未闭合、缺 `name` / `description`、`name` 与目录名不符、命名非法或超长、`description` 过短、本地绝对路径、正文引用断链、Python 脚本语法错 | 1，阻断提交 |
| W | 缺 `displayName` / `version`、`SKILL.md` 超 500 行、skill 未列进本 README、徽章 `skills-N` 与实际数量不符 | 0，仅提示 |

push 与 PR 会自动跑（`.github/workflows/check.yml`），本地也能提前跑：

```bash
python3 scripts/check_repo.py
```

skill 自己的业务闸门（比如用例红线）属于各个 skill，安装在它的 `scripts/` 下，不混进仓库级检查。

## 安装

```bash
git clone git@github.com:Jasonlya/xxuntuil-test-skills.git
cd xxuntuil-test-skills
./install.sh                    # 全部 skill → ~/.workbuddy/skills/
```

纯拷贝，不改宿主任何配置。覆盖已装版本时**把旧目录改名成 `.bak.<时间戳>` 备份，不删除**。

```bash
./install.sh --list                          # 仓库里有哪些 skill
./install.sh c2d-case-writing                # 只装一个
./install.sh -d ~/proj/.workbuddy/skills     # 装到指定目录（项目级，随 git 共享给团队）
```

| 范围 | 目录 | 适用 |
|---|---|---|
| 个人 | `~/.workbuddy/skills/` | 所有项目可用 |
| 项目 | `<仓库根>/.workbuddy/skills/` | 只对该仓库生效，随 git 流转 |

升级：`git pull` 后重跑原命令。卸载：删掉宿主目录下对应的 skill 目录即可，仓库里始终留全量。

**装完要确认真的被装载**：新开一个会话，用它该被触发的那句话问一次，能看到 Agent 去读 `SKILL.md` 才算成功。目录存在 ≠ 触发成功。

## 目录结构

```text
skills/                    产品：一个目录一个 skill
  <name>/
    SKILL.md               唯一入口：元数据 + 铁律 + 工作流
    README.md              详情页：这个 skill 的完整说明与实测记录
    references/            按需加载：规范、清单、矩阵
    assets/                可直接复制的模板
    scripts/               该 skill 自己的闸门
scripts/check_repo.py      仓库级自检
.github/workflows/check.yml  push 与 PR 自动跑自检
install.sh                 安装脚本（单装 / 全装 / 项目级 / 备份式覆盖）
assets/                    README 图示（按 skill 分子目录，如 assets/c2d/）
```

## 新增一个 skill

```bash
mkdir -p skills/<name>/{references,assets,scripts}
# 写 SKILL.md（目录名必须等于其中 name）、写 README.md 详情页
python3 scripts/check_repo.py          # 本地自检，E 级必须清零
```

五条规矩（前两条由脚本拦）：

1. **目录名 == frontmatter `name`**，小写连字符、≤40 字符。
2. **`description` 写清三件事**：做什么 + 什么时候用 + 触发词原话。
3. **正文只留骨架**，细则进 `references/`、模板进 `assets/`、能跑的逻辑进 `scripts/`，SKILL.md 控制在 500 行内。
4. **能机判的别写成散文**，写成脚本，并说清闸门判不了什么。
5. **不编事实**。查不到的字段名、阈值来源写 `TODO：向 {谁} 确认 {什么}`。

还得把新 skill 补进上面的技能清单表，并更新 `skills-N` 徽章——这两处 `check_repo.py` 会提示，但改还得人改。完整流程见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 兼容性

skill 以 Markdown 指令 + 相对路径引用 + 按需运行的标准库脚本分发，不依赖 SDK。

| 宿主 | 目录 | 验证范围 |
|---|---|---|
| WorkBuddy | `~/.workbuddy/skills/` 或项目 `.workbuddy/skills/` | 主要适配对象；本机实测 |
| Claude Code | `~/.claude/skills/` 或项目 `.claude/skills/` | 目录结构兼容，未在该宿主实测产出效果 |
| 其他支持 `SKILL.md` 的宿主 | 依其规则 | 结构可适配，触发与产出需各自验证 |

所有 skill 的指令正文为中文。原生 Windows 未覆盖（建议 WSL）；除 macOS 外的平台未实测。

## 实测记录

仓库级（macOS · Python 3.13 · 2026-11-26）：

| 场景 | 结果 |
|---|---|
| `check_repo.py` 负向验证（name 不符 + 断链 + 本地路径 + 脚本语法错） | 4 类全部报出，退出码 1 |
| 同上跑正常仓库 | 0 E 0 W，退出码 0 |
| CI（push 与 PR） | 与本地共用同一脚本，最近一次运行通过 |

各 skill 自己的实测记录在它的详情页里，比如 [c2d-case-writing 的闸门与图源实测](./skills/c2d-case-writing/README.md#实测记录)（模板 0 错放行 / 坏样例 11 错阻断 / 13 个图源 curl 全部 200）。

**没做过的事**：没有「有 skill vs 无 skill」的产出质量对照，所以这里不写任何百分比提升。

## 文档导航

| 文档 | 适合何时阅读 |
|---|---|
| [skills/c2d-case-writing/README.md](./skills/c2d-case-writing/README.md) | 想用这个 skill，看完整说明与实测 |
| [skills/c2d-case-writing/SKILL.md](./skills/c2d-case-writing/SKILL.md) | 想直接看它怎么干活（Agent 读的就是这份） |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | 想加一个 skill 或改现有内容 |
| [CHANGELOG.md](./CHANGELOG.md) | 查版本变更 |
| [LICENSE](./LICENSE) | MIT |

## 贡献与反馈

欢迎按[贡献指南](./CONTRIBUTING.md)提交改进。可复现的问题与具体需求走 [Issues](https://github.com/Jasonlya/xxuntuil-test-skills/issues)。

## License

[MIT](./LICENSE)
