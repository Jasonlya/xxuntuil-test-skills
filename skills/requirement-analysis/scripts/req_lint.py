#!/usr/bin/env python3
"""需求测试分析闸门（req_lint）

结构不写死在脚本里。几段、每段由哪些块组成、每个表格必须有哪些列、每列承担
什么语义、跨表要满足什么约束，全部来自 assets/req-model.schema.json。
脚本里没有出现任何段号，也没有出现任何编号前缀——需要定位时按 schema 里的
section key 查（如 key="evidence"）。改结构只改 schema。

用法：
    python3 req_lint.py 需求测试分析.md
    python3 req_lint.py 需求测试分析.md --json
    python3 req_lint.py --describe                    # 打印输出契约
    python3 req_lint.py 需求测试分析.md --schema ./x.json # 换一份 schema

退出码：E 级 >= 1 时为 1（阻断定稿）；0 表示无 E；2 表示输入或 schema 本身有问题。

检查项：
  E001 缺段
  E002 段内容为空（声明为空可豁免，见 W007）
  E003 编号条目缺来源标注 [SRC-*]
  E004 状态没有对应的非法迁移（保留码位：v2 用「维度=状态」的分析项表达，schema 里不再有状态表）
  E005 接口缺失败态（保留码位：v2 用「维度=异常」的分析项表达）
  E006 待澄清项缺「向谁确认」，或只写了待确认/TBD
  E007 出现不可判定表述（功能正常 / 符合预期 / 表现良好 …）
  E008 非功能指标的数值为空（保留码位：v2 用「维度=性能」的分析项 + 关键取值列表达）
  E009 分析项的观测点为空
  E010 自动化分级不在 A/B/C 之内
  E011 出现 SRC-VERBAL 但未在同一行引用待澄清编号
  E012 缺 schema 要求的必需列
  E013 缺 schema 要求的必需块（表格 / 段落 / 代码块）
  E014 移交索引里的条数与实际不符
  E015 引用指向不存在的编号
  E016 编号格式不符（前缀错或序号不是两位以上）
  E017 必填单元格为空
  E018 枚举值不在允许范围内
  E019 表格行数少于 schema 要求
  E020 小节列表项少于 schema 要求
  E021 判 C 却没写复核条件
  E022 必需文本过短（低于 schema 的 min_len），通常是「正常」「符合要求」这类不成句内容
  E023 功能点没有任何分析项
  E024 位置列只有载体没有位置（写「PRD」「文档」「代码」）
  E025 原文摘录是指代而非原句（写「详见」「同上」）
  E026 功能点没有任何证据支撑
  W001 单个表格超过 40 行
  W002 待澄清项过多，需求可能尚未成熟
  W003 文件头缺基线与 commit
  W004 编号重复
  W006 段标题未含预期关键词
  W007 声明为空的段，但 schema 要求有内容
  W008 表格存在 schema 未定义的列
  W009 列顺序与 schema 不一致
  W010 移交索引无法解析
  W011 分析项没有证据支撑
  W012 全部分析项都是正常流维度（没做异常与边界分析）
  W013 强证据占比过低
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "assets" / "req-model.schema.json"

ROLES = {"id", "source", "text", "enum", "number", "ref", "person", "locator", "quote", "any"}
BLOCK_TYPES = {"table", "prose", "code"}

# 目前实现的跨表约束。schema 里写了别的名字会以退出码 2 拒绝运行——
# 未实现的约束如果被静默跳过，schema 看起来声明了校验，实际上什么都没查。
KNOWN_CONSTRAINTS = {
    "fp_has_analysis",
    "every_fp_has_evidence",
    "every_ta_has_evidence",
    "c_requires_review_condition",
    "normal_flow_only",
    "weak_evidence_dominance",
    "handover_index_consistency",
}

SECTION_RE = re.compile(r"^##(?!#)\s*(\d{1,2})(?!\d)(?!\.\d)\s*(?:[.、．]\s*)?(.*)$")
SRC_RE = re.compile(r"\[SRC-[^\]]*\]")
SRC_VERBAL_RE = re.compile(r"SRC-VERBAL")
# 全文扫描用：只认 [SRC-VERBAL 这种真正的来源标注，避免正文里提到标记名就被误伤
SRC_VERBAL_BRACKET_RE = re.compile(r"\[SRC-VERBAL")
OQ_REF_RE = re.compile(r"OQ-\d{1,3}")
ID_BODY_RE = re.compile(r"^([A-Z]{2,4})-(\d{1,3})$")
DIGIT_RE = re.compile(r"\d")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")

# ref 列支持一行多个编号：FP-01、TA-03 / FP-01,TA-03
REF_SPLIT_RE = re.compile(r"[、,，/／;；]+")
# 位置必须落到具体处所，下面这些只有载体没有位置
LOCATOR_BARE = {
    "", "-", "—", "/", "prd", "PRD", "文档", "需求", "需求文档", "代码", "源码",
    "设计", "设计文档", "接口", "接口文档", "原型", "群聊", "会议", "口头",
}
# 摘录以这些词开头，说明写的是指针而不是原句
QUOTE_POINTER_PREFIX = ("详见", "参见", "见第", "见上", "见下", "同上", "同前", "略", "如前")

VAGUE_PHRASES = [
    "功能正常", "工作正常", "正常运行", "正常显示", "显示正常", "表现良好",
    "符合预期", "无明显异常", "无异常现象", "效果良好", "一切正常",
    "无明显问题", "行为正确", "结果正确", "处理正常",
]

EMPTY_PERSON = {"", "-", "—", "/", "待确认", "待定", "tbd", "TBD", "TODO", "?", "待定待确认", "无"}
EMPTY_CELL = {"", "-", "—", "/"}

# 段被显式声明为空时的豁免措辞（铁律二）
DECLARED_EMPTY_RE = re.compile(r"已核对|无此类要素|无此类|不适用本需求|本需求不涉及")

INDEX_FP_N = re.compile(r"(\d+)\s*个功能点")
INDEX_TA_N = re.compile(r"(\d+)\s*条分析")
INDEX_EVD_N = re.compile(r"(\d+)\s*条证据")
INDEX_OQ_N = re.compile(r"(\d+)\s*个待澄清")
INDEX_OQ_DONE = re.compile(r"[（(]\s*(\d+)\s*已裁决\s*[）)]")
INDEX_ABC = re.compile(r"A\s*(\d+)\s*/\s*B\s*(\d+)\s*/\s*C\s*(\d+)")


class InputError(Exception):
    """输入或 schema 自身的问题，不是被检文档的问题。"""


# ---------------------------------------------------------------- schema

def load_schema(path: Path) -> dict:
    if not path.exists():
        raise InputError(f"schema 不存在：{path}")
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InputError(f"schema 不是合法 JSON：{path}:{e.lineno}:{e.colno} {e.msg}")

    for key in ("schema", "version", "sections"):
        if key not in data:
            raise InputError(f"schema 缺顶层字段「{key}」")

    sections = data["sections"]
    if not isinstance(sections, list) or not sections:
        raise InputError("schema 的 sections 必须是非空数组")

    numbers = [s.get("no") for s in sections]
    if numbers != list(range(1, len(sections) + 1)):
        raise InputError(f"schema 的段号必须从 1 连续递增，实际为 {numbers}")

    keys = [s.get("key") for s in sections]
    if len(set(keys)) != len(keys):
        raise InputError(f"schema 的段 key 必须唯一，实际为 {keys}")

    # 约束可以写在顶层（推荐，带 on 声明作用于哪些段），也兼容旧版段级字符串引用
    raw_constraints = data.get("constraints", [])
    declared_names: set[str] = set()
    if isinstance(raw_constraints, dict):
        norm = [{"name": k, "on": [], "level": "E"} for k in raw_constraints]
    elif isinstance(raw_constraints, list):
        norm = []
        for c in raw_constraints:
            if isinstance(c, str):
                c = {"name": c, "on": [], "level": "E"}
            if not isinstance(c, dict) or "name" not in c:
                raise InputError(f"schema 的 constraints 条目缺少 name：{c}")
            for k in c.get("on", []):
                if k not in keys:
                    raise InputError(f"约束「{c['name']}」声明作用于段 key「{k}」，但 sections 里没有这个 key")
            if c["name"] not in KNOWN_CONSTRAINTS:
                raise InputError(
                    f"schema 声明了约束「{c['name']}」，但脚本没有实现它。"
                    f"已实现：{sorted(KNOWN_CONSTRAINTS)}。"
                    f"未实现的约束会被静默跳过，因此这里直接报错")
            declared_names.add(c["name"])
            norm.append(c)
    else:
        raise InputError("schema 的 constraints 必须是数组或对象")
    data["_constraints"] = norm

    for sec in sections:
        no = sec["no"]
        for key in ("no", "key", "title", "blocks"):
            if key not in sec:
                raise InputError(f"schema 第 {no} 段缺字段「{key}」")
        if not sec["blocks"]:
            raise InputError(f"schema 第 {no} 段没有任何 block")
        for cn in sec.get("constraints", []):
            if cn not in declared_names:
                raise InputError(
                    f"schema 第 {no} 段声明了约束「{cn}」，但 constraints 里没有它的定义。"
                    f"未定义的约束会被静默跳过，因此这里直接报错")
        for b in sec["blocks"]:
            bt = b.get("type")
            if bt not in BLOCK_TYPES:
                raise InputError(f"schema 第 {no} 段有未知块类型「{bt}」，只支持 {sorted(BLOCK_TYPES)}")
            if bt == "table":
                cols = b.get("columns")
                if not cols:
                    raise InputError(f"schema 第 {no} 段「{b.get('name')}」是表格但没有 columns")
                if b.get("id_prefix") and not any(c.get("role") == "id" for c in cols):
                    raise InputError(
                        f"schema 第 {no} 段「{b.get('name')}」声明了 id_prefix，但没有 role=id 的列")
                for c in cols:
                    if "name" not in c or "role" not in c:
                        raise InputError(f"schema 第 {no} 段「{b.get('name')}」有列缺 name 或 role：{c}")
                    if c["role"] not in ROLES:
                        raise InputError(
                            f"schema 第 {no} 段列「{c['name']}」用了未知角色「{c['role']}」，只支持 {sorted(ROLES)}")
                    if c["role"] == "enum" and not c.get("values"):
                        raise InputError(f"schema 第 {no} 段列「{c['name']}」是 enum 但没有 values")
            elif bt == "prose":
                if not (b.get("must_contain") or b.get("name")):
                    raise InputError(f"schema 第 {no} 段有 prose 块，既无 must_contain 也无 name，无法定位")
            elif bt == "code":
                if not b.get("must_contain"):
                    raise InputError(f"schema 第 {no} 段的 code 块必须给 must_contain，否则无法区分是不是那个代码块")
    return data


# ---------------------------------------------------------------- 文档解析

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


def split_sections(lines: list[str]) -> dict[int, dict]:
    secs: dict[int, dict] = {}
    cur: int | None = None
    for i, ln in enumerate(lines, 1):
        m = SECTION_RE.match(ln)
        if m and 1 <= int(m.group(1)) <= 99:
            num = int(m.group(1))
            cur = num
            if num not in secs:
                secs[num] = {"title": m.group(2).strip(), "start": i, "lines": []}
            continue
        if cur is not None:
            secs[cur]["lines"].append((i, ln))
    return secs


def blocks_of(sec_lines: list[tuple[int, str]]) -> dict:
    """把段内内容切成表格 / 代码块 / 散文三类，互不重叠。"""
    tables, codes, prose = [], [], []
    i, n = 0, len(sec_lines)
    while i < n:
        lineno, raw = sec_lines[i]
        s = raw.strip()
        if s.startswith("```"):
            j = i + 1
            fence: list[str] = []
            while j < n and not sec_lines[j][1].strip().startswith("```"):
                fence.append(sec_lines[j][1])
                j += 1
            codes.append({"line": lineno, "text": "\n".join(fence)})
            i = j + 1
            continue
        if s.startswith("|"):
            j = i
            chunk: list[tuple[int, str]] = []
            while j < n and sec_lines[j][1].strip().startswith("|"):
                chunk.append(sec_lines[j])
                j += 1
            header = cells(chunk[0][1])
            body = [(ln, cells(r)) for ln, r in chunk[1:] if not is_sep(r)]
            tables.append({"header": header, "rows": body, "line": chunk[0][0]})
            i = j
            continue
        prose.append((lineno, raw))
        i += 1
    return {"tables": tables, "codes": codes, "prose": prose}


def header_contains(header: list[str], names: list[str]) -> bool:
    return all(any(n in h for h in header) for n in names)


def resolve_columns(header: list[str], spec: list[dict]) -> tuple[dict[str, int], set[int]]:
    """按 schema 的列名定位实际列：先精确、再包含，已占用的不重复分配。"""
    colmap: dict[str, int] = {}
    taken: set[int] = set()
    for c in spec:
        name = c["name"]
        idx = None
        for i, h in enumerate(header):
            if i not in taken and h.strip() == name:
                idx = i
                break
        if idx is None:
            for i, h in enumerate(header):
                if i not in taken and name in h:
                    idx = i
                    break
        if idx is not None:
            colmap[name] = idx
            taken.add(idx)
    return colmap, taken


# ---------------------------------------------------------------- 检查主体

def check(path: Path, schema: dict) -> tuple[list[dict], list[dict], dict]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    errors: list[dict] = []
    warnings: list[dict] = []

    def err(code: str, sec: int | None, line: int | None, msg: str) -> None:
        errors.append({"code": code, "section": sec, "line": line, "message": msg})

    def warn(code: str, sec: int | None, line: int | None, msg: str) -> None:
        warnings.append({"code": code, "section": sec, "line": line, "message": msg})

    secs = split_sections(lines)
    spec_by_no = {s["no"]: s for s in schema["sections"]}

    # E001 缺段
    for no, spec in spec_by_no.items():
        if no not in secs:
            err("E001", no, None, f"缺少第 {no} 段「{spec['title']}」")
            continue
        title = secs[no]["title"]
        keys = spec.get("title_keywords") or []
        if keys and not any(k in title for k in keys):
            warn("W006", no, secs[no]["start"],
                 f"第 {no} 段标题「{title}」未含预期关键词（{'/'.join(keys)}），请确认段意未偏离")

    # E002 空段
    for no, s in secs.items():
        if no in spec_by_no and not [ln for _, ln in s["lines"] if ln.strip()]:
            err("E002", no, s["start"],
                f"第 {no} 段为空。空段必须写明「已核对，无此类要素」并给依据，留白无法区分「没有」和「没查」")

    # 逐段匹配块
    matched: dict[int, dict] = {}
    for no, spec in spec_by_no.items():
        if no not in secs:
            continue
        seg = blocks_of(secs[no]["lines"])
        declared_empty = any(DECLARED_EMPTY_RE.search(ln) for _, ln in seg["prose"])
        claimed: set[int] = set()
        prose_text = "\n".join(ln for _, ln in seg["prose"])
        hit: dict[str, dict] = {"tables": {}, "prose": {}, "code": {}, "declared_empty": declared_empty}

        for b in spec["blocks"]:
            bt, name = b["type"], b.get("name", b["type"])
            if bt == "table":
                target = None
                if b.get("identify_by"):
                    for ti, t in enumerate(seg["tables"]):
                        if ti in claimed:
                            continue
                        if header_contains(t["header"], b["identify_by"]):
                            target = ti
                            break
                else:
                    for ti in range(len(seg["tables"])):
                        if ti not in claimed:
                            target = ti
                            break
                if target is None:
                    # 退一步：段内只剩一张没被占用的表，就用它。
                    # 否则「少了一列」会被误报成「缺整块」——前者是结构违约(E012)，
                    # 后者是整块没写(E013)，修法完全不同。
                    remaining = [ti for ti in range(len(seg["tables"])) if ti not in claimed]
                    if len(remaining) == 1:
                        target = remaining[0]
                if target is None:
                    if not b.get("required", True):
                        continue
                    if declared_empty:
                        warn("W007", no, secs[no]["start"],
                             f"第 {no} 段声明为空，但 schema 要求「{name}」。若确实没有，请把依据写清；若只是没查，请补齐")
                    else:
                        hint = f"（识别依据：包含列 {'/'.join(b['identify_by'])}）" if b.get("identify_by") else ""
                        err("E013", no, secs[no]["start"],
                            f"第 {no} 段缺「{name}」表格{hint}。结构契约见 assets/req-model.schema.json")
                    continue
                claimed.add(target)
                hit["tables"][name] = {"table": seg["tables"][target], "block": b}

            elif bt == "prose":
                keys = b.get("must_contain") or [name]
                if not any(k in prose_text for k in keys):
                    if b.get("required", True):
                        if declared_empty:
                            warn("W007", no, secs[no]["start"],
                                 f"第 {no} 段声明为空，但 schema 要求「{name}」小节")
                        else:
                            err("E013", no, secs[no]["start"],
                                f"第 {no} 段缺「{name}」小节（未出现 {'/'.join(keys)}）")
                    continue
                hit["prose"][name] = b

            elif bt == "code":
                keys = b.get("must_contain") or []
                found = None
                for ci, c in enumerate(seg["codes"]):
                    if ci in claimed:
                        continue
                    if all(k in c["text"] for k in keys):
                        found = ci
                        break
                if found is None:
                    if b.get("required", True):
                        if declared_empty:
                            warn("W007", no, secs[no]["start"],
                                 f"第 {no} 段声明为空，但 schema 要求「{name}」代码块")
                        else:
                            err("E013", no, secs[no]["start"],
                                f"第 {no} 段缺「{name}」代码块（未找到同时含 {'/'.join(keys)} 的代码块）")
                    continue
                claimed.add(found)
                hit["code"][name] = seg["codes"][found]

        matched[no] = hit

    # ---- 表格结构：缺列 / 多列 / 列序 / 行数
    layouts: list[dict] = []  # {sec, name, block, table, colmap}
    for no, hit in matched.items():
        for name, item in hit["tables"].items():
            t, b = item["table"], item["block"]
            colmap, taken = resolve_columns(t["header"], b["columns"])
            missing = [c["name"] for c in b["columns"]
                       if c.get("required", True) and c["name"] not in colmap]
            if missing:
                err("E012", no, t["line"],
                    f"第 {no} 段「{name}」缺必需列：{'、'.join(missing)}。"
                    f"实际表头：{' | '.join(t['header'])}")
            extra = [h for i, h in enumerate(t["header"]) if i not in taken and h.strip()]
            if extra:
                warn("W008", no, t["line"],
                     f"第 {no} 段「{name}」有 schema 未定义的列：{'、'.join(extra)}。若是有意扩展请在 schema 里补上，否则可能是列名写错")
            ordered = [colmap[c["name"]] for c in b["columns"] if c["name"] in colmap]
            if ordered != sorted(ordered):
                warn("W009", no, t["line"],
                     f"第 {no} 段「{name}」的列顺序与 schema 不一致（schema 顺序：{'、'.join(c['name'] for c in b['columns'])}）")
            need_rows = b.get("min_rows", 0)
            if need_rows and len(t["rows"]) < need_rows:
                err("E019", no, t["line"],
                    f"第 {no} 段「{name}」只有 {len(t['rows'])} 行，schema 要求至少 {need_rows} 行")
            if len(t["rows"]) > 40:
                warn("W001", no, t["line"],
                     f"第 {no} 段「{name}」共 {len(t['rows'])} 行（>40），建议按子主题拆开，否则难以评审")
            layouts.append({"sec": no, "name": name, "block": b, "table": t, "colmap": colmap})

    # ---- 单元格：第一遍收集 id，第二遍校验（ref 需要全量 id 才能判）
    id_index: dict[str, tuple[int, int]] = {}
    ids_by_prefix: dict[str, list[str]] = {}
    for lay in layouts:
        b, t, colmap = lay["block"], lay["table"], lay["colmap"]
        id_col = next((c for c in b["columns"] if c["role"] == "id"), None)
        if not id_col:
            continue
        idx = colmap.get(id_col["name"])
        if idx is None:
            continue
        prefix = b.get("id_prefix")
        for lineno, row in t["rows"]:
            val = row[idx] if idx < len(row) else ""
            m = ID_BODY_RE.match(val.strip().strip("`"))
            if not m:
                continue
            full = val.strip().strip("`")
            if full in id_index:
                warn("W004", lay["sec"], lineno,
                     f"编号 {full} 重复（首次出现于第 {id_index[full][1]} 行）。编号不复用，删除的留空")
            else:
                id_index[full] = (lay["sec"], lineno)
            if prefix and m.group(1) != prefix:
                continue
            ids_by_prefix.setdefault(m.group(1), []).append(full)

    for lay in layouts:
        no, name, b, t, colmap = lay["sec"], lay["name"], lay["block"], lay["table"], lay["colmap"]
        id_col = next((c for c in b["columns"] if c["role"] == "id"), None)
        id_idx = colmap.get(id_col["name"]) if id_col else None

        for lineno, row in t["rows"]:
            if not any(c.strip() for c in row):
                continue
            rid = row[id_idx].strip().strip("`") if id_idx is not None and id_idx < len(row) else ""
            label = rid or f"第 {no} 段「{name}」第 {lineno} 行"

            for c in b["columns"]:
                idx = colmap.get(c["name"])
                if idx is None:
                    continue
                val = row[idx].strip() if idx < len(row) else ""
                role = c["role"]
                required = c.get("required", True)

                if role == "id":
                    if not val:
                        err("E017", no, lineno, f"{label} 的「{c['name']}」为空。每条条目必须有编号")
                        continue
                    m = ID_BODY_RE.match(val.strip("`"))
                    if not m:
                        err("E016", no, lineno,
                            f"{label} 的编号「{val}」格式不符，应为 大写前缀-两位以上序号（如 REQ-01）")
                    else:
                        prefix = b.get("id_prefix")
                        if prefix and m.group(1) != prefix:
                            err("E016", no, lineno,
                                f"{label} 的编号前缀应为 {prefix}-，实际为 {m.group(1)}-")
                        elif len(m.group(2)) < 2:
                            err("E016", no, lineno,
                                f"{label} 的序号「{m.group(2)}」不足两位。写成 {m.group(1)}-0{m.group(2)}，否则排序会乱")
                    continue

                if role == "source":
                    if val in EMPTY_CELL or not SRC_RE.search(val):
                        err("E003", no, lineno,
                            f"{label} 的「{c['name']}」缺来源标注。每条结论必须能指回章节 / 接口 / 代码行（[SRC-*]）")
                    elif SRC_VERBAL_RE.search(val) and not OQ_REF_RE.search(" ".join(row)):
                        err("E011", no, lineno,
                            f"{label} 的 SRC-VERBAL 来源未引用未决项编号（如 → OQ-01）。口头需求必须转成待确认事项")
                    continue

                if role == "person":
                    if val in EMPTY_PERSON:
                        err(c.get("empty_code", "E006"), no, lineno,
                            f"{label} 的「{c['name']}」为「{val or '空'}」。「待确认」三个字不是责任人，问题会永远没人答")
                    continue

                if role == "ref":
                    if not val:
                        if required:
                            err("E017", no, lineno, f"{label} 的「{c['name']}」为空，必须指向一条具体条目")
                        continue
                    # 一行可挂多条：支撑对象 / 影响对象 天然是一对多
                    for one in [x.strip().strip("`") for x in REF_SPLIT_RE.split(val) if x.strip()]:
                        m = ID_BODY_RE.match(one)
                        if not m:
                            err("E016", no, lineno, f"{label} 的「{c['name']}」里「{one}」不是编号格式")
                            continue
                        allowed = c.get("ref_prefix")
                        if allowed and m.group(1) not in allowed:
                            err("E016", no, lineno,
                                f"{label} 的「{c['name']}」指向 {m.group(1)}-，允许的前缀为 {'/'.join(allowed)}")
                        if one not in id_index:
                            err("E015", no, lineno,
                                f"{label} 的「{c['name']}」指向 {one}，但文档里没有这个编号")
                    continue

                if role == "locator":
                    if not val or val in EMPTY_CELL:
                        if required:
                            err(c.get("empty_code", "E024"), no, lineno,
                                f"{label} 的「{c['name']}」为空")
                        continue
                    if val.strip().lower() in LOCATOR_BARE or len(val) < 4:
                        err(c.get("empty_code", "E024"), no, lineno,
                            f"{label} 的「{c['name']}」只写了「{val}」，落不到具体处所。"
                            f"要写成 文件:行 / PRD §2.1 / GET /api/login / 配置键")
                    continue

                if role == "quote":
                    if not val or val in EMPTY_CELL:
                        if required:
                            err(c.get("empty_code", "E025"), no, lineno,
                                f"{label} 的「{c['name']}」为空")
                        continue
                    bare = val.strip().strip("「」\"'“”")
                    if bare.startswith(QUOTE_POINTER_PREFIX) or len(bare) < 6:
                        err(c.get("empty_code", "E025"), no, lineno,
                            f"{label} 的「{c['name']}」写的是指代不是原句：「{val}」。"
                            f"证据要能被第三人独立核对，摘录必须是原文片段")
                    continue

                if role == "enum":
                    if not val:
                        if required:
                            err(c.get("empty_code", "E017"), no, lineno, f"{label} 的「{c['name']}」为空")
                        continue
                    if val not in c["values"]:
                        err(c.get("invalid_code", "E018"), no, lineno,
                            f"{label} 的「{c['name']}」为「{val}」，只能是 {' / '.join(c['values'])}")
                    continue

                if role == "number":
                    if not val:
                        if required:
                            err(c.get("empty_code", "E017"), no, lineno,
                                f"{label} 的「{c['name']}」为空。无量化指标只能判未决项，不能用形容词代替")
                        continue
                    if not DIGIT_RE.search(val):
                        err(c.get("empty_code", "E018"), no, lineno,
                            f"{label} 的「{c['name']}」为「{val}」，不含数字。数值列不接受形容词")
                    continue

                if role == "text":
                    if not val or val in EMPTY_CELL:
                        if required:
                            err(c.get("empty_code", "E017"), no, lineno,
                                f"{label} 的「{c['name']}」为空或只写了「{val}」")
                        continue
                    min_len = c.get("min_len", 0)
                    if min_len and len(val) < min_len:
                        err("E022", no, lineno,
                            f"{label} 的「{c['name']}」只有 {len(val)} 字，少于 {min_len} 字，"
                            f"大概率是「正常」「符合要求」这类不成句的内容")
                    continue

                if role == "any" and required and val in EMPTY_CELL:
                    err("E017", no, lineno, f"{label} 的「{c['name']}」为空")

    # ---- 散文块：列表项数量
    for no, hit in matched.items():
        for name, b in hit["prose"].items():
            need = b.get("min_list_items", 0)
            if not need:
                continue
            keys = b.get("must_contain") or [name]
            lines_no = secs[no]["lines"]
            start = None
            for k, (_, ln) in enumerate(lines_no):
                if any(kw in ln for kw in keys):
                    start = k
                    break
            if start is None:
                continue
            count = 0
            for _, ln in lines_no[start:]:
                if LIST_ITEM_RE.match(ln):
                    count += 1
            if count < need:
                err("E020", no, lines_no[start][0],
                    f"第 {no} 段「{name}」只有 {count} 条列表项，至少需要 {need} 条")

    # ---- 跨表约束
    # 段号一律按 schema 的 section key 解析，脚本里不出现任何数字段号；
    # 列名按 tag 定位，列改名不影响校验。要改语义就改 schema 里的 tag。
    key_no = {s["key"]: s["no"] for s in schema["sections"]}

    def col_of(sec_key: str, role: str | None = None, tag: str | None = None,
               name: str | None = None) -> list[tuple[int, str]]:
        target = key_no.get(sec_key)
        out: list[tuple[int, str]] = []
        for lay in layouts:
            if lay["sec"] != target:
                continue
            b, t, colmap = lay["block"], lay["table"], lay["colmap"]
            if name:
                wanted = name
            elif tag:
                wanted = next((c["name"] for c in b["columns"] if c.get("tag") == tag), None)
            else:
                wanted = next((c["name"] for c in b["columns"] if c["role"] == role), None)
            if wanted is None:
                continue
            idx = colmap.get(wanted)
            if idx is None:
                continue
            for lineno, row in t["rows"]:
                if idx < len(row) and row[idx].strip():
                    out.append((lineno, row[idx].strip().strip("`")))
        return out

    def refs_in(sec_key: str, role: str | None = None, name: str | None = None) -> set[str]:
        out: set[str] = set()
        for _, v in col_of(sec_key, role=role, name=name):
            for one in REF_SPLIT_RE.split(v):
                one = one.strip().strip("`")
                if one:
                    out.add(one)
        return out

    for c in schema.get("_constraints", []):
        cname = c["name"]

        if cname == "fp_has_analysis":
            covered = refs_in("analysis", name="功能点")
            for lineno, fid in col_of("fp", role="id"):
                if fid not in covered:
                    err("E023", key_no.get("fp"), lineno,
                        f"{fid} 没有任何分析项。功能点进了清单却没进测试计划，等于默认它不会出问题")

        elif cname == "every_fp_has_evidence":
            covered = refs_in("evidence", name="支撑对象")
            for lineno, fid in col_of("fp", role="id"):
                if fid not in covered:
                    err("E026", key_no.get("fp"), lineno,
                        f"{fid} 没有任何证据支撑。证据是本产物的立身之本，缺了就不是分析而是猜测；"
                        f"确实找不到出处的，把它降级为待澄清")

        elif cname == "every_ta_has_evidence":
            # 一条证据挂到功能点上，就覆盖该功能点下的全部分析项。只有
            # 「分析项自己没证据、所属功能点也没证据」才是真缺口。
            covered = refs_in("evidence", name="支撑对象")
            fp_by_line = dict(col_of("analysis", name="功能点"))
            for lineno, tid in col_of("analysis", role="id"):
                if tid in covered:
                    continue
                fids = {x.strip() for x in REF_SPLIT_RE.split(fp_by_line.get(lineno, "")) if x.strip()}
                if fids & covered:
                    continue
                warn("W011", key_no.get("analysis"), lineno,
                     f"{tid} 及其所属功能点都没有证据。这条分析目前只有分析方的判断支撑")

        elif cname == "c_requires_review_condition":
            grades = col_of("analysis", tag="automation")
            reviews = dict(col_of("analysis", tag="review_condition"))
            for lineno, v in grades:
                if v == "C" and reviews.get(lineno, "") in EMPTY_CELL:
                    err("E021", key_no.get("analysis"), lineno,
                        f"第 {lineno} 行判为 C 却没有「复核条件」。判 C 必须写清什么条件下重新评估，"
                        f"否则半年后会有人重评一遍")

        elif cname == "normal_flow_only":
            dims = [v for _, v in col_of("analysis", tag="dimension")]
            if dims and all(d == "正常流" for d in dims):
                warn("W012", key_no.get("analysis"), secs.get(key_no.get("analysis"), {}).get("start"),
                     f"{len(dims)} 条分析全是正常流维度。正常流只在实现缺失时失败，"
                     f"缺陷基本都在异常、边界、状态、权限里")

        elif cname == "weak_evidence_dominance":
            strengths = [v for _, v in col_of("evidence", tag="strength")]
            if strengths:
                strong = sum(1 for s in strengths if s == "强")
                ratio = strong / len(strengths)
                if ratio < 0.3:
                    warn("W013", key_no.get("evidence"), secs.get(key_no.get("evidence"), {}).get("start"),
                         f"强证据 {strong}/{len(strengths)}（{ratio:.0%}），低于 30%。"
                         f"结论主要来自文档转述或口头，交付前建议补接口实测或代码核对")

        elif cname == "handover_index_consistency":
            no_h = key_no.get("handover")
            code = matched.get(no_h, {}).get("code", {}).get("移交索引")
            if not code:
                continue
            body = code["text"]
            m_fp = INDEX_FP_N.search(body)
            m_ta = INDEX_TA_N.search(body)
            m_evd = INDEX_EVD_N.search(body)
            m_oq = INDEX_OQ_N.search(body)
            m_done = INDEX_OQ_DONE.search(body)
            m_abc = INDEX_ABC.search(body)
            if not (m_fp and m_ta and m_evd and m_oq and m_abc):
                forms = [b["format"] for b in spec_by_no[no_h]["blocks"]
                         if b["type"] == "code" and b.get("format")]
                warn("W010", no_h, code["line"],
                     "移交索引无法解析，期望格式："
                     + (forms[0] if forms else
                        "需求测试分析.md · F 个功能点 · T 条分析 · E 条证据 · O 个待澄清（K 已裁决）"
                        "· 自动化 Aa/Bb/Cc · 基线 branch@commit"))
                continue

            actual = {
                "功能点": len(col_of("fp", role="id")),
                "分析": len(col_of("analysis", role="id")),
                "证据": len(col_of("evidence", role="id")),
                "待澄清": len(col_of("oq", role="id")),
            }
            actual_done = sum(1 for _, v in col_of("oq", tag="oq_status") if v == "已裁决")
            grades = {g: 0 for g in "ABC"}
            for _, v in col_of("analysis", tag="automation"):
                if v in grades:
                    grades[v] += 1

            problems = []
            for label, m in (("功能点", m_fp), ("分析", m_ta), ("证据", m_evd), ("待澄清", m_oq)):
                if int(m.group(1)) != actual[label]:
                    problems.append(f"{label}数写 {m.group(1)}，实际 {actual[label]}")
            if m_done and int(m_done.group(1)) != actual_done:
                problems.append(f"已裁决数写 {m_done.group(1)}，实际 {actual_done}")
            declared_abc = [int(m_abc.group(1)), int(m_abc.group(2)), int(m_abc.group(3))]
            actual_abc = [grades["A"], grades["B"], grades["C"]]
            if declared_abc != actual_abc:
                problems.append(
                    f"分级写 A{declared_abc[0]}/B{declared_abc[1]}/C{declared_abc[2]}，"
                    f"实际 A{actual_abc[0]}/B{actual_abc[1]}/C{actual_abc[2]}")
            if problems:
                err("E014", no_h, code["line"],
                    "移交索引与实际条目不符：" + "；".join(problems) + "。下游只读这一行，写错就是发假数据")

    # ---- 全文类检查
    for i, ln in enumerate(lines, 1):
        for phrase in VAGUE_PHRASES:
            if phrase in ln:
                err("E007", None, i,
                    f"出现不可判定表述「{phrase}」。预期结果必须能被机器或明确的人工判据判真假")
                break

    for i, ln in enumerate(lines, 1):
        # 表格行里的 SRC-VERBAL 一律要求挂待澄清；正文里用反引号提到标记名的说明句不算
        hit = SRC_VERBAL_RE.search(ln) if ln.strip().startswith("|") else SRC_VERBAL_BRACKET_RE.search(ln)
        if hit and not OQ_REF_RE.search(ln):
            err("E011", None, i,
                "SRC-VERBAL 来源未引用未决项编号（如 → OQ-01）。口头需求必须转成待确认事项")

    fm = schema.get("frontmatter", {})
    head = "\n".join(lines[:20])
    if fm.get("must_contain_any") and not any(k in head for k in fm["must_contain_any"]):
        warn("W003", None, None, "文件头部没有基线与 commit。无基线的模型无法判断三个月后是否还成立")

    oq_no = key_no.get("oq")
    oq_n = len(col_of("oq", role="id"))
    if oq_n > 10:
        warn("W002", oq_no, secs.get(oq_no, {}).get("start"),
             f"待澄清 {oq_n} 条（>10），需求可能尚未成熟：先集中澄清一轮，再谈覆盖率")

    errors.sort(key=lambda x: (x["line"] or 0, x["code"]))
    warnings.sort(key=lambda x: (x["line"] or 0, x["code"]))
    meta = {
        "file": str(path),
        "schema": f"{schema['schema']} v{schema['version']}",
        "sections_found": sorted(secs.keys()),
        "sections_expected": len(schema["sections"]),
        "counts": {k: len(v) for k, v in sorted(ids_by_prefix.items())},
    }
    return errors, warnings, meta


# ---------------------------------------------------------------- 契约输出

def describe(schema: dict, shown_path: str = "assets/req-model.schema.json") -> None:
    print(f"{schema['schema']} · 输出契约 v{schema['version']}")
    print(f"结构来源：{shown_path}（唯一真相源，改结构只改这里）")
    if schema.get("note"):
        print()
        print(schema["note"])
    print()
    print("列角色（role）：")
    for role, desc in schema.get("roles", {}).items():
        print(f"  {role:8} {desc}")
    print()
    for sec in schema["sections"]:
        print(f"## {sec['no']}. {sec['title']}  (key: {sec['key']})")
        if sec.get("why"):
            print(f"   为什么：{sec['why']}")
        for b in sec["blocks"]:
            req = "必需" if b.get("required", True) else "可选"
            if b["type"] == "table":
                ident = f" · 识别：含 {'/'.join(b['identify_by'])}" if b.get("identify_by") else ""
                pre = f" · 前缀 {b['id_prefix']}" if b.get("id_prefix") else ""
                print(f"   块「{b.get('name')}」表格 · {req}{pre} · 最少 {b.get('min_rows', 0)} 行{ident}")
                print(f"     {'列':<16}{'角色':<8}{'必需':<6}约束")
                for c in b["columns"]:
                    constraint = ""
                    if c.get("values"):
                        constraint = " ∈ {" + " / ".join(c["values"]) + "}"
                    if c.get("ref_prefix"):
                        constraint += f" 指向 {'/'.join(c['ref_prefix'])}-*"
                    if c.get("min_len"):
                        constraint += f" ≥{c['min_len']} 字"
                    if c.get("note"):
                        constraint += f"  //{c['note']}"
                    print(f"     {c['name']:<16}{c['role']:<8}{'是' if c.get('required', True) else '否':<6}{constraint}")
            elif b["type"] == "prose":
                extra = []
                if b.get("must_contain"):
                    extra.append("含 " + "/".join(b["must_contain"]))
                if b.get("min_list_items"):
                    extra.append(f"≥{b['min_list_items']} 条列表项")
                print(f"   块「{b.get('name')}」小节 · {req} · {' · '.join(extra)}")
                if b.get("note"):
                    print(f"     //{b['note']}")
            else:
                print(f"   块「{b.get('name')}」代码块 · {req} · 含 {'/'.join(b.get('must_contain', []))}")
                if b.get("format"):
                    print(f"     格式：{b['format']}")
        for cn in sec.get("constraints", []):
            print(f"   约束 {cn}：{schema['constraints'][cn]}")
        print()


# ---------------------------------------------------------------- 入口

def main() -> int:
    ap = argparse.ArgumentParser(description="需求模型闸门（schema 驱动）")
    ap.add_argument("file", nargs="?", help="需求模型 markdown 路径")
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="schema 路径（默认取 skill 自带的）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--describe", action="store_true", help="打印输出契约后退出")
    args = ap.parse_args()

    try:
        schema = load_schema(Path(args.schema))
    except InputError as e:
        print(f"schema 错误：{e}", file=sys.stderr)
        return 2

    if args.describe:
        sp = Path(args.schema)
        try:
            shown = str(sp.resolve().relative_to(DEFAULT_SCHEMA.parent.parent))
        except (ValueError, OSError):
            shown = str(sp)
        describe(schema, shown)
        return 0

    if not args.file:
        ap.print_usage(sys.stderr)
        print("需要给出需求模型路径，或用 --describe 查看契约", file=sys.stderr)
        return 2

    path = Path(args.file)
    if not path.exists():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 2
    if not path.is_file():
        print(f"不是文件：{path}", file=sys.stderr)
        return 2

    errors, warnings, meta = check(path, schema)

    if args.json:
        print(json.dumps({
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "meta": meta,
        }, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    print("需求测试分析闸门 · req_lint")
    print(f"文件：{meta['file']}")
    print(f"契约：{meta['schema']}")
    print(f"段：{len(meta['sections_found'])}/{meta['sections_expected']}")
    if meta["counts"]:
        print("条目：" + " · ".join(f"{k} {v}" for k, v in meta["counts"].items()))
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
