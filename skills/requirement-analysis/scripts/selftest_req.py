#!/usr/bin/env python3
"""req_lint 自测：单点破坏模板，断言命中的错误码集合与预期完全一致。

为什么要有这个：闸门最危险的失败不是「报错太多」，而是「该报的没报」。
只证明「模板能过」没有意义——一个永远返回 0 的脚本也能过。这里逐条破坏，
断言每次只命中该命中的码，多一条少一条都算失败。

用法：
    python3 scripts/selftest_req.py
    python3 scripts/selftest_req.py -v     # 打印每个用例命中的码

退出码：全部符合预期 0，任一不符 1。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
TEMPLATE = SKILL / "assets" / "req-model-template.md"
SCHEMA = SKILL / "assets" / "req-model.schema.json"


def load_module():
    spec = importlib.util.spec_from_file_location("req_lint", HERE / "req_lint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- 变形工具

def table_block(text: str, marker: str, fn) -> str:
    """按表块处理：fn(kind, cells) -> cells，kind ∈ {header, sep, row}。

    表格必须整块处理——只改表头不改数据行，会造成整列错位，
    那样测的就不是「缺列」而是「数据串列」了。
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("|") and marker in s:
            j = i
            block = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                block.append(lines[j])
                j += 1
            for bi, b in enumerate(block):
                cs = [c.strip() for c in b.strip().strip("|").split("|")]
                kind = "sep" if (cs and set("".join(cs)) <= set("-:")) else ("header" if bi == 0 else "row")
                out.append("| " + " | ".join(fn(kind, cs)) + " |")
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def drop_col(marker: str, col: str):
    """按表头定位列号后整列删除（含分隔行），保持各行列数一致。"""
    def apply(text: str) -> str:
        holder: dict[str, int] = {}

        def fn(kind, cs):
            if kind == "header" and col in cs:
                holder["k"] = cs.index(col)
            k = holder.get("k")
            if k is None or k >= len(cs):
                return cs
            return cs[:k] + cs[k + 1:]
        return table_block(text, marker, fn)
    return apply


def add_col(marker: str, name: str):
    def apply(text: str) -> str:
        def fn(kind, cs):
            if kind == "sep":
                return cs + ["---"]
            if kind == "header":
                return cs + [name]
            return cs + [""]
        return table_block(text, marker, fn)
    return apply


def swap_cols(marker: str, a: int, b: int):
    def apply(text: str) -> str:
        def fn(kind, cs):
            cs = list(cs)
            if kind != "sep" and len(cs) > max(a, b):
                cs[a], cs[b] = cs[b], cs[a]
            return cs
        return table_block(text, marker, fn)
    return apply


def rename_col(marker: str, old: str, new: str):
    return lambda text: table_block(
        text, marker, lambda kind, cs: [new if (kind == "header" and c == old) else c for c in cs])


def set_cell(marker: str, row_key: str, col: str, value: str):
    """改某张表里首列为 row_key 的那行、列名为 col 的单元格。"""
    def apply(text: str) -> str:
        lines = text.splitlines()
        out, i = [], 0
        while i < len(lines):
            s = lines[i].strip()
            if s.startswith("|") and marker in s:
                j = i
                block = []
                while j < len(lines) and lines[j].strip().startswith("|"):
                    block.append(lines[j])
                    j += 1
                names = [c.strip() for c in block[0].strip().strip("|").split("|")]
                if col in names:
                    k = names.index(col)
                    for bi, b in enumerate(block):
                        cs = [c.strip() for c in b.strip().strip("|").split("|")]
                        if bi and cs and cs[0] == row_key and k < len(cs):
                            cs[k] = value
                            out.append("| " + " | ".join(cs) + " |")
                        else:
                            out.append(b)
                else:
                    out.extend(block)
                i = j
                continue
            out.append(lines[i])
            i += 1
        return "\n".join(out)
    return apply


def drop_rows(text: str, marker: str) -> str:
    """删掉某张表的全部数据行，只留表头与分隔行。"""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("|") and marker in s:
            out.append(lines[i])
            j = i + 1
            if j < len(lines) and set(lines[j].strip().replace("|", "").replace(" ", "")) <= set("-:"):
                out.append(lines[j])
                j += 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------- 用例

