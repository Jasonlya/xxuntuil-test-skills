# xxuntuil-test-skills

> 我的测试类 Agent Skills 合集。一个目录一个 skill，装进 `~/.workbuddy/skills/` 或项目的 `.workbuddy/skills/` 即可被 WorkBuddy / Claude Code 等支持 `SKILL.md` 的 Agent 识别。

**当前收录 1 个 skill**，全部经过本地实测（脚本跑过、图片链接 curl 过），不是抄来的模板。

## 仓库结构

```
xxuntuil-test-skills/
├── skills/                       # 所有 skill，一个目录一个
│   └── c2d-case-writing/         # 目录名必须等于 SKILL.md frontmatter 里的 name
│       ├── SKILL.md              # 唯一入口：元数据 + 铁律 + 工作流 + 常见错误
│       ├── references/           # 按需加载的知识：场景矩阵、图源登记表、格式细则
│       ├── assets/               # 可直接复制的起点：用例模板（含金标准样例）
│       └── scripts/              # 可机械执行的闸门，零第三方依赖
├── scripts/
│   └── check_repo.py             # 仓库自检：命名 / 元数据 / 断链 / 脚本语法
├── .github/workflows/check.yml   # push 与 PR 自动跑自检
├── install.sh                    # 安装脚本（单装 / 全装 / 项目级）
├── .gitignore
└── README.md
```

三层加载模型决定了这个结构：`SKILL.md` 的元数据常驻上下文，正文只在触发时加载，`references/` 与 `assets/` 再由正文按需指向。所以正文只留骨架，细则一律外链——**写得越少，触发越准**。

## 技能清单

| Skill | 能力 | 触发场景 | 隐私资产 | 状态 |
|---|---|---|---|---|
| [`c2d-case-writing`](skills/c2d-case-writing/SKILL.md) | 为 C2D（设计稿转代码）编写图片校验用例：每条强制挂真实图片直链，并声明该图**为什么**能触发这条规则；产出 markmap 用例 + 机读 Schema + 链接核验报告 | C2D 图片校验、MasterGo 图片填充/导出、设计稿转代码图片测试、写图片相关测试用例 | 6 组 47 条场景规则；13 个实测图片直链；2 道机判闸门 | `v0.1.0` |

### c2d-case-writing 解决什么

图片类 bug 几乎都在资源与渲染管线的边界上（填充模式、裁剪、蒙版、透明通道、倍率、格式降级、加载回退），有两个共性麻烦：

1. **纯文字写不出可执行用例**——"用一张长图测裁剪"，执行者不知道多长、什么比例、什么格式，两个人结论不可比，回归也没法复现。
2. **图不对等于没测**——用 1:1 的图测 FILL 裁切，容器也是 1:1，压根不产生裁切，用例"通过"了但零验证。

所以每条用例钉死两样东西：**一张具体的图（直链）** + **这张图为什么能测到该场景**。规则写进 `references/image-rule-matrix.md`，链接写进 `references/image-fixture-registry.md`，剩下交给脚本拦。

## 安装

### 方式一：脚本（推荐）

```bash
git clone git@github.com:Jasonlya/xxuntuil-test-skills.git
cd xxuntuil-test-skills

./install.sh                          # 全部 skill → ~/.workbuddy/skills/
./install.sh c2d-case-writing         # 只装一个
./install.sh --list                   # 看看仓库里有哪些
./install.sh -d ~/proj/.workbuddy/skills   # 装到指定目录（项目级）
./install.sh --force c2d-case-writing # 覆盖已装版本（旧版自动改名备份，不删除）
```

### 方式二：手动拷贝

```bash
cp -R skills/c2d-case-writing ~/.workbuddy/skills/
```

### 装到哪

| 范围 | 目录 | 适用 |
|---|---|---|
| 个人 | `~/.workbuddy/skills/` | 所有项目可用 |
| 项目 | `<仓库根>/.workbuddy/skills/` | 随 git 流转，团队共享（skill 只对该仓库生效） |

装完新开一个会话即可识别，**不需要改 SKILL.md**。目录名必须与 frontmatter `name` 一致，否则不加载——`scripts/check_repo.py` 会拦这一条。

## 使用（以 c2d-case-writing 为例）

```bash
# 从模板起一份用例
cp .workbuddy/skills/c2d-case-writing/assets/case-template.md 测试用例_C2D图片_markmap.md

# 闸门一：红线检查（占位符 / 本地路径 / 缺直链 / 缺特征 / 预期不可判定）
python3 .workbuddy/skills/c2d-case-writing/scripts/case_lint_c2d.py 测试用例_C2D图片_markmap.md

# 闸门二：链接实测（状态码 / Content-Type / 体积，跟随重定向）
python3 .workbuddy/skills/c2d-case-writing/scripts/check_image_links.py \
  测试用例_C2D图片_markmap.md --out 图片素材核验_$(date +%Y%m%d).md
```

两个脚本退出码非 0 即阻断定稿。直接在对话里说"C2D 图片校验的用例"，skill 会被自动触发，不必手敲命令。

## 新增 skill 约定

合集要长大，得先有规矩：

1. **目录名 == frontmatter `name`**，小写连字符，≤40 字符。这是加载的硬条件，破了就是静默不生效。
2. **description 写清三件事**：做什么 + 什么时候用 + 触发词原话。它是唯一常驻上下文的部分，写虚了就不会被触发。
3. **正文只留流程骨架**，细则拆到 `references/`，模板放 `assets/`，能跑的逻辑放 `scripts/`。单个 SKILL.md 建议 ≤500 行。
4. **能机判的别写成散文**。规则写完问一句"这条能不能用脚本拦"，能就写成脚本——弱模型不会自查，评审方也没法逐条复核。
5. **不编事实**。查不到的 API 字段名、阈值来源，写 `TODO：向 {谁} 确认 {什么}`，不要用"通常/一般应该是"填充。

提交前跑一遍自检：

```bash
python3 scripts/check_repo.py
```

## 仓库自检

`scripts/check_repo.py` 零依赖，检查 11 项：

| 级别 | 内容 |
|---|---|
| E（阻断） | SKILL.md 缺失 / frontmatter 缺失或未闭合 / name 或 description 缺失 / name 与目录名不符 / name 命名非法 / description 过短 / 存在本地绝对路径 / 正文引用的文件不存在（断链）/ 脚本语法错误 |
| W（告警） | SKILL.md 超长 / 缺 `displayName` / 缺 `version` |

push 与 PR 会自动跑（`.github/workflows/check.yml`），本地也能提前跑。

## 已知边界

- **图源是第三方免费服务**：`c2d-case-writing` 的 13 个直链来自 `picsum.photos` 与 `placehold.co`，实测可用但不承诺 SLA。失效时按 `references/image-fixture-registry.md` 的「自备槽位规范」替换，再重跑 `check_image_links.py`。picsum 会 302 跳到带 `hmac` 签名的地址，**用例里只写原 URL**，核验脚本必须跟随重定向。
- **MasterGo API 有 5 项未核实**：填充模式字段名与枚举、mask 判定方式、blendMode 是否暴露、OpenAPI 导出端点、签名有效期。按 `references/case-format-c2d.md` 附录 B 的约定写成 TODO，不做猜测性断言——用例前提写错比留空危害大。
- **只在本机 WorkBuddy 与 macOS + Python 3 上实测过**。其余 Agent 与平台按 `SKILL.md` 标准结构应当兼容，但未逐一验证。

## License

暂未设置。若希望他人可自由复制与修改，建议补一份 MIT。
