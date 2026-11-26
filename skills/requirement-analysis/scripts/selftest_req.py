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


def move_col(marker: str, col: str):
    """把某列整列移到末尾（表头、分隔行、数据行同步移动），数据不错位。"""
    def apply(text: str) -> str:
        holder: dict[str, int] = {}

        def fn(kind, cs):
            if kind == "header" and col in cs:
                holder["k"] = cs.index(col)
            k = holder.get("k")
            if k is None or k >= len(cs):
                return cs
            return cs[:k] + cs[k + 1:] + [cs[k]]
        return table_block(text, marker, fn)
    return apply


def set_col(marker: str, col: str, value: str):
    """把某列所有数据行设成同一个值，用来测枚举覆盖类约束。"""
    def apply(text: str) -> str:
        holder: dict[str, int] = {}

        def fn(kind, cs):
            if kind == "header" and col in cs:
                holder["k"] = cs.index(col)
            k = holder.get("k")
            if k is None or kind in ("header", "sep"):
                return cs
            cs = list(cs)
            if k < len(cs):
                cs[k] = value
            return cs
        return table_block(text, marker, fn)
    return apply


def add_rows(marker: str, rows: list[str]):
    """在某张表末尾追加数据行。"""
    def apply(text: str) -> str:
        lines = text.splitlines()
        out, i = [], 0
        while i < len(lines):
            s = lines[i].strip()
            if s.startswith("|") and marker in s:
                j = i
                while j < len(lines) and lines[j].strip().startswith("|"):
                    out.append(lines[j])
                    j += 1
                out.extend(rows)
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

    FP = "| 编号 | 功能点 | 用户可感知的行为 |"
    TA = "| 编号 | 功能点 | 维度 | 验证意图 |"
    EVD = "| 编号 | 支撑对象 | 来源类型 | 位置 |"
    OQ = "| 编号 | 问题 | 影响对象 |"

    gap_block = tpl[tpl.index("**证据缺口**"):tpl.index("## 4 待澄清")]
    seg4 = tpl[tpl.index("## 4 待澄清"):tpl.index("## 5 移交索引")]
    fp05 = "| FP-05 | 第三方 Token 校验 | 第三方持 token 调用校验接口，得到有效 / 无效结论 | P1 | [SRC-DOC] 接入文档 §4 |"
    evd06 = ("| EVD-06 | OQ-01 | SRC-VERBAL | 11-25 需求评审录音 12:30 | "
             "「锁定先按账号做，IP 那块后面再说」 → OQ-01 | 弱 |")
    evd07 = ("| EVD-07 | FP-04、TA-11 | SRC-API | auth.yaml#/components/schemas/TokenPair | "
             "`access_token: {expires_in: 7200}` / `refresh_token: {expires_in: 604800}` | 强 |")

    # ---- 结构类
    c.append(("删掉第 5 段（移交索引）", tpl[: tpl.index("## 5 移交索引")], {"E001"}))
    c.append(("第 4 段整段留空", tpl.replace(seg4, "## 4 待澄清\n\n"),
              {"E002", "E013", "E015", "E014"}))
    c.append(("分析表删维度列", drop_col(TA, "维度")(tpl), {"E012"}))
    c.append(("证据表删原文摘录列", drop_col(EVD, "原文摘录")(tpl), {"E012"}))
    c.append(("证据表列改名", rename_col(EVD, "原文摘录", "说明")(tpl), {"E012", "W008"}))
    c.append(("证据表多一个备注列", add_col(EVD, "备注")(tpl), {"W008"}))
    c.append(("分析表把观测点列移到最后", move_col(TA, "观测点")(tpl), {"W009"}))
    c.append(("删掉证据缺口小节", tpl.replace(gap_block, ""), {"E013"}))
    c.append(("本期不做没有列表项",
              tpl.replace("- 不接第三方 OAuth / 企业微信扫码登录\n"
                          "- 不做多因子认证（MFA）\n"
                          "- 不做单点登录（SSO）\n", ""),
              {"E020"}))
    c.append(("待澄清表清空数据行", drop_rows(tpl, OQ), {"E019", "E015", "E014"}))
    c.append(("第 3 段声明为空", tpl.replace(gap_block, "已核对，无此类要素。\n\n"), {"W007"}))
    c.append(("段名改成测试设计", tpl.replace("## 2 需求用例分析", "## 2 测试设计"), {"W006"}))
    c.append(("去掉基线行",
              tpl.replace("> **基线**：`{仓库}` `{分支}` @ `{commit}`（{拉取日期}）\n", ""),
              {"W003"}))

    # ---- 编号与引用
    c.append(("功能点指向不存在编号", set_cell(TA, "TA-01", "功能点", "FP-99")(tpl), {"E015"}))
    c.append(("证据编号写成一位数", set_cell(EVD, "EVD-05", "编号", "EVD-5")(tpl), {"E016"}))
    c.append(("证据编号重复占号", tpl.replace(evd07, evd07 + "\n" + evd07), {"W004", "E014"}))
    c.append(("证据支撑对象写字母", set_cell(EVD, "EVD-06", "支撑对象", "看 OQ-01")(tpl), {"E016"}))

    # ---- 单元格内容
    c.append(("功能点来源写破折号", set_cell(FP, "FP-02", "来源", "—")(tpl), {"E003"}))
    c.append(("待澄清责任人写待确认", set_cell(OQ, "OQ-02", "向谁确认", "待确认")(tpl), {"E006"}))
    c.append(("验证意图写功能正常",
              set_cell(TA, "TA-02", "验证意图", "登录功能正常，不出现异常情况")(tpl), {"E007"}))
    c.append(("观测点写破折号", set_cell(TA, "TA-02", "观测点", "—")(tpl), {"E009"}))
    c.append(("证据位置只写文档", set_cell(EVD, "EVD-04", "位置", "文档")(tpl), {"E024"}))
    c.append(("摘录写详见第几章", set_cell(EVD, "EVD-05", "原文摘录", "详见 PRD 第 2 章")(tpl), {"E025"}))
    c.append(("关键取值留空", set_cell(TA, "TA-04", "关键取值", "")(tpl), {"E017"}))
    c.append(("维度写成可能", set_cell(TA, "TA-05", "维度", "可能")(tpl), {"E018"}))
    c.append(("验证意图只写四个字", set_cell(TA, "TA-08", "验证意图", "锁定生效")(tpl), {"E022"}))
    c.append(("自动化写 P0", set_cell(TA, "TA-03", "自动化", "P0")(tpl), {"E010", "E014"}))
    c.append(("判 C 不写复核条件", set_cell(TA, "TA-14", "复核条件", "—")(tpl), {"E021"}))
    c.append(("口头来源整行不挂待澄清",
              tpl.replace(evd06,
                          "| EVD-06 | FP-02 | SRC-VERBAL | 11-25 需求评审录音 12:30 | "
                          "「锁定先按账号做，IP 那块后面再说」 | 弱 |"),
              {"E011"}))

    # ---- 跨表约束
    fp06 = "| FP-06 | 找回密码 | 通过邮箱重置密码后可用新密码登录 | P2 | [SRC-REQ] PRD §5.1 |"
    c.append(("新增功能点无分析无证据", tpl.replace(fp05, fp06 + "\n" + fp05),
              {"E023", "E026", "E014"}))
    ta15 = ("| TA-15 | FP-06 | 正常流 | 邮箱链接 30 分钟内有效 → 可重置密码 | 有效期 30min | "
            "重置接口响应 code | A | — | [SRC-REQ] PRD §5.1 |")
    ta14 = [ln for ln in tpl.splitlines() if ln.startswith("| TA-14 |")][0]
    c.append(("新增功能点无证据但有分析",
              tpl.replace(fp05, fp06 + "\n" + fp05).replace(ta14, ta14 + "\n" + ta15),
              {"E026", "W011", "E014"}))
    c.append(("全部分析写成正常流", set_col(TA, "维度", "正常流")(tpl), {"W012"}))
    c.append(("强证据全部降级", set_col(EVD, "强度", "中")(tpl), {"W013"}))

    # ---- 移交索引
    c.append(("索引分级与实际不符",
              tpl.replace("自动化 A10/B3/C1", "自动化 A11/B2/C1"), {"E014"}))
    c.append(("索引功能点数写成中文",
              tpl.replace("5 个功能点", "五个功能点"), {"W010"}))

    # ---- 规模类
    extra_evd = "".join(
        f"| EVD-{n:02d} | FP-01 | SRC-REQ | PRD §9.{n} | 「补录证据第 {n} 条内容」 | 强 |\n"
        for n in range(8, 43))
    c.append(("证据表超过 40 行", tpl.replace(evd07, evd07 + "\n" + extra_evd.strip()),
              {"W001", "E014"}))

    extra_oq = "".join(
        f"| OQ-{n:02d} | 验证用待澄清第 {n} 条问题？ | FP-01 | 产品-张 | 按当前实现为准 | "
        f"对应分析项需重写期望值 | 未裁决 |\n"
        for n in range(4, 12))
    c.append(("待澄清超过 10 条",
              tpl.replace("| OQ-03 | refresh token 是否随刷新轮换？",
                          extra_oq + "| OQ-03 | refresh token 是否随刷新轮换？"),
              {"W002", "E014"}))

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
        ("删掉第 4 段", m(lambda d: d["sections"].pop(3))),
        ("段号重复", m(lambda d: d["sections"][3].update(no=3))),
        ("段 key 重复", m(lambda d: d["sections"][1].update(key="fp"))),
        ("列角色写错", m(lambda d: d["sections"][1]["blocks"][0]["columns"][2].update(role="date"))),
        ("枚举缺 values", m(lambda d: d["sections"][1]["blocks"][0]["columns"][2].pop("values"))),
        ("引用未定义约束", m(lambda d: d["sections"][0].setdefault("constraints", []).append("no_such"))),
        ("顶层声明未实现的约束",
         m(lambda d: d["constraints"].append({"name": "no_such_constraint", "on": ["fp"]}))),
        ("约束指向不存在的段 key",
         m(lambda d: d["constraints"].append({"name": "fp_has_analysis", "on": ["nope"]}))),
        ("表格缺 columns", m(lambda d: d["sections"][1]["blocks"][0].pop("columns"))),
        ("id_prefix 但无 id 列",
         m(lambda d: d["sections"][2]["blocks"][0]["columns"][0].update(role="text"))),
        ("代码块缺 must_contain", m(lambda d: d["sections"][4]["blocks"][0].update(must_contain=[]))),
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