def build_cases(tpl: str) -> list[tuple[str, str, set[str]]]:
    """(说明, 变形后的文本, 期望命中的码集合)"""
    c: list[tuple[str, str, set[str]]] = []

    c.append(("删掉第 12 段", tpl[: tpl.index("## 12. 验证边界与移交")], {"E001"}))
    c.append(("接口表删失败态列", drop_col("| 编号 | 接口 |", "失败态")(tpl), {"E012"}))
    c.append(("可测表删 OBS 列", drop_col("| 编号 | 对应规则 |", "OBS 观测点")(tpl), {"E012"}))
    c.append(("规则表删来源列", drop_col("| 编号 | 规则（可判真假的陈述） |", "来源")(tpl), {"E012"}))
    c.append(("失败态列改名", rename_col("| 编号 | 接口 |", "失败态", "异常")(tpl), {"E012", "W008"}))
    c.append(("规则表加备注列", add_col("| 编号 | 规则（可判真假的陈述） |", "备注")(tpl), {"W008"}))
    c.append(("规则表整列对调", swap_cols("| 编号 | 规则（可判真假的陈述） |", 0, 1)(tpl), {"W009"}))
    c.append(("异常表清空数据行", drop_rows(tpl, "| 编号 | 场景 |"), {"E019", "E015"}))
    c.append(("删掉业务规则整表",
              tpl.replace(tpl[tpl.index("| 编号 | 规则（可判真假的陈述） |"):tpl.index("## 7. 异常与降级")], ""),
              {"E002", "E013", "E014", "E015"}))
    c.append(("移交索引分级不符", tpl.replace("自动化 A4/B2/C1", "自动化 A5/B1/C1"), {"E014"}))
    c.append(("移交索引写成待补", tpl.replace("自动化 A4/B2/C1", "自动化 待补"), {"W010"}))
    c.append(("可测项指向不存在编号", set_cell("| 编号 | 对应规则 |", "TST-01", "对应规则", "REQ-99")(tpl), {"E015"}))
    c.append(("编号写成一位数", set_cell("| 编号 | 规则（可判真假的陈述） |", "REQ-03", "编号", "REQ-3")(tpl), {"E016", "E015"}))
    c.append(("规则列来源写破折号", set_cell("| 编号 | 规则（可判真假的陈述） |", "REQ-02", "来源", "—")(tpl), {"E003"}))
    c.append(("接口失败态写破折号", set_cell("| 编号 | 接口 |", "API-02", "失败态", "—")(tpl), {"E005"}))
    c.append(("未决项责任写待确认", set_cell("| 编号 | 问题 |", "OQ-02", "向谁确认", "待确认")(tpl), {"E006"}))
    c.append(("用户可见结果写功能正常", set_cell("| 编号 | 场景 |", "EX-01", "用户可见结果", "功能正常")(tpl), {"E007"}))
    c.append(("非功能数值写很快", set_cell("| 编号 | 指标 |", "NFR-02", "数值", "很快")(tpl), {"E008"}))
    c.append(("观测点写破折号", set_cell("| 编号 | 对应规则 |", "TST-02", "OBS 观测点", "—")(tpl), {"E009"}))
    c.append(("分级写 P0", set_cell("| 编号 | 对应 |", "AUTO-03", "级别", "P0")(tpl), {"E010", "E014"}))
    c.append(("终态写可能", set_cell("| 编号 | 状态 |", "ST-02", "终态", "可能")(tpl), {"E018"}))
    c.append(("角色必填列留空", set_cell("| 角色 | 能做 |", "运营", "能做", "")(tpl), {"E017"}))
    c.append(("规则只写八个字", set_cell("| 编号 | 规则（可判真假的陈述） |", "REQ-02", "规则（可判真假的陈述）", "抵扣要正确")(tpl), {"E022"}))
    c.append(("口头来源不挂 OQ",
              tpl.replace("[SRC-VERBAL 产品张三 11-26 口述] → OQ-01", "[SRC-VERBAL 产品张三 11-26 口述]"),
              {"E011"}))
    c.append(("删掉状态 ST-04 的非法迁移",
              tpl.replace("| ST-04 | 使用过期券 | 拒绝 | 下单前置校验返回 `code=40902` | [SRC-REQ §4.2] |\n", ""),
              {"E004"}))
    c.append(("非目标写成空",
              tpl.replace("- 不支持多张券叠加使用\n- 不支持跨店铺券\n"
                          "- 不支持券转赠或退回账户外\n"
                          "- 不改造 promotion-service 的面额计算引擎，本需求只验消费侧", "（无）"),
              {"E020"}))
    c.append(("编号重复占号",
              tpl.replace("| REQ-03 | LOCKED 状态超过 30 分钟未支付，自动回到 UNUSED | [SRC-REQ §4.3] |",
                          "| REQ-03 | LOCKED 状态超过 30 分钟未支付，自动回到 UNUSED | [SRC-REQ §4.3] |\n"
                          "| REQ-03 | 同一编号被重复使用一次 | [SRC-REQ §4.3] |"),
              {"W004", "E014"}))
    c.append(("判 C 不写复核条件",
              set_cell("| 编号 | 对应 |", "AUTO-07", "复核条件", "—")(tpl), {"E021"}))
    c.append(("去掉基线行",
              tpl.replace("> **基线**：`main@7f3a9c2`（2026-11-25 拉取）\n", ""), {"W003"}))
    c.append(("段名改成功能描述", tpl.replace("## 6. 业务规则", "## 6. 功能描述"), {"W006"}))
    c.append(("可测项多于分级项",
              tpl.replace("| TST-07 | NFR-01 | 网关 P95 指标 | 压测脚本 50 QPS | 需独立压测环境与稳定流量 | 持续 5 分钟 |",
                          "| TST-07 | NFR-01 | 网关 P95 指标 | 压测脚本 50 QPS | 需独立压测环境与稳定流量 | 持续 5 分钟 |\n"
                          "| TST-08 | REQ-06 | `GET /coupons` 返回列表 | 造过期券，秒级 | 真实服务 | 无 |"),
              {"W005"}))
    c.append(("单表超过 40 行",
              tpl.replace("| 支付网关 | 支付成功回调 | 沙箱 | [SRC-DOC §5.2] |\n",
                          "| 支付网关 | 支付成功回调 | 沙箱 | [SRC-DOC §5.2] |\n"
                          + "".join(f"| extra-{n} | 用途 {n} | 真实服务 | [SRC-DOC §3] |\n" for n in range(1, 42))),
              {"W001"}))

    # 未决项 11 条（同步改索引，避免 E014 掩盖 W002）
    extra_oq = "".join(f"| OQ-{n:02d} | 验证用未决项 {n} | 产品 张三 | 无 | （待答复） | 未裁决 |\n"
                       for n in range(6, 12))
    t = tpl.replace("| OQ-05 | 运营账号同时有发放与作废权限", extra_oq + "| OQ-05 | 运营账号同时有发放与作废权限")
    c.append(("未决项超过 10 条", t.replace("5 个未决（1 已裁决）", "11 个未决（1 已裁决）"), {"W002"}))

    # 第 8 段声明为空
    seg8 = tpl[tpl.index("## 8. 非功能约束"):tpl.index("## 9. 可测性评估")]
    c.append(("非功能段声明为空",
              tpl.replace(seg8, "## 8. 非功能约束\n\n"
                                "已核对，无此类要素：本需求无性能与容量要求，依据 REQ 正文未提任何门限。\n\n"),
              {"W007", "E015"}))

    return c


