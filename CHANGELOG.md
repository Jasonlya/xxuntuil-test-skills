# 变更记录

本文件记录所有值得注意的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-11-26

首个版本。仓库从零建立，收录一个 skill。

### 新增

- **仓库结构**：`skills/<name>/` 平铺，目录名必须等于 frontmatter `name`。选平铺而非按分类嵌套，是因为安装脚本要按目录名直接拷贝，引入分类层就会让「目录名 == name」这个硬约束断掉。
- **`scripts/check_repo.py`**：仓库自检，零依赖。E 级 12 类（缺 SKILL.md、frontmatter 未闭合、缺 name、name 命名非法、name 超长、name 与目录名不符、缺 description、description 过短、本地绝对路径、正文引用断链、文件读取失败、Python 脚本语法错误），W 级 3 类（缺 displayName、缺 version、SKILL.md 超过 500 行）。退出码 1 阻断。
- **`install.sh`**：单装 / 全装 / `--list` / `-d` 指定目录。覆盖时把旧目录改名为 `.bak.<时间戳>` 备份，不做删除。
- **`.github/workflows/check.yml`**：push 到 main 与 PR 时自动跑自检。
- **`skills/c2d-case-writing` v0.1.0**：C2D 图片校验用例编写。
  - `SKILL.md`：五条铁律、五段式用例格式、六阶段工作流、优先级判定、十类常见错误。
  - `references/image-rule-matrix.md`：6 组 47 条场景规则（A 填充 10 / B 裁剪 8 / C 导出 10 / D 代码渲染 11 / E 加载回退 5 / F 视觉一致性 3），每条规则声明「必配图片特征」与「可判定预期」。
  - `references/image-fixture-registry.md`：13 个实测公网图片直链槽位 + 自备槽位规范。
  - `references/case-format-c2d.md`：TC 编号规则、导读四件套、附录隔离规范、判定强度对照。
  - `assets/case-template.md`：可直接复制的用例起点，含 5 条金标准样例。
  - `scripts/case_lint_c2d.py`：12 项 E + 6 项 W 红线闸门。
  - `scripts/check_image_links.py`：链接实测（状态码 / Content-Type / 体积），跟随重定向，支持 `expect_status` 声明预期失败。
- **文档**：`README.md` 与 `README.en.md`（含明暗双版横幅、工作流图、闸门真实输出图）、`CONTRIBUTING.md`、`LICENSE`（MIT）。

### 验证

- 闸门对模板：4 模块 / 5 条用例 → 0 错 0 警，退出码 0。
- 闸门对故意写坏的 2 条用例：11 错 4 警，退出码 1。
- 链接核验对模板：4 条链接 → 3 OK + 1 预期失败，失败 0，退出码 0；去掉 `expect_status` 后同一条立即判坏链，退出码 1。
- 13 个图源逐个 `curl`：全部 200 且 `Content-Type` 匹配。
- 仓库自检负向验证：name 不符 / 断链 / 本地绝对路径 / 脚本语法错，4 类全部报出。

### 已知限制

- 只在 macOS + Python 3.13 + WorkBuddy 上实测过，其他平台与宿主未验证。
- MasterGo 插件 API 有 5 项未核实（填充模式字段名与枚举、mask 判定方式、blendMode 是否暴露、OpenAPI 导出端点、签名有效期），按 `references/case-format-c2d.md` 附录 B 的约定写成 TODO，未做猜测性断言。
- 图源依赖第三方免费服务（picsum.photos / placehold.co），不承诺 SLA。
- 未做「有 skill vs 无 skill」的产出质量对照，因此不提供任何提升百分比。
