#!/usr/bin/env python3
"""Probe candidate URLs once each with a browser UA; print status/size/type."""
import concurrent.futures as cf
import json
import sys

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
URLS = [
    # Japanese: reference / news / government / tech / literature / corporate
    "https://ja.wikipedia.org/wiki/%E6%97%A5%E6%9C%AC%E8%AA%9E",
    "https://ja.wikipedia.org/wiki/%E6%BC%A2%E5%AD%97",
    "https://www3.nhk.or.jp/news/html/20261111/k10014000000000.html",
    "https://www3.nhk.or.jp/news/",
    "https://www.asahi.com/",
    "https://www.asahi.com/articles/ASV1B0000V1B.html",
    "https://www.yomiuri.co.jp/",
    "https://www.sankei.com/",
    "https://www.nikkei.com/",
    "https://www.kantei.go.jp/",
    "https://www.soumu.go.jp/",
    "https://www.bunka.go.jp/",
    "https://www.ndl.go.jp/",
    "https://www.jma.go.jp/jma/index.html",
    "https://www.metro.tokyo.lg.jp/",
    "https://elaws.e-gov.go.jp/",
    "https://www.aozora.gr.jp/cards/000148/files/789_14547.html",
    "https://www.aozora.gr.jp/cards/000081/files/456_15050.html",
    "https://qiita.com/",
    "https://zenn.dev/",
    "https://note.com/",
    "https://developer.mozilla.org/ja/docs/Web/CSS/font-family",
    "https://developers.cyberagent.co.jp/blog/",
    "https://tech.smarthr.jp/",
    "https://blog.recruit.co.jp/",
    "https://www.itmedia.co.jp/",
    "https://www.gizmodo.jp/",
    "https://www.hatena.ne.jp/",
    "https://b.hatena.ne.jp/",
    "https://www.cookpad.com/",
    "https://jp.mercari.com/",
    "https://www.rakuten.co.jp/",
    "https://www.amazon.co.jp/",
    "https://www.yahoo.co.jp/",
    "https://www.zozo.com/",
    "https://www.jstage.jst.go.jp/",
    "https://www.u-tokyo.ac.jp/ja/index.html",
    "https://www.kyoto-u.ac.jp/ja",
    # Chinese
    "https://zh.wikipedia.org/wiki/%E6%B1%89%E5%AD%97",
    "https://www.gov.cn/",
    "https://www.people.com.cn/",
    "https://www.xinhuanet.com/",
    "https://www.zhihu.com/",
    "https://www.csdn.net/",
    "https://developer.mozilla.org/zh-CN/docs/Web/CSS/font-family",
    "https://www.douban.com/",
    # Korean
    "https://ko.wikipedia.org/wiki/%ED%95%9C%EA%B5%AD%EC%96%B4",
    "https://www.yna.co.kr/",
    "https://www.korea.kr/",
    "https://www.seoul.go.kr/",
    "https://news.naver.com/",
    "https://www.daum.net/",
    "https://brunch.co.kr/",
    "https://developer.mozilla.org/ko/docs/Web/CSS/font-family",
]

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.8,zh;q=0.6,ko;q=0.5"})


def probe(u):
    try:
        r = S.get(u, timeout=25, allow_redirects=True)
        n = len(r.content)
        title = ""
        ct = r.headers.get("content-type", "")
        if "html" in ct:
            import re
            m = re.search(rb"<title[^>]*>(.*?)</title>", r.content[:200000], re.S | re.I)
            if m:
                title = m.group(1).decode(r.encoding or "utf-8", "replace")[:70]
        return {"url": u, "status": r.status_code, "final": r.url, "bytes": n,
                "type": ct.split(";")[0], "title": title}
    except Exception as e:  # noqa: BLE001
        return {"url": u, "status": None, "error": repr(e)[:160]}


with cf.ThreadPoolExecutor(max_workers=8) as ex:
    rows = list(ex.map(probe, URLS))
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
