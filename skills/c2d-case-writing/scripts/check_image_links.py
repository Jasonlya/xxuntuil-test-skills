#!/usr/bin/env python3
"""图片链接可用性核验 —— 零第三方依赖（只用标准库 urllib）。

把"每条用例必须挂真实可访问的图片"从口号变成实测：逐条 GET，核对状态码与
Content-Type。预期失败的用例（404 回退、非图片资源）在用例里写
`expect_status: 404`，命中即判「预期失败」而非坏链。

    python3 check_image_links.py 测试用例_C2D图片_markmap.md \
        [--out 图片素材核验_20261126.md] [--timeout 15] [--json]

判定：
    OK        2xx 且 Content-Type 为 image/*
    EXPECTED  状态码与用例声明的 expect_status 一致（预期失败样本）
    FAIL      2xx 但非 image/*、或状态码与声明不符、或请求异常

退出码：存在 FAIL → 1；仅有 OK/EXPECTED → 0。
"""

import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL_RE = re.compile(r"https?://[^\s<>\"'）)\]]+")
TC_RE = re.compile(r"^###\s+(TC-[0-9A-Za-z]+-[0-9A-Za-z]+)")
EXPECT_RE = re.compile(r"expect_status\s*[:：]\s*(\d{3})")
UA = "Mozilla/5.0 (compatible; c2d-case-lint/0.1; image-link-check)"
MAX_BYTES = 5 * 1024 * 1024


def strip_tail(u):
    return u.rstrip(".,;、。，）)]}>\"'")


def collect(path):
    """返回 [(tc, url, expect_status_or_None)]，保持出现顺序，URL 去重。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    items = []
    seen = set()
    cur_tc = "-"
    buf = []

    def flush(tc, block_lines):
        block = "\n".join(block_lines)
        m = EXPECT_RE.search(block)
        expect = int(m.group(1)) if m else None
        for u in URL_RE.findall(block):
            u = strip_tail(u)
            if not u or u in seen:
                continue
            seen.add(u)
            items.append((tc, u, expect))

    for ln in lines:
        t = TC_RE.match(ln)
        if t:
            flush(cur_tc, buf)
            buf = []
            cur_tc = t.group(1)
            continue
        buf.append(ln)
    flush(cur_tc, buf)
    return items


def probe(url, timeout):
    req = Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"})
    t0 = time.time()
    try:
        with urlopen(req, timeout=timeout) as r:
            status = getattr(r, "status", None) or r.getcode()
            ct = (r.headers.get("Content-Type") or "").lower()
            data = r.read(MAX_BYTES)
            size = len(data)
            final = r.geturl()
            ms = int((time.time() - t0) * 1000)
            return {"status": status, "ctype": ct, "size": size,
                    "final": final, "ms": ms, "error": None}
    except HTTPError as e:
        ct = (e.headers.get("Content-Type") or "").lower() if e.headers else ""
        return {"status": e.code, "ctype": ct, "size": 0,
                "final": url, "ms": int((time.time() - t0) * 1000), "error": None}
    except (URLError, OSError) as e:
        return {"status": 0, "ctype": "", "size": 0, "final": url,
                "ms": int((time.time() - t0) * 1000), "error": str(getattr(e, "reason", e))}


def verdict(res, expect):
    st, ct = res["status"], res["ctype"]
    if expect is not None:
        if st == expect:
            return "EXPECTED", "状态码 %d 与用例声明一致（预期失败样本）" % st
        return "FAIL", "声明 expect_status=%d，实测 %d" % (expect, st)
    if res["error"]:
        return "FAIL", "请求异常：%s" % res["error"]
    if not (200 <= st < 300):
        return "FAIL", "非 2xx（%d）" % st
    if not ct.startswith("image/"):
        return "FAIL", "Content-Type 非图片：%s" % (ct or "(空)")
    return "OK", "图片直链正常"


def human(n):
    if n >= 1024 * 1024:
        return "%.1fMB" % (n / 1048576.0)
    if n >= 1024:
        return "%.1fKB" % (n / 1024.0)
    return "%dB" % n


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    out = None
    timeout = 15
    paths = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--out":
            out = args[i + 1]
            i += 2
            continue
        if a == "--timeout":
            timeout = float(args[i + 1])
            i += 2
            continue
        if not a.startswith("--"):
            paths.append(a)
        i += 1

    if not paths:
        print(__doc__)
        sys.exit(2)

    rows = []
    for p in paths:
        for tc, url, expect in collect(p):
            res = probe(url, timeout)
            v, why = verdict(res, expect)
            rows.append({"file": os.path.basename(p), "tc": tc, "url": url,
                         "expect": expect, "verdict": v, "why": why, **res})

    ok = sum(1 for r in rows if r["verdict"] == "OK")
    exp = sum(1 for r in rows if r["verdict"] == "EXPECTED")
    fail = [r for r in rows if r["verdict"] == "FAIL"]

    if as_json:
        print(json.dumps({"ok": ok, "expected": exp, "fail": len(fail), "rows": rows},
                         ensure_ascii=False, indent=2))
    else:
        print("=" * 78)
        print("链接核验：共 %d 条 → OK %d / 预期失败 %d / 失败 %d" % (len(rows), ok, exp, len(fail)))
        print("=" * 78)
        for r in rows:
            mark = {"OK": "✅", "EXPECTED": "🟡", "FAIL": "❌"}[r["verdict"]]
            print("%s %-9s %-4s %-26s %-9s %s"
                  % (mark, r["tc"], r["status"], (r["ctype"] or "-")[:26],
                     human(r["size"]), r["url"]))
            if r["verdict"] == "FAIL":
                print("        ↳ %s" % r["why"])

    if out:
        lines = ["# 图片素材核验 — %s" % time.strftime("%Y-%m-%d"), "",
                 "- 来源：%s" % "、".join(os.path.basename(p) for p in paths),
                 "- 合计：%d 条 → OK %d / 预期失败 %d / 失败 %d" % (len(rows), ok, exp, len(fail)),
                 "", "| 用例 | 状态码 | Content-Type | 体积 | 判定 | 链接 | 说明 |",
                 "|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append("| %s | %s | %s | %s | %s | %s | %s |"
                         % (r["tc"], r["status"], r["ctype"] or "-", human(r["size"]),
                            r["verdict"], r["url"], r["why"]))
        if any(r["final"] != r["url"] for r in rows):
            lines += ["", "> 注：部分链接发生重定向，表中链接为正则抽取的原始 URL。实测终址见 --json 输出的 `final` 字段。"]
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\n已写入：%s" % out)

    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
