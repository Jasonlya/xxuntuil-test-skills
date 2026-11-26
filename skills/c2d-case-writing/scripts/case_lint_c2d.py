#!/usr/bin/env python3
"""C2D 图片用例红线闸门 —— 不调模型、零第三方依赖。

配套 SKILL.md 五条铁律与 references/case-format-c2d.md。把"每条用例必须挂真实
图片直链且特征能触发场景"从散文规则变成可机判的检查：弱模型不会自查，评审方
也没法逐条复核一张图对不对。

    python3 case_lint_c2d.py 测试用例_C2D图片_markmap.md [--allow-compact] [--json]

检查项（E = 错误，退出码 1 阻断定稿；W = 告警，需人工确认）：

    E1  缺导读四件套（功能与角色 / 环境与账号 / 术语表 / 图例）
    E2  TC 编号不符合 TC-{两位模块号}-{两位序号}
    E3  TC 编号重复
    E4  TC 编号模块号与所在 `## N.` 不符
    E5  缺「被测图片」段
    E6  「被测图片」段内无 http(s) 图片直链
    E7  「被测图片」段含占位符 / 本地路径 / data URI
    E8  缺「为何能测到」（说明该图特征如何触发规则）
    E9  缺「预期结果」段或为空
    E10 预期结果含不可判定表述（显示正常 / 无问题 …）
    E11 缺「规则」段或未引用 IMG-* 编号
    E12 一级模块编号 `## N.` 重复
    W1  用例标题未标注 [P0]/[P1]/[P2]
    W2  「被测图片」段缺「特征：」行
    W3  同一图片直链被 >3 条用例复用
    W4  预期涉及加载/异步/生效但无时限表述
    W5  P0 占比 >=35% 且用例数 >=6（冒烟集失去筛选意义）
    W6  用例只集中在 1 个模块（覆盖坍缩）
"""

import json
import re
import sys
from collections import Counter, OrderedDict

PLACEHOLDER_PATTERNS = [
    (re.compile(r"\{[^}\n]*\}"), "花括号占位符"),
    (re.compile(r"<[^>\n]*(url|URL|图片|img|image)[^>\n]*>"), "尖括号占位符"),
    (re.compile(r"占位图|示例图|某张图|某数据|xxx\.(png|jpg|jpeg|webp|svg)"), "占位表述"),
    (re.compile(r'(^|[\s(])(\.{1,2}/|/Users/|/home/|[A-Za-z]:\\)'), "本地路径"),
    (re.compile(r'(^|[\s(])(?![^\s]*://)\S+\.(png|jpe?g|gif|webp|svg)(\s|$)', re.M), "裸文件名（非直链）"),
    (re.compile(r"file://"), "file 协议"),
    (re.compile(r"data:image/"), "data URI 内联"),
]

UNDECIDABLE = [
    "显示正常", "正常显示", "显示正确", "显示无误", "功能正常", "无问题",
    "没有问题", "效果良好", "看起来", "基本正常", "大致正常", "符合预期即可",
]

TIME_HINT = re.compile(r"(≤|<=|不超过|以内|\d+\s*(ms|毫秒|s|秒|分钟)|超时|时限)")
ASYNC_HINT = re.compile(r"(加载|异步|生效|轮询|渲染完成)")

URL_RE = re.compile(r"https?://[^\s<>\"'）)\]]+")
TC_RE = re.compile(r"^###\s+(TC-[0-9A-Za-z]+-[0-9A-Za-z]+)")
TC_STRICT = re.compile(r"^TC-\d{2}-\d{2}$")
MODULE_RE = re.compile(r"^##\s+(\d+)\.\s")
PRIO_RE = re.compile(r"\[P([012])\]")


def strip_tail(url):
    return url.rstrip(".,;、。，）)]}>\"")


def section_text(lines, key):
    """取 `- <key>：` 起的整段（含缩进子项），返回 (行索引, 文本)。"""
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        if not s.startswith("-") and not s.startswith("*"):
            continue
        if key not in s:
            continue
        indent = len(ln) - len(ln.lstrip())
        out = [ln]
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                continue
            ind2 = len(nxt) - len(nxt.lstrip())
            if ind2 > indent:
                out.append(nxt)
            else:
                break
        return i, "\n".join(out)
    return -1, ""


