#!/usr/bin/env python3
"""Computed weight audit. Run: .venv/bin/python measure/weight_usage_browser.py.

Requires Playwright and system Chromium; saves per-text-node runs, not HTML.
"""
import json
import os
import time
import base64
import hashlib
import subprocess
from collections import Counter
from pathlib import Path
from playwright.sync_api import sync_playwright
from weight_usage import STATS, OUT, DECOMP, ROLE_RE, CLASS_RE, page_weights
from fetch_corpus import robots_allowed, UA

WALK = r"""({decomp, role, cls}) => {
 const root = document.querySelector('main') || document.querySelector('article') || document.body;
 const runs = [];
 const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
 let node;
 while (node = walker.nextNode()) {
   const text = node.textContent;
   const chars = Array.from(text).filter(c => !/\s/u.test(c)).length;
   if (!chars) continue;
   const el = node.parentElement;
   const style = getComputedStyle(el);
   if (['hidden','collapse'].includes(style.visibility)) continue;
   let hidden = false, excluded = false;
   for (let a = el; a; a = a.parentElement) {
     const s = getComputedStyle(a);
     if (s.display === 'none' || s.contentVisibility === 'hidden' || Number(s.opacity) === 0) hidden = true;
     if (decomp.includes(a.localName) || new RegExp(role,'i').test(a.getAttribute('role') || '') || new RegExp(cls,'i').test(a.getAttribute('class') || '')) excluded = true;
   }
   if (hidden) continue;
   const range = document.createRange(); range.selectNodeContents(node);
   if (!Array.from(range.getClientRects()).some(r => r.width > 0 && r.height > 0)) continue;
   runs.push({text, chars, weight:style.fontWeight, font_family:style.fontFamily,
     tag:el.localName, id:el.id, estimator_scope:root.contains(node) && !excluded});
 }
 return {runs, title:document.title, fonts_status:document.fonts.status};
}"""


def aggregate(rows, key):
    counts = Counter()
    for row in rows:
        counts.update(row[key])
    total = sum(counts.values())
    return dict(chars_by_weight=dict(sorted(counts.items())), total_chars=total,
                share_pct={w: round(100*n/total, 4) for w,n in sorted(counts.items())})


def main():
    stats = [r for r in json.loads(STATS.read_text()) if r.get('unique_chars') and r.get('gf_estimate')]
    # Four successful pages per language, distinct genres first, then corpus order.
    preferred = {'ja':['wikipedia.org','asahi.com','kantei.go.jp','aozora.gr.jp'],
                 'zh':['wikipedia.org','gov.cn','people.com.cn','developer.mozilla.org'],
                 'ko':['wikipedia.org','yna.co.kr','korea.kr','brunch.co.kr']}
    pages, skipped = [], []
    with sync_playwright() as p:
        proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        cert = os.environ.get('CODEX_PROXY_CERT')
        args = []
        if cert:
            pubkey = subprocess.check_output(['openssl','x509','-in',cert,'-pubkey','-noout'])
            der = subprocess.check_output(['openssl','pkey','-pubin','-outform','DER'], input=pubkey)
            pin = base64.b64encode(hashlib.sha256(der).digest()).decode()
            args = ['--ignore-certificate-errors-spki-list=' + pin]
        browser = p.chromium.launch(args=args, executable_path='/usr/bin/chromium', headless=True,
                                   proxy={'server':proxy} if proxy else None)
        context = browser.new_context(viewport={'width':1440,'height':1000}, user_agent=UA)
        fixture = context.new_page()
        fixture.set_content('<style>main .medium {font:500 16px sans-serif} .hidden {display:none}</style><main>A<strong>BC</strong><span class=medium>DEF</span><span style=font-weight:300>GH</span><span class=hidden>HIDDEN</span><nav>MENU</nav></main>')
        check = fixture.evaluate(WALK, {'decomp':DECOMP,'role':ROLE_RE.pattern,'cls':CLASS_RE.pattern})
        actual = Counter()
        for run in check['runs']:
            if run['estimator_scope']: actual[run['weight']] += run['chars']
        assert actual == {'400':1, '700':2, '500':3, '300':2}, actual
        fixture.close()
        for lang in ('ja','zh','ko'):
            candidates = [r for r in stats if r['lang']==lang]
            firsts = [next(r for r in candidates if h in r['url']) for h in preferred[lang]]
            candidates = firsts + [r for r in candidates if r not in firsts]
            successes = 0
            for rec in candidates:
                if successes == 4: break
                url = rec['url']
                page = context.new_page()
                failures = []
                page.on('requestfailed', lambda req: failures.append({'url':req.url,'type':req.resource_type,'error':req.failure}))
                try:
                    if not robots_allowed(url)[0]: raise ValueError('robots disallowed')
                    response = page.goto(url, wait_until='load', timeout=60000)
                    if not response or response.status != 200: raise ValueError(f'HTTP {response.status if response else None}')
                    html = response.body()
                    page.wait_for_timeout(3000)
                    page.evaluate('() => Promise.race([document.fonts.ready, new Promise(r=>setTimeout(r,10000))])')
                    data = page.evaluate(WALK, {'decomp':DECOMP,'role':ROLE_RE.pattern,'cls':CLASS_RE.pattern})
                    counts = Counter(); scoped = Counter()
                    for run in data['runs']:
                        counts[run['weight']] += run['chars']
                        if run['estimator_scope']: scoped[run['weight']] += run['chars']
                    if sum(scoped.values()) < 100: raise ValueError('fewer than 100 scoped characters')
                    row = {k:rec.get(k) for k in ('url','lang','genre')}
                    row.update(data, final_url=page.url, computed=dict(counts), computed_scope=dict(scoped),
                               estimator={str(k):v for k,v in page_weights(html,url).items()}, failed_requests=failures)
                    pages.append(row); successes += 1
                    print(lang, url, dict(counts), flush=True)
                except Exception as e:
                    skipped.append({'url':url,'reason':str(e)})
                    print('SKIP',url,str(e)[:150],flush=True)
                finally:
                    page.close()
        version = browser.version
        browser.close()
    assert len(pages)>=10 and all(sum(r['lang']==l for r in pages)>=3 for l in ('ja','zh','ko'))
    for row in pages:
        assert sum(row['computed'].values()) == sum(r['chars'] for r in row['runs'])
    out = {'provenance':{'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'browser':version,
           'viewport':[1440,1000], 'wait':'load + 3s + fonts.ready (10s cap)',
           'selection':'4 successful pages per language; preferred distinct genres then corpus order',
           'characters':'Unicode code points excluding whitespace; one run per visible DOM text node',
           'visibility':'positive Range rectangle; ancestor display/content-visibility/opacity and computed visibility; entire document, not just viewport',
           'limitations':'No pseudo-element text, shadow DOM, iframes, occlusion or per-glyph clipping; computed CSS weight is not proof of physical font face or synthesis.'},
           'baseline_pct':{'400':94.66,'700':5.21,'other':0.13}, 'skipped':skipped,
           'overall':{key:aggregate(pages,key) for key in ('computed','computed_scope','estimator')},
           'by_lang':{l:{key:aggregate([r for r in pages if r['lang']==l],key) for key in ('computed','computed_scope','estimator')} for l in ('ja','zh','ko')},'pages':pages}
    target = OUT.with_name('weight_usage_browser.json')
    target.write_text(json.dumps(out,ensure_ascii=False,indent=1)+'\n')
    print(json.dumps(out['overall'],indent=2))

if __name__ == '__main__':
    main()