def schema_cases() -> list[tuple[str, dict]]:
    """schema 自身写坏时必须报错退出码 2，不能静默放行。"""
    import copy
    base = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def m(fn):
        d = copy.deepcopy(base)
        fn(d)
        return d

    return [
        ("删掉第 7 段", m(lambda d: d["sections"].pop(6))),
        ("列角色写错", m(lambda d: d["sections"][5]["blocks"][0]["columns"][1].update(role="date"))),
        ("枚举缺 values", m(lambda d: d["sections"][2]["blocks"][0]["columns"][3].pop("values"))),
        ("引用未定义约束", m(lambda d: d["sections"][8].setdefault("constraints", []).append("no_such"))),
        ("表格缺 columns", m(lambda d: d["sections"][1]["blocks"][0].pop("columns"))),
        ("id_prefix 无 id 列", m(lambda d: d["sections"][1]["blocks"][0].update(id_prefix="XX"))),
        ("代码块缺 must_contain", m(lambda d: d["sections"][11]["blocks"][2].update(must_contain=[]))),
        ("段号重复", m(lambda d: d["sections"][3].update(no=3))),
    ]


# ---------------------------------------------------------------- 执行

def codes_of(mod, path: Path) -> set[str]:
    errors, warnings, _ = mod.check(path, mod.load_schema(SCHEMA))
    return {e["code"] for e in errors} | {w["code"] for w in warnings}


def main() -> int:
    verbose = "-v" in sys.argv
    mod = load_module()
    tpl = TEMPLATE.read_text(encoding="utf-8")
    failures = 0

    print("req_lint 自测 · 单点破坏")
    print(f"模板：{TEMPLATE.relative_to(SKILL)}")
    print()

    base_codes = codes_of(mod, TEMPLATE)
    if base_codes:
        print(f"  ✗ 基线失败：模板本身命中 {sorted(base_codes)}，后续用例无意义")
        return 1
    print("  基线与预期：模板 E0 W0 ✓")
    print()

    with tempfile.TemporaryDirectory() as td:
        for i, (label, text, expected) in enumerate(build_cases(tpl), 1):
            if text.strip() == tpl.strip():
                print(f"  ✗ {label}：变形未生效（用例本身失效，不是闸门的问题）")
                failures += 1
                continue
            p = Path(td) / f"case_{i}.md"
            p.write_text(text, encoding="utf-8")
            got = codes_of(mod, p)
            ok = got == expected
            mark = "✓" if ok else "✗"
            print(f"  {mark} {label}")
            if not ok or verbose:
                print(f"      期望 {sorted(expected)}  实际 {sorted(got)}")
            if not ok:
                failures += 1

        print()
        print("req_lint 自测 · 坏 schema 必须报错")
        for label, data in schema_cases():
            sp = Path(td) / "broken.json"
            sp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            try:
                mod.load_schema(sp)
            except mod.InputError as e:
                print(f"  ✓ {label} → 拒绝加载：{str(e)[:56]}")
                continue
            print(f"  ✗ {label} → 被静默接受，schema 校验有漏洞")
            failures += 1

        sp = Path(td) / "bad.json"
        sp.write_text("{oops", encoding="utf-8")
        try:
            mod.load_schema(sp)
            print("  ✗ JSON 语法坏 → 被静默接受")
            failures += 1
        except mod.InputError:
            print("  ✓ JSON 语法坏 → 拒绝加载")

    print()
    if failures:
        print(f"汇总：{failures} 项不符合预期")
        return 1
    print("汇总：全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
