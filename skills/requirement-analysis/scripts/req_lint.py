#!/usr/bin/env python3
"""需求模型闸门（req_lint）

校验 `需求模型.md` 是否满足本 skill 的铁律。只判文本结构上可机械判定的部分，
判不了的内容（这条规则写得对不对、有没有漏关键业务）不在本脚本职责内。

用法：
    python3 req_lint.py 需求模型.md
    python3 req_lint.py 需求模型.md --json
    python3 req_lint.py 需求模型.md --min-severity W   # E 与 W 都显示（默认）

退出码：E 级问题 >= 1 时为 1（阻断定稿），否则为 0。

检查项：
  E001 缺段（十二段任一缺失）
  E002 段内容为空（空段必须写「已核对，无此类要素」，不能留白）
  E003 编号条目缺来源标注 [SRC-*]
  E004 状态类条目缺少对应的非法迁移（或非法迁移未写拦截方式）
  E005 接口条目缺失败态
  E006 未决项缺「向谁确认」，或只写了待确认/TBD
  E007 出现不可判定表述（功能正常/符合预期/表现良好…）
  E008 非功能约束的数值列为空或不含数字
  E009 可测性条目的观测点（OBS）为空
  E010 自动化分级不在 A/B/C 之内
  E011 出现 SRC-VERBAL 但未在同一行引用未决项编号
  W001 单个表格超过 40 行（建议拆分）
  W002 未决项超过 10 条（需求可能尚未成熟）
  W003 文件头缺基线与 commit
  W004 编号重复
  W005 可测性条目多于自动化分级条目（有可测项未分级）
  W006 第 12 段未写「不验」范围
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 结构定义

SECTION_SPEC = [
    (1, "目标与非目标", ("目标",)),
    (2, "角色与权限", ("角色",)),
    (3, "状态与迁移", ("状态",)),
    (4, "数据契约", ("数据", "字段")),
    (5, "接口与依赖", ("接口",)),
    (6, "业务规则", ("规则",)),
    (7, "异常与降级", ("异常",)),
    (8, "非功能约束", ("非功能",)),
    (9, "可测性评估", ("可测",)),
    (10, "自动化分级", ("自动化",)),
    (11, "未决项", ("未决",)),
    (12, "验证边界与移交", ("边界", "移交")),
]

# 这些编号类型的条目必须能指回来源
NEED_SOURCE = {"REQ", "FLD", "API", "EX", "NFR", "ST"}

ID_RE = re.compile(r"^\s*`?([A-Z]{2,4})-(\d{1,3})")
SECTION_RE = re.compile(r"^##(?!#)\s*(\d{1,2})(?!\d)(?!\.\d)\s*(?:[.、．]\s*)?(.*)$")
SRC_RE = re.compile(r"\[SRC-[^\]]*\]")
SRC_VERBAL_RE = re.compile(r"SRC-VERBAL")
OQ_REF_RE = re.compile(r"OQ-\d{1,3}")
HAS_DIGIT_RE = re.compile(r"\d")

# 不可判定表述：写这些词等于没写预期结果
VAGUE_PHRASES = [
    "功能正常", "工作正常", "正常运行", "正常显示", "显示正常", "表现良好",
    "符合预期", "无明显异常", "无异常现象", "效果良好", "一切正常",
    "无明显问题", "行为正确", "结果正确", "处理正常",
]

EMPTY_OQ_MARKERS = {"", "-", "—", "/", "待确认", "待定", "tbd", "TBD", "TODO", "?"}


# ---------------------------------------------------------------- 解析工具

def cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_sep(line: str) -> bool:
    s = line.strip().strip("|").strip()
    return bool(s) and "-" in s and set(s) <= set("-: |")


def find_tables(sec_lines: list[tuple[int, str]]) -> list[dict]:
    """把段内的连续表格行切成一个个表格块。"""
    tables: list[dict] = []
    block: list[tuple[int, list[str]]] = []

    def flush() -> None:
        nonlocal block
        if block:
            header_line, header = block[0]
            body = [(ln, cs) for ln, cs in block[1:] if not is_sep("|".join(cs))]
            # 表头必须像表头（含表头分隔行的表格一定会被识别）
            if header and any("-" in "".join(cs) for _, cs in block[1:2]):
                tables.append({"header": header, "rows": body, "line": header_line})
            elif header and not any(is_sep("|".join(cs)) for _, cs in block[1:]):
                # 无分隔行时仍按表格处理，但只在有多列时
                if len(header) > 1:
                    tables.append({"header": header, "rows": body, "line": header_line})
        block = []

    for lineno, raw in sec_lines:
        if raw.strip().startswith("|"):
            block.append((lineno, cells(raw)))
        else:
            flush()
    flush()
    return tables


def col_index(header: list[str], *keys: str) -> int | None:
    for i, h in enumerate(header):
        for k in keys:
            if k and k in h:
                return i
    return None


def get_row_cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


# ---------------------------------------------------------------- 检查主体

def check(path: Path) -> tuple[list[dict], list[dict], dict]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 切段
    secs: dict[int, dict] = {}
    cur: int | None = None
    for i, ln in enumerate(lines, 1):
        m = SECTION_RE.match(ln)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 12:
                cur = num
                if num not in secs:
                    secs[num] = {"title": m.group(2).strip(), "start": i, "lines": []}
                continue
        if cur is not None:
            secs[cur]["lines"].append((i, ln))

    errors: list[dict] = []
    warnings: list[dict] = []

    def err(code: str, sec: int | None, line: int | None, msg: str) -> None:
        errors.append({"code": code, "section": sec, "line": line, "message": msg})

    def warn(code: str, sec: int | None, line: int | None, msg: str) -> None:
        warnings.append({"code": code, "section": sec, "line": line, "message": msg})

    # E001 缺段
    for num, name, keys in SECTION_SPEC:
        if num not in secs:
            err("E001", num, None, f"缺少第 {num} 段「{name}」")
            continue
        title = secs[num]["title"]
        if not any(k in title for k in keys):
            warn("W007", num, secs[num]["start"],
                 f"第 {num} 段标题「{title}」未包含预期关键词（{'/'.join(keys)}），请确认段意未偏离")

    # E002 空段
    for num, spec in secs.items():
        body = [ln for _, ln in spec["lines"] if ln.strip()]
        if not body:
            err("E002", num, spec["start"],
                f"第 {num} 段为空。空段必须写明「已核对，无此类要素」并给依据，留白无法区分「没有」和「没查」")

    tables_by_sec: dict[int, list[dict]] = {num: find_tables(spec["lines"]) for num, spec in secs.items()}

    # E003 编号条目缺来源
    for num, tables in tables_by_sec.items():
        for t in tables:
            for lineno, row in t["rows"]:
                if not row:
                    continue
                m = ID_RE.match(row[0])
                if not m:
                    continue
                kind = m.group(1)
                if kind in NEED_SOURCE and not SRC_RE.search(" ".join(row)):
                    err("E003", num, lineno,
                        f"{m.group(0).strip()} 缺来源标注。每条结论必须能指回章节 / 接口 / 代码行（[SRC-*]）")

    # E004 状态缺非法迁移
    if 3 in tables_by_sec:
        state_ids: list[tuple[int, str]] = []
        illegal_table = None
        for t in tables_by_sec[3]:
            if col_index(t["header"], "拦截方式") is not None:
                illegal_table = t
            if col_index(t["header"], "状态") is not None and col_index(t["header"], "终态") is not None:
                for lineno, row in t["rows"]:
                    m = ID_RE.match(row[0]) if row else None
                    if m and m.group(1) == "ST":
                        state_ids.append((lineno, m.group(0).strip()))
        if state_ids and illegal_table is None:
            err("E004", 3, secs[3]["start"],
                "第 3 段没有非法迁移表（缺「拦截方式」列）。每个状态至少需要一条非法迁移并写明拦截方式")
        elif state_ids and illegal_table is not None:
            covered = set()
            for _, row in illegal_table["rows"]:
                m = ID_RE.match(row[0]) if row else None
                if m:
                    covered.add(m.group(0).strip())
            for lineno, sid in state_ids:
                if sid not in covered:
                    err("E004", 3, lineno,
                        f"{sid} 没有对应的非法迁移条目。每个状态至少一条「不允许发生」的尝试及拦截方式")

    # E005 接口缺失败态
    if 5 in tables_by_sec:
        for t in tables_by_sec[5]:
            idx = col_index(t["header"], "失败态", "失败")
            if idx is None:
                continue
            for lineno, row in t["rows"]:
                m = ID_RE.match(row[0]) if row else None
                if not m or m.group(1) != "API":
                    continue
                if get_row_cell(row, idx) in EMPTY_OQ_MARKERS:
                    err("E005", 5, lineno, f"{m.group(0).strip()} 缺失败态。只写成功态会在联调期集中暴雷")

    # E008 非功能约束无数值
    if 8 in tables_by_sec:
        nfr_seen = 0
        for t in tables_by_sec[8]:
            idx = col_index(t["header"], "数值", "指标值")
            if idx is None:
                continue
            for lineno, row in t["rows"]:
                m = ID_RE.match(row[0]) if row else None
                if not m or m.group(1) != "NFR":
                    continue
                nfr_seen += 1
                val = get_row_cell(row, idx)
                if not val or not HAS_DIGIT_RE.search(val):
                    err("E008", 8, lineno,
                        f"{m.group(0).strip()} 的数值列为空或不含数字。无量化指标只能判未决项，不能用形容词代替")
        if nfr_seen == 0:
            warn("W008", 8, secs[8]["start"], "第 8 段没有 NFR-* 条目，请确认确无非功能约束")

    # E009 可测性缺观测点
    if 9 in tables_by_sec:
        for t in tables_by_sec[9]:
            idx = col_index(t["header"], "OBS", "观测点")
            if idx is None:
                continue
            for lineno, row in t["rows"]:
                m = ID_RE.match(row[0]) if row else None
                if not m or m.group(1) != "TST":
                    continue
                if not get_row_cell(row, idx):
                    err("E009", 9, lineno,
                        f"{m.group(0).strip()} 的观测点为空。写不出观测点的规则在当前架构下不可验证")

    # E010 自动化分级非法值
    if 10 in tables_by_sec:
        for t in tables_by_sec[10]:
            idx = col_index(t["header"], "级别", "分级")
            if idx is None:
                continue
            for lineno, row in t["rows"]:
                m = ID_RE.match(row[0]) if row else None
                if not m or m.group(1) != "AUTO":
                    continue
                val = get_row_cell(row, idx)
                if val not in {"A", "B", "C"}:
                    err("E010", 10, lineno,
                        f"{m.group(0).strip()} 的级别为「{val or '空'}」，只能是 A / B / C")

    # E006 未决项缺责任人
    if 11 in tables_by_sec:
        oq_count = 0
        for t in tables_by_sec[11]:
            idx = col_index(t["header"], "向谁确认", "责任人", "确认人")
            if idx is None:
                continue
            for lineno, row in t["rows"]:
                m = ID_RE.match(row[0]) if row else None
                if not m or m.group(1) != "OQ":
                    continue
                oq_count += 1
                who = get_row_cell(row, idx)
                if who in EMPTY_OQ_MARKERS:
                    err("E006", 11, lineno,
                        f"{m.group(0).strip()} 没有「向谁确认」。「待确认」三个字不是责任人，问题会永远没人答")
        if oq_count > 10:
            warn("W002", 11, secs[11]["start"],
                 f"未决项 {oq_count} 条（>10），需求可能尚未成熟，建议先做一轮集中澄清再定稿")

    # E007 不可判定表述
    for i, ln in enumerate(lines, 1):
        for phrase in VAGUE_PHRASES:
            if phrase in ln:
                err("E007", None, i,
                    f"出现不可判定表述「{phrase}」。预期结果必须能被机器或明确的人工判据判真假")
                break

    # E011 SRC-VERBAL 未挂未决项
    for i, ln in enumerate(lines, 1):
        if SRC_VERBAL_RE.search(ln) and not OQ_REF_RE.search(ln):
            err("E011", None, i,
                "SRC-VERBAL 来源未引用未决项编号（如 → OQ-01）。口头需求必须转成待确认事项")

    # W001 表格过长
    for num, tables in tables_by_sec.items():
        for t in tables:
            if len(t["rows"]) > 40:
                warn("W001", num, t["line"],
                     f"该表格 {len(t['rows'])} 行（>40），建议按子主题拆开，否则难以评审")

    # W003 缺基线
    head = "\n".join(lines[:20])
    if "基线" not in head and not re.search(r"\bcommit\b", text, re.I):
        warn("W003", None, None, "文件头部没有基线与 commit。无基线的模型无法判断三个月后是否还成立")

    # W004 编号重复（迁移表的首列是「从状态」引用，不是定义，跳过）
    def is_transition_table(header: list[str]) -> bool:
        return col_index(header, "从", "尝试") is not None

    seen: dict[str, int] = {}
    for num, tables in tables_by_sec.items():
        for t in tables:
            if is_transition_table(t["header"]):
                continue
            for lineno, row in t["rows"]:
                m = ID_RE.match(row[0]) if row else None
                if not m:
                    continue
                full = m.group(0).strip()
                if full in seen:
                    warn("W004", num, lineno, f"编号 {full} 重复（首次出现于第 {seen[full]} 行）")
                else:
                    seen[full] = lineno

    # W005 可测性项多于分级项
    tst_n = sum(1 for t in tables_by_sec.get(9, []) for _, r in t["rows"]
                if r and (m := ID_RE.match(r[0])) and m.group(1) == "TST")
    auto_n = sum(1 for t in tables_by_sec.get(10, []) for _, r in t["rows"]
                 if r and (m := ID_RE.match(r[0])) and m.group(1) == "AUTO")
    if tst_n > auto_n:
        warn("W005", 10, secs.get(10, {}).get("start"),
             f"可测性条目 {tst_n} 条、自动化分级 {auto_n} 条，有可测项未做分级")

    # W006 未写不验范围
    if 12 in secs:
        body12 = "\n".join(ln for _, ln in secs[12]["lines"])
        if "不验" not in body12:
            warn("W006", 12, secs[12]["start"],
                 "第 12 段未写「不验」范围及理由。只写验什么，评审时无法判断是否漏测")

    meta = {
        "file": str(path),
        "sections_found": sorted(secs.keys()),
        "sections_expected": [n for n, _, _ in SECTION_SPEC],
        "tst": tst_n,
        "auto": auto_n,
    }
    return errors, warnings, meta


# ---------------------------------------------------------------- 输出

def main() -> int:
    ap = argparse.ArgumentParser(description="需求模型闸门")
    ap.add_argument("file", help="需求模型 markdown 路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 2

    errors, warnings, meta = check(path)

    if args.json:
        print(json.dumps({
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "meta": meta,
        }, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    print("需求模型闸门 · req_lint")
    print(f"文件：{meta['file']}")
    print(f"段：{len(meta['sections_found'])}/12")
    print()

    for item in errors:
        loc = f"第 {item['line']} 行" if item["line"] else "全文"
        sec = f"[第 {item['section']} 段] " if item["section"] else ""
        print(f"  ✗ {item['code']} {sec}{loc}")
        print(f"      {item['message']}")
    for item in warnings:
        loc = f"第 {item['line']} 行" if item["line"] else "全文"
        sec = f"[第 {item['section']} 段] " if item["section"] else ""
        print(f"  ! {item['code']} {sec}{loc}")
        print(f"      {item['message']}")

    if not errors and not warnings:
        print("  ✓ 全部通过")

    print()
    verdict = "通过" if not errors else "不通过（E 级问题必须修复后才能定稿）"
    print(f"汇总: E {len(errors)} · W {len(warnings)} → {verdict}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