def parse(text):
    lines = text.splitlines()
    modules = []          # (lineno, num)
    cases = []            # dict
    cur_module = None
    cur_case = None
    for idx, ln in enumerate(lines):
        m = MODULE_RE.match(ln)
        if m:
            cur_module = int(m.group(1))
            modules.append((idx + 1, cur_module))
            if cur_case:
                cur_case["body"] = lines[cur_case["start"]:idx]
                cases.append(cur_case)
                cur_case = None
            continue
        if ln.startswith("## "):
            if cur_case:
                cur_case["body"] = lines[cur_case["start"]:idx]
                cases.append(cur_case)
                cur_case = None
            cur_module = None
            continue
        t = TC_RE.match(ln)
        if t:
            if cur_case:
                cur_case["body"] = lines[cur_case["start"]:idx]
                cases.append(cur_case)
            cur_case = {
                "id": t.group(1),
                "lineno": idx + 1,
                "title": ln,
                "module": cur_module,
                "start": idx,
                "body": [],
            }
    if cur_case:
        cur_case["body"] = lines[cur_case["start"]:]
        cases.append(cur_case)
    return lines, modules, cases


def lint(path, allow_compact=False):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines, modules, cases = parse(text)
    errors, warns = [], []

    def err(line, code, msg):
        errors.append({"line": line, "code": code, "msg": msg})

    def warn(line, code, msg):
        warns.append({"line": line, "code": code, "msg": msg})

    # E12 模块编号重复
    seen_mod = {}
    for lineno, num in modules:
        if num in seen_mod:
            err(lineno, "E12", "一级模块编号 `## %d.` 重复（首次在 %d 行）" % (num, seen_mod[num]))
        else:
            seen_mod[num] = lineno

    # E1 导读四件套
    if not allow_compact:
        gi = next((i for i, ln in enumerate(lines) if ln.strip() in ("## 导读", "# 导读")), -1)
        if gi < 0:
            err(1, "E1", "缺「## 导读」段（四件套无处安放）")
        else:
            gi_end = next((i for i in range(gi + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
            block = "\n".join(lines[gi:gi_end])
            for key, name in [("功能", "功能与角色"), ("环境", "环境与账号"),
                              ("术语", "术语表"), ("图例", "图例")]:
                if key not in block:
                    err(gi + 1, "E1", "导读四件套缺「%s」" % name)

    if not cases:
        err(1, "E9", "未解析到任何 `### TC-*` 用例")
        return finish(path, errors, warns, modules, cases)

    # 逐条用例
    seen_tc = {}
    url_count = Counter()
    for c in cases:
        body = c["body"]
        tc = c["id"]
        ln = c["lineno"]

        # E2/E3/E4
        if not TC_STRICT.match(tc):
            err(ln, "E2", "TC 编号不合规：%s（应为 TC-两位模块号-两位序号）" % tc)
        if tc in seen_tc:
            err(ln, "E3", "TC 编号重复：%s（首次在 %d 行）" % (tc, seen_tc[tc]))
        else:
            seen_tc[tc] = ln
        m = re.match(r"TC-(\d+)-", tc)
        if m and c["module"] is not None and int(m.group(1)) != c["module"]:
            err(ln, "E4", "TC 编号模块号 %s 与所在 `## %d.` 不符" % (m.group(1), c["module"]))

        # E11 规则段
        _, rule_txt = section_text(body, "规则")
        if not rule_txt:
            err(ln, "E11", "缺「- 规则：」段")
        elif not re.search(r"IMG-[A-Z]+-\d+", rule_txt):
            err(ln, "E11", "规则段未引用 IMG-* 编号")

        # E5/E6/E7 被测图片段
        img_i, img_txt = section_text(body, "被测图片")
        if not img_txt:
            err(ln, "E5", "缺「- 被测图片：」段（本 skill 的一票否决项）")
        else:
            head = img_txt.splitlines()[0]
            urls = [strip_tail(u) for u in URL_RE.findall(img_txt)]
            urls = [u for u in urls if u]
            if not urls:
                err(ln, "E6", "被测图片段内无 http(s) 图片直链")
            else:
                c["url"] = urls[0]
                url_count[urls[0]] += 1
                if len(urls) > 1:
                    warn(ln, "W3", "被测图片段含 %d 个链接（一 case 一图）" % len(urls))
            for pat, desc in PLACEHOLDER_PATTERNS:
                if pat.search(img_txt):
                    err(ln, "E7", "被测图片段含%s" % desc)
            if "特征：" not in img_txt and "特征:" not in img_txt:
                warn(ln, "W2", "被测图片段缺「特征：」行（格式/尺寸/比例/体积）")
            if not allow_compact and "为何能测到" not in img_txt:
                err(ln, "E8", "缺「为何能测到」——未说明该图特征如何触发这条规则")

        # E9/E10/W4 预期结果
        _, exp_txt = section_text(body, "预期结果")
        if not exp_txt or len(exp_txt.strip()) < 12:
            err(ln, "E9", "缺「- 预期结果：」段或内容为空")
        else:
            for w in UNDECIDABLE:
                if w in exp_txt:
                    err(ln, "E10", "预期结果含不可判定表述「%s」" % w)
            if ASYNC_HINT.search(exp_txt) and not TIME_HINT.search(exp_txt):
                warn(ln, "W4", "预期涉及加载/异步但缺时限")

        # W1 优先级
        if not PRIO_RE.search(c["title"]):
            warn(ln, "W1", "标题未标注 [P0]/[P1]/[P2]")

    # W3 单图复用
    for url, n in url_count.items():
        if n > 3:
            first = next((c["lineno"] for c in cases if c.get("url") == url), 0)
            warn(first, "W3", "同一图片被 %d 条用例复用：%s（确认是否真能测出差异）" % (n, url))

    # W5 P0 占比
    prios = Counter()
    for c in cases:
        m = PRIO_RE.search(c["title"])
        if m:
            prios["P" + m.group(1)] += 1
    total = len(cases)
    if total >= 6 and prios["P0"] / float(total) >= 0.35:
        warn(0, "W5", "P0 占比 %.0f%%（%d/%d），冒烟集被稀释，逐条回炉自检"
             % (prios["P0"] * 100.0 / total, prios["P0"], total))

    # W6 覆盖坍缩
    mods = {c["module"] for c in cases if c["module"] is not None}
    if total >= 4 and len(mods) == 1:
        warn(0, "W6", "全部 %d 条用例集中在 1 个模块（覆盖可能坍缩）" % total)

    return finish(path, errors, warns, modules, cases, prios)


def finish(path, errors, warns, modules, cases, prios=None):
    res = {
        "file": path,
        "modules": len(modules),
        "cases": len(cases),
        "priorities": dict(prios or {}),
        "errors": errors,
        "warns": warns,
        "passed": len(errors) == 0,
    }
    return res


def main():
    args = [a for a in sys.argv[1:]]
    as_json = "--json" in args
    allow_compact = "--allow-compact" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print(__doc__)
        sys.exit(2)

    all_res = [lint(p, allow_compact) for p in paths]

    if as_json:
        print(json.dumps(all_res, ensure_ascii=False, indent=2))
    else:
        for r in all_res:
            print("=" * 68)
            print("文件：%s" % r["file"])
            print("模块 %d 个 / 用例 %d 条 / 优先级 %s"
                  % (r["modules"], r["cases"], r["priorities"] or "未标注"))
            print("-" * 68)
            if not r["errors"] and not r["warns"]:
                print("✅ 无问题")
            for e in r["errors"]:
                print("  ❌ %s  L%-4d %s" % (e["code"], e["line"], e["msg"]))
            for w in r["warns"]:
                print("  ⚠️  %s  L%-4d %s" % (w["code"], w["line"], w["msg"]))
            print("-" * 68)
            print("错误 %d / 告警 %d → %s"
                  % (len(r["errors"]), len(r["warns"]),
                     "阻断定稿" if r["errors"] else "放行（告警需人工确认）"))

    sys.exit(1 if any(r["errors"] for r in all_res) else 0)


if __name__ == "__main__":
    main()
