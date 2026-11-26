#!/usr/bin/env python3
"""xxuntuil-test-skills 仓库闸门 —— 校验 skills/ 下每个 skill 是否真能被 Agent 加载。

合集一长大，最先坏的都是静默问题：目录名和 name 不一致（不加载）、正文引用的
references 文件改名后忘同步（读了 404）、脚本复制过程中被改坏（跑起来报错）。
这些都用不着模型判断，脚本拦得住。

零第三方依赖。退出码 1 = 有 E 级问题，阻断提交。

    python3 scripts/check_repo.py               # 检查全部
    python3 scripts/check_repo.py --skill NAME  # 只查一个
    python3 scripts/check_repo.py --json        # 机读输出
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOCAL_PATH_RE = re.compile(
    r"(?<![\w.])("
    r"/Users/[A-Za-z0-9._-]+"
    r"|/home/[a-z][A-Za-z0-9._-]*"
    r"|~/[A-Za-z0-9._-]"
    r"|[A-Za-z]:\\\\"
    r")"
)
# 正文里引用的 skill 内部相对路径，如 references/x.md、scripts/y.py
REF_RE = re.compile(
    r"(?<![\w/.-])((?:references|assets|scripts)"
    r"/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.(?:md|py|sh|json|ya?ml|txt|js))"
)
MAX_SKILL_LINES = 500
MIN_DESC_LEN = 40
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt", ".js"}


def parse_frontmatter(text: str):
    """返回 (dict | None, body)。支持 `key: value`、引号值、以及 `>` / `|` 块标量。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text

    fm: dict[str, str] = {}
    i = 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if ":" not in line or line[:1].isspace():
            i += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value in (">", "|", ">-", "|-", ">+", "|+"):
            block = []
            i += 1
            while i < end and (not lines[i].strip() or lines[i][:1].isspace()):
                block.append(lines[i].strip())
                i += 1
            fm[key] = " ".join(x for x in block if x)
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fm[key] = value
        i += 1
    return fm, "\n".join(lines[end + 1 :])


def iter_text_files(skill_dir: Path):
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def check_skill(skill_dir: Path):
    """返回 (errors, warnings)，元素为 (code, message)。"""
    errors: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.is_file():
        errors.append(("E001", "缺少 SKILL.md"))
        return errors, warnings

    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)

    if fm is None:
        errors.append(("E002", "SKILL.md 缺少合法 frontmatter（需以 --- 开头并有结束的 ---）"))
        fm = {}

    name = fm.get("name", "").strip()
    desc = fm.get("description", "").strip()

    if not name:
        errors.append(("E003", "frontmatter 缺 name"))
    else:
        if not NAME_RE.match(name):
            errors.append(("E004", f"name 不合规: {name!r}（小写字母数字与连字符，不以连字符开头结尾）"))
        if len(name) > 40:
            errors.append(("E005", f"name 超长: {len(name)} 字符（上限 40）"))
        if name != skill_dir.name:
            errors.append(("E006", f"name 与目录名不一致: name={name!r} dir={skill_dir.name!r}（会导致不加载）"))

    if not desc:
        errors.append(("E007", "frontmatter 缺 description"))
    elif len(desc) < MIN_DESC_LEN:
        errors.append(("E008", f"description 过短: {len(desc)} 字符（下限 {MIN_DESC_LEN}，需写清做什么+何时用+触发词）"))

    if not fm.get("displayName"):
        warnings.append(("W001", "未声明 displayName"))
    if not fm.get("version"):
        warnings.append(("W002", "未声明 version"))

    line_count = len(text.splitlines())
    if line_count > MAX_SKILL_LINES:
        warnings.append(("W003", f"SKILL.md {line_count} 行，超过建议上限 {MAX_SKILL_LINES}（细则宜拆到 references/）"))

    # 断链：正文引用的 references/ assets/ scripts/ 文件必须存在
    for ref in sorted(set(REF_RE.findall(body))):
        if not (skill_dir / ref).exists():
            errors.append(("E010", f"正文引用的文件不存在: {ref}"))

    # 本地绝对路径：装到别人机器上必然失效
    for path in iter_text_files(skill_dir):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(("E011", f"{path.relative_to(skill_dir)} 读取失败: {exc}"))
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            hit = LOCAL_PATH_RE.search(line)
            if hit:
                rel = path.relative_to(skill_dir)
                errors.append(("E009", f"{rel}:{lineno} 含本地绝对路径 {hit.group(1)!r}"))

    # 脚本语法：复制过程中被改坏、编辑器转义最常见的坑
    for script in sorted((skill_dir / "scripts").glob("*")) if (skill_dir / "scripts").is_dir() else []:
        if script.suffix != ".py":
            continue
        try:
            compile(script.read_text(encoding="utf-8", errors="replace"), str(script), "exec")
        except SyntaxError as exc:
            errors.append(("E012", f"scripts/{script.name} 语法错误: 第 {exc.lineno} 行 {exc.msg}"))

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 skills/ 下每个 skill 的可加载性")
    ap.add_argument("--skill", help="只检查指定 skill")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if not SKILLS_DIR.is_dir():
        print(f"错误: 找不到 {SKILLS_DIR}", file=sys.stderr)
        return 1

    skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))
    if args.skill:
        skill_dirs = [p for p in skill_dirs if p.name == args.skill]
        if not skill_dirs:
            print(f"错误: skills/ 下没有 {args.skill!r}", file=sys.stderr)
            return 1

    if not skill_dirs:
        print("错误: skills/ 下没有任何 skill 目录", file=sys.stderr)
        return 1

    report = []
    total_e = total_w = 0
    for skill_dir in skill_dirs:
        errors, warnings = check_skill(skill_dir)
        total_e += len(errors)
        total_w += len(warnings)
        report.append(
            {
                "skill": skill_dir.name,
                "errors": [{"code": c, "message": m} for c, m in errors],
                "warnings": [{"code": c, "message": m} for c, m in warnings],
            }
        )

    if args.json:
        print(json.dumps({"ok": total_e == 0, "skills": report}, ensure_ascii=False, indent=2))
        return 0 if total_e == 0 else 1

    print("xxuntuil-test-skills · 仓库自检")
    print(f"skills/ 下 {len(skill_dirs)} 个 skill\n")
    for item in report:
        print(item["skill"])
        if not item["errors"] and not item["warnings"]:
            print("  ✓ 全部通过")
        for e in item["errors"]:
            print(f"  ✗ {e['code']} {e['message']}")
        for w in item["warnings"]:
            print(f"  ! {w['code']} {w['message']}")
        print()

    verdict = "通过" if total_e == 0 else "不通过（有 E 级问题）"
    print(f"汇总: E {total_e} · W {total_w} → {verdict}")
    return 0 if total_e == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
