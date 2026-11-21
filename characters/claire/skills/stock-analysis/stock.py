#!/usr/bin/env python3
"""Claire's stock technical analysis: fetch daily bars, compute indicators, score the setup, draw a chart.

usage:
  stock.py <code or name> [--weeks 4] [--out outputs] [--no-chart]

<code>: US ticker (AAPL, BRK-B), A share (600519, sh600519, 000001.SZ), HK (0700, 00700.HK, hk00700),
or a company name (贵州茅台, 腾讯, Tesla) which is looked up first.

Prints one JSON object (UTF-8) with the resolved symbol, the last bar, statistics over the analysis
window (default the last 4 weeks = 20 trading days), indicator values, rule-based signals with a
score in [-100, 100], key price levels, and the paths of the chart PNG and the full JSON it saved.

Standard library only (works with any Python 3.8+ on Windows / macOS / Linux). Data: Yahoo Finance
chart API, falling back to Tencent (qfq-adjusted) for A / HK / US. Not investment advice.
"""
import argparse, datetime as dt, json, math, os, re, struct, sys, urllib.parse, urllib.request, zlib

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'}


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- symbol resolution

def a_exchange(code):
    if code[0] in '69':
        return 'sh'
    if code[0] in '48':
        return 'bj'
    return 'sz'


def resolve(q):
    """-> dict(market=US|CN|HK, code, yahoo, tencent, name)"""
    s = q.strip()
    u = s.upper()
    m = re.fullmatch(r'(SH|SZ|BJ)?(\d{6})(\.(SS|SH|SZ|BJ))?', u)
    if m:
        code = m.group(2)
        ex = (m.group(1) or (m.group(4) or '')).lower().replace('ss', 'sh') or a_exchange(code)
        ysuf = {'sh': 'SS', 'sz': 'SZ', 'bj': 'BJ'}[ex]
        return dict(market='CN', code=code, yahoo=f'{code}.{ysuf}', tencent=f'{ex}{code}', name=None, currency='CNY')
    m = re.fullmatch(r'(HK)?0*(\d{1,5})(\.HK)?', u)
    if m and (m.group(1) or m.group(3) or len(s) <= 5):
        n = int(m.group(2))
        return dict(market='HK', code=f'{n:05d}', yahoo=f'{n:04d}.HK', tencent=f'hk{n:05d}', name=None, currency='HKD')
    m = re.fullmatch(r'(US)?([A-Z][A-Z0-9]{0,5})([.\-][A-Z])?', u)
    if m and not re.search(r'[^\x00-\x7f]', s):
        t = m.group(2) + (('-' + m.group(3)[1:]) if m.group(3) else '')
        return dict(market='US', code=t, yahoo=t, tencent='us' + t.replace('-', '.'), name=None, currency='USD')
    return search(s)


def search(q):
    """Company name -> symbol, via Eastmoney suggest (handles Chinese names for A / HK / US)."""
    url = ('https://searchapi.eastmoney.com/api/suggest/get?type=14&count=10&token=D43BF722C8E33BDC906FB84D85E326E8&input='
           + urllib.parse.quote(q))
    try:
        data = json.loads(http_get(url))['QuotationCodeTable']['Data'] or []
    except Exception as e:
        raise SystemExit(json.dumps({'error': f'找不到「{q}」：搜索失败 {e}'}, ensure_ascii=False))
    rank = {'AStock': 0, 'HK': 1, 'UsStock': 2}
    data = [d for d in data if d.get('Classify') in rank]
    if not data:
        raise SystemExit(json.dumps({'error': f'找不到「{q}」对应的美股 / A 股 / 港股，请直接给股票代码'}, ensure_ascii=False))
    exact = [d for d in data if d['Name'] == q]
    d = (exact or sorted(data, key=lambda d: rank[d['Classify']]))[0]
    r = resolve({'AStock': d['Code'], 'HK': 'HK' + d['Code'], 'UsStock': 'US' + d['Code']}[d['Classify']])
    r['name'] = d['Name']
    return r


# ---------------------------------------------------------------- data

def fetch_yahoo(sym, rng='1y'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval=1d&includePrePost=false'
    j = json.loads(http_get(url))['chart']
    if j.get('error') or not j.get('result'):
        raise RuntimeError(str(j.get('error')))
    r = j['result'][0]
    meta = r['meta']
    q = r['indicators']['quote'][0]
    tz = dt.timedelta(seconds=meta.get('gmtoffset', 0))
    bars = []
    for i, t in enumerate(r.get('timestamp') or []):
        o, h, l, c, v = (q[k][i] for k in ('open', 'high', 'low', 'close', 'volume'))
        if None in (o, h, l, c):
            continue
        d = (dt.datetime.fromtimestamp(t, dt.timezone.utc) + tz).date().isoformat()
        if bars and bars[-1]['date'] == d:
            bars.pop()
        bars.append(dict(date=d, open=o, high=h, low=l, close=c, volume=v or 0))
    # Yahoo's chart closes are split-adjusted, not dividend-adjusted; fine for a few-weeks technical view
    name = meta.get('longName') or meta.get('shortName')
    return bars, name, meta.get('currency'), 'Yahoo Finance'


def fetch_tencent(sym, n=260):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq'
    j = json.loads(http_get(url))
    d = j['data'][sym]
    rows = d.get('qfqday') or d.get('day') or []
    bars = [dict(date=r[0], open=float(r[1]), close=float(r[2]), high=float(r[3]), low=float(r[4]), volume=float(r[5]))
            for r in rows]
    name = None
    qt = (d.get('qt') or {}).get(sym)
    if isinstance(qt, list) and len(qt) > 1:
        name = qt[1]
    return bars, name, None, 'Tencent (前复权)'


def cn_name(sym):
    """Chinese short name for A / HK shares from Tencent's quote line (GBK)."""
    try:
        t = http_get(f'https://qt.gtimg.cn/q={sym}', 8).decode('gbk', 'replace')
        return t.split('~')[1] or None
    except Exception:
        return None


def with_deadline(fn, arg, sec):
    """Run fn(arg) in a thread; give up after `sec` seconds (a stalled socket must not block the fallback)."""
    import threading
    box = {}
    def run():
        try:
            box['ok'] = fn(arg)
        except Exception as e:
            box['err'] = e
    t = threading.Thread(target=run, daemon=True)
    t.start(); t.join(sec)
    if 'ok' in box:
        return box['ok']
    raise box.get('err') or TimeoutError(f'no response in {sec}s')


def load(r):
    errors = []
    srcs = [(fetch_yahoo, r['yahoo']), (fetch_tencent, r['tencent'])]
    if r['market'] in ('CN', 'HK'):
        srcs.reverse()          # Tencent is usually faster and qfq-adjusted for A / HK
    for fn, arg in srcs:
        try:
            bars, name, cur, src = with_deadline(fn, arg, 30)
            if len(bars) >= 30:
                return bars, name, cur, src
            errors.append(f'{src}: only {len(bars)} bars')
        except Exception as e:
            errors.append(f'{fn.__name__}: {e}')
    raise SystemExit(json.dumps({'error': '行情数据获取失败', 'symbol': r, 'details': errors}, ensure_ascii=False))


# ---------------------------------------------------------------- indicators

def sma(xs, n):
    out, s = [], 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def ema(xs, n):
    k, out, e = 2 / (n + 1), [], None
    for x in xs:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out


def rsi(cl, n):
    out, ag, al = [None], None, None
    for i in range(1, len(cl)):
        ch = cl[i] - cl[i - 1]
        g, l = max(ch, 0), max(-ch, 0)
        if i <= n:
            ag = (ag or 0) + g / n
            al = (al or 0) + l / n
            out.append(None if i < n else (100 if al == 0 else 100 - 100 / (1 + ag / al)))
        else:
            ag = (ag * (n - 1) + g) / n
            al = (al * (n - 1) + l) / n
            out.append(100 if al == 0 else 100 - 100 / (1 + ag / al))
    return out


def macd(cl):
    dif = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]
    dea = ema(dif, 9)
    return dif, dea, [2 * (a - b) for a, b in zip(dif, dea)]   # A-share convention: histogram = 2*(DIF-DEA)


def kdj(bars, n=9):
    k = d = 50.0
    K, D, J = [], [], []
    for i in range(len(bars)):
        w = bars[max(0, i - n + 1):i + 1]
        hi, lo = max(b['high'] for b in w), min(b['low'] for b in w)
        rsv = 50 if hi == lo else (bars[i]['close'] - lo) / (hi - lo) * 100
        k = 2 / 3 * k + rsv / 3
        d = 2 / 3 * d + k / 3
        K.append(k); D.append(d); J.append(3 * k - 2 * d)
    return K, D, J


def boll(cl, n=20, m=2):
    mid = sma(cl, n)
    up, lo = [], []
    for i in range(len(cl)):
        if mid[i] is None:
            up.append(None); lo.append(None); continue
        w = cl[i - n + 1:i + 1]
        sd = math.sqrt(sum((x - mid[i]) ** 2 for x in w) / n)
        up.append(mid[i] + m * sd); lo.append(mid[i] - m * sd)
    return up, mid, lo


def atr(bars, n=14):
    trs = []
    for i, b in enumerate(bars):
        pc = bars[i - 1]['close'] if i else b['close']
        trs.append(max(b['high'] - b['low'], abs(b['high'] - pc), abs(b['low'] - pc)))
    out, a = [], None
    for i, t in enumerate(trs):
        a = t if a is None else (a * (n - 1) + t) / n
        out.append(a)
    return out


def obv(bars):
    out, v = [], 0.0
    for i, b in enumerate(bars):
        if i:
            pc = bars[i - 1]['close']
            v += b['volume'] if b['close'] > pc else (-b['volume'] if b['close'] < pc else 0)
        out.append(v)
    return out


def linreg(ys):
    n = len(ys)
    xm, ym = (n - 1) / 2, sum(ys) / n
    sxx = sum((i - xm) ** 2 for i in range(n))
    sxy = sum((i - xm) * (y - ym) for i, y in enumerate(ys))
    slope = sxy / sxx
    ss_tot = sum((y - ym) ** 2 for y in ys) or 1e-12
    ss_res = sum((y - (ym + slope * (i - xm))) ** 2 for i, y in enumerate(ys))
    return slope, 1 - ss_res / ss_tot


def swings(bars, k=2):
    """Local highs / lows (k bars each side) -> ([(i, price)], [(i, price)])."""
    hs, ls = [], []
    for i in range(k, len(bars) - k):
        w = bars[i - k:i + k + 1]
        if bars[i]['high'] == max(b['high'] for b in w):
            hs.append((i, bars[i]['high']))
        if bars[i]['low'] == min(b['low'] for b in w):
            ls.append((i, bars[i]['low']))
    return hs, ls


def candle_patterns(bars):
    out = []
    if len(bars) < 3:
        return out
    a, b = bars[-2], bars[-1]
    body = abs(b['close'] - b['open'])
    rng = b['high'] - b['low'] or 1e-12
    upper = b['high'] - max(b['open'], b['close'])
    lower = min(b['open'], b['close']) - b['low']
    if body <= 0.1 * rng:
        out.append(('十字星', 0, '多空僵持，常出现在变盘前'))
    elif lower >= 2 * body and upper <= body:
        out.append(('锤子线 / 下影线长', 1, '下方有承接买盘'))
    elif upper >= 2 * body and lower <= body:
        out.append(('射击之星 / 上影线长', -1, '上方抛压较重'))
    if a['close'] < a['open'] and b['close'] > b['open'] and b['close'] >= a['open'] and b['open'] <= a['close']:
        out.append(('看涨吞没', 1, '阳线实体吞没前一根阴线'))
    if a['close'] > a['open'] and b['close'] < b['open'] and b['open'] >= a['close'] and b['close'] <= a['open']:
        out.append(('看跌吞没', -1, '阴线实体吞没前一根阳线'))
    last3 = bars[-3:]
    if all(x['close'] > x['open'] for x in last3) and last3[0]['close'] < last3[1]['close'] < last3[2]['close']:
        out.append(('红三兵', 1, '连续三根上涨阳线'))
    if all(x['close'] < x['open'] for x in last3) and last3[0]['close'] > last3[1]['close'] > last3[2]['close']:
        out.append(('三只乌鸦', -1, '连续三根下跌阴线'))
    return out


# ---------------------------------------------------------------- analysis

def r2(x, nd=2):
    return None if x is None else round(x, nd)


def analyze(bars, win):
    cl = [b['close'] for b in bars]
    vol = [b['volume'] for b in bars]
    n = len(bars)
    win = min(win, n - 1)
    ma = {p: sma(cl, p) for p in (5, 10, 20, 60)}
    dif, dea, hist = macd(cl)
    rsi6, rsi14 = rsi(cl, 6), rsi(cl, 14)
    K, D, J = kdj(bars)
    bu, bm, bl = boll(cl)
    at = atr(bars)
    ob = obv(bars)
    vma5, vma20 = sma(vol, 5), sma(vol, 20)
    last, prev = bars[-1], bars[-2]
    w = bars[-win:]
    base = bars[-win - 1]['close']
    wc = [b['close'] for b in w]
    slope, rsq = linreg(wc)
    peak, mdd = wc[0], 0.0
    for c in wc:
        peak = max(peak, c); mdd = min(mdd, c / peak - 1)
    rets = [cl[i] / cl[i - 1] - 1 for i in range(n - win, n)]
    vol_ann = math.sqrt(sum((x - sum(rets) / len(rets)) ** 2 for x in rets) / max(1, len(rets) - 1)) * math.sqrt(252)
    weeks = []
    for i in range(0, win, 5):
        seg = w[i:i + 5]
        p0 = bars[-win - 1 + i]['close']
        weeks.append(dict(start=seg[0]['date'], end=seg[-1]['date'], change_pct=r2((seg[-1]['close'] / p0 - 1) * 100),
                          high=r2(max(b['high'] for b in seg), 3), low=r2(min(b['low'] for b in seg), 3),
                          avg_volume=round(sum(b['volume'] for b in seg) / len(seg))))
    up_days = sum(1 for x in rets if x > 0)
    up_vol = sum(w[i]['volume'] for i in range(win) if rets[i] > 0)
    dn_vol = sum(w[i]['volume'] for i in range(win) if rets[i] < 0)

    # ---- signals: (name, weight, detail); weight > 0 bullish
    sig = []
    c = last['close']
    def add(name, wt, detail):
        sig.append(dict(signal=name, weight=wt, detail=detail))

    m5, m10, m20, m60 = (ma[p][-1] for p in (5, 10, 20, 60))
    if m5 and m10 and m20:
        if m5 > m10 > m20:
            add('均线多头排列', 15, f'MA5 {m5:.2f} > MA10 {m10:.2f} > MA20 {m20:.2f}')
        elif m5 < m10 < m20:
            add('均线空头排列', -15, f'MA5 {m5:.2f} < MA10 {m10:.2f} < MA20 {m20:.2f}')
        else:
            add('均线缠绕', 0, '短中期均线交织，方向不明')
    if m20:
        add('站上 MA20' if c > m20 else '跌破 MA20', 10 if c > m20 else -10, f'收盘 {c:.2f} vs MA20 {m20:.2f}（{(c / m20 - 1) * 100:+.1f}%）')
        m20_slope = (ma[20][-1] / ma[20][-6] - 1) * 100 if ma[20][-6] else 0
        add('MA20 上行' if m20_slope > 0.3 else ('MA20 下行' if m20_slope < -0.3 else 'MA20 走平'),
            5 if m20_slope > 0.3 else (-5 if m20_slope < -0.3 else 0), f'近 5 日 MA20 变化 {m20_slope:+.2f}%')
    if m60:
        add('位于 MA60 之上' if c > m60 else '位于 MA60 之下', 5 if c > m60 else -5, f'MA60 {m60:.2f}（中期趋势参考）')
    for i in range(1, 4):   # MA5/MA10 cross within the last 3 bars
        a0, b0, a1, b1 = ma[5][-i - 1], ma[10][-i - 1], ma[5][-i], ma[10][-i]
        if None not in (a0, b0, a1, b1):
            if a0 <= b0 and a1 > b1:
                add('MA5 上穿 MA10（金叉）', 8, f'{bars[-i]["date"]}'); break
            if a0 >= b0 and a1 < b1:
                add('MA5 下穿 MA10（死叉）', -8, f'{bars[-i]["date"]}'); break
    for i in range(1, 4):
        if dif[-i - 1] <= dea[-i - 1] and dif[-i] > dea[-i]:
            add('MACD 金叉' + ('（零轴上方）' if dif[-i] > 0 else '（零轴下方）'), 12 if dif[-i] > 0 else 8, bars[-i]['date']); break
        if dif[-i - 1] >= dea[-i - 1] and dif[-i] < dea[-i]:
            add('MACD 死叉' + ('（零轴下方）' if dif[-i] < 0 else '（零轴上方）'), -12 if dif[-i] < 0 else -8, bars[-i]['date']); break
    else:
        if hist[-1] > 0:
            add('MACD 红柱' + ('放大' if hist[-1] > hist[-2] else '缩短'), 5 if hist[-1] > hist[-2] else 1, f'DIF {dif[-1]:.3f} / DEA {dea[-1]:.3f}')
        else:
            add('MACD 绿柱' + ('放大' if hist[-1] < hist[-2] else '缩短'), -5 if hist[-1] < hist[-2] else -1, f'DIF {dif[-1]:.3f} / DEA {dea[-1]:.3f}')
    # divergence over the window: new price extreme without indicator confirmation
    hi_i = max(range(n - win, n), key=lambda i: cl[i])
    lo_i = min(range(n - win, n), key=lambda i: cl[i])
    if hi_i >= n - 3 and dif[-1] < max(dif[n - win:n - 3]):
        add('MACD 顶背离迹象', -8, '价格创窗口新高，DIF 未创新高')
    if lo_i >= n - 3 and dif[-1] > min(dif[n - win:n - 3]):
        add('MACD 底背离迹象', 8, '价格创窗口新低，DIF 未创新低')
    r14 = rsi14[-1]
    if r14 is not None:
        if r14 >= 70:
            add('RSI 超买', -8, f'RSI14 = {r14:.1f}')
        elif r14 <= 30:
            add('RSI 超卖', 8, f'RSI14 = {r14:.1f}（短线反弹概率上升，但不代表趋势反转）')
        elif r14 >= 55:
            add('RSI 偏强', 4, f'RSI14 = {r14:.1f}')
        elif r14 <= 45:
            add('RSI 偏弱', -4, f'RSI14 = {r14:.1f}')
        else:
            add('RSI 中性', 0, f'RSI14 = {r14:.1f}')
    if K[-2] <= D[-2] and K[-1] > D[-1]:
        add('KDJ 金叉' + ('（低位）' if K[-1] < 30 else ''), 6 if K[-1] < 30 else 3, f'K {K[-1]:.1f} / D {D[-1]:.1f} / J {J[-1]:.1f}')
    elif K[-2] >= D[-2] and K[-1] < D[-1]:
        add('KDJ 死叉' + ('（高位）' if K[-1] > 70 else ''), -6 if K[-1] > 70 else -3, f'K {K[-1]:.1f} / D {D[-1]:.1f} / J {J[-1]:.1f}')
    elif J[-1] > 100:
        add('KDJ 钝化超买', -3, f'J = {J[-1]:.1f}')
    elif J[-1] < 0:
        add('KDJ 钝化超卖', 3, f'J = {J[-1]:.1f}')
    if bu[-1]:
        pb = (c - bl[-1]) / (bu[-1] - bl[-1]) if bu[-1] != bl[-1] else 0.5
        width = (bu[-1] - bl[-1]) / bm[-1] * 100
        widths = [(bu[i] - bl[i]) / bm[i] * 100 for i in range(n - win, n) if bu[i]]
        if c > bu[-1]:
            add('突破布林上轨', 3, f'%B = {pb:.2f}；强势但短线偏离大')
        elif c < bl[-1]:
            add('跌破布林下轨', -3, f'%B = {pb:.2f}；弱势但短线超跌')
        if widths and width <= min(widths) * 1.05:
            add('布林带收口', 0, f'带宽 {width:.1f}% 为窗口最窄，可能临近变盘')
    if vma5[-1] and vma20[-1]:
        vr = vma5[-1] / vma20[-1]
        chg5 = cl[-1] / cl[-6] - 1
        if vr > 1.3 and chg5 > 0:
            add('放量上涨', 8, f'5 日均量 / 20 日均量 = {vr:.2f}，近 5 日 {chg5 * 100:+.1f}%')
        elif vr > 1.3 and chg5 < 0:
            add('放量下跌', -8, f'5 日均量 / 20 日均量 = {vr:.2f}，近 5 日 {chg5 * 100:+.1f}%')
        elif vr < 0.75 and chg5 < 0:
            add('缩量回调', 2, f'量比 {vr:.2f}，抛压不重')
        elif vr < 0.75 and chg5 > 0:
            add('缩量上涨', -2, f'量比 {vr:.2f}，上涨缺乏量能确认')
    if up_vol + dn_vol:
        uv = up_vol / (up_vol + dn_vol)
        if uv > 0.6:
            add('上涨日成交占优', 4, f'窗口内上涨日成交量占 {uv * 100:.0f}%')
        elif uv < 0.4:
            add('下跌日成交占优', -4, f'窗口内上涨日成交量仅占 {uv * 100:.0f}%')
    for name, wt, detail in candle_patterns(bars):
        add(f'K 线：{name}', 4 * wt, detail)

    score = max(-100, min(100, round(sum(s['weight'] for s in sig) * 100 / 70)))
    verdict = ('偏多' if score >= 25 else '中性偏多' if score >= 10 else '偏空' if score <= -25 else '中性偏空' if score <= -10 else '中性')

    # ---- levels
    a = at[-1]
    hs, ls = swings(bars[-max(win, 40):])
    res = sorted({round(p, 3) for _, p in hs if p > c})[:3]
    sup = sorted({round(p, 3) for _, p in ls if p < c}, reverse=True)[:3]
    yr = bars[-250:]
    hi_1y, lo_1y = max(b['high'] for b in yr), min(b['low'] for b in yr)
    for lvl in (m20, bm[-1] if bm[-1] else None, bl[-1] if bl[-1] else None, bu[-1] if bu[-1] else None, m60, hi_1y, lo_1y):
        if lvl and lvl < c and all(abs(lvl - s) / c > 0.01 for s in sup):
            sup.append(round(lvl, 3))
        if lvl and lvl > c and all(abs(lvl - r) / c > 0.01 for r in res):
            res.append(round(lvl, 3))
    sup = sorted(sup, reverse=True)[:3]
    res = sorted(res)[:3]
    s1 = sup[0] if sup else c - 2 * a
    stop = round(min(s1 - 0.5 * a, c - 1.5 * a), 3)
    target = round(res[0] if res else c + 2 * a, 3)
    rr = (target - c) / (c - stop) if c > stop else None

    def ser(xs, nd=3):
        return [r2(x, nd) for x in xs[-win:]]

    return dict(
        last=dict(date=last['date'], open=r2(last['open'], 3), high=r2(last['high'], 3), low=r2(last['low'], 3),
                  close=r2(c, 3), volume=round(last['volume']), change_pct=r2((c / prev['close'] - 1) * 100)),
        window=dict(trading_days=win, start=w[0]['date'], end=w[-1]['date'], start_close=r2(base, 3),
                    change_pct=r2((c / base - 1) * 100), high=r2(max(b['high'] for b in w), 3),
                    low=r2(min(b['low'] for b in w), 3), up_days=up_days, down_days=win - up_days,
                    trend_slope_pct_per_day=r2(slope / wc[0] * 100, 3), trend_r2=r2(rsq), max_drawdown_pct=r2(mdd * 100),
                    annualized_volatility_pct=r2(vol_ann * 100, 1), weeks=weeks,
                    high_52w=r2(hi_1y, 3), low_52w=r2(lo_1y, 3), history_days=len(yr)),
        indicators=dict(ma5=r2(m5, 3), ma10=r2(m10, 3), ma20=r2(m20, 3), ma60=r2(m60, 3),
                        macd=dict(dif=r2(dif[-1], 4), dea=r2(dea[-1], 4), hist=r2(hist[-1], 4)),
                        rsi6=r2(rsi6[-1], 1), rsi14=r2(r14, 1), kdj=dict(k=r2(K[-1], 1), d=r2(D[-1], 1), j=r2(J[-1], 1)),
                        boll=dict(upper=r2(bu[-1], 3), mid=r2(bm[-1], 3), lower=r2(bl[-1], 3)),
                        atr14=r2(a, 3), atr_pct=r2(a / c * 100), volume_ratio_5_20=r2(vma5[-1] / vma20[-1] if vma20[-1] else None),
                        obv_change_in_window=round(ob[-1] - ob[-win - 1])),
        signals=sig, score=score, verdict=verdict,
        levels=dict(support=sup, resistance=res, stop_loss=stop, target=target,
                    reward_risk=r2(rr), note='支撑/压力来自近期摆动高低点、MA20/MA60、布林带与 52 周高低点；止损 = 第一支撑下方 0.5×ATR 与 1.5×ATR 中较低者'),
        series=dict(date=[b['date'] for b in w], close=ser(cl), volume=[round(b['volume']) for b in w],
                    ma5=ser(ma[5]), ma20=ser(ma[20]), rsi14=ser(rsi14, 1), macd_hist=ser(hist, 4)),
        _plot=dict(bars=bars[-win:], ma5=ma[5][-win:], ma10=ma[10][-win:], ma20=ma[20][-win:],
                   bu=bu[-win:], bl=bl[-win:], rsi=rsi14[-win:], dif=dif[-win:], dea=dea[-win:], hist=hist[-win:],
                   sup=sup[:2], res=res[:2]),
    )


# ---------------------------------------------------------------- chart (pure-python PNG)

FONT = {  # 5x7 bitmap glyphs, rows top->bottom, 5 bits each
    '0': '0E 11 13 15 19 11 0E', '1': '04 0C 04 04 04 04 0E', '2': '0E 11 01 02 04 08 1F', '3': '1F 02 04 02 01 11 0E',
    '4': '02 06 0A 12 1F 02 02', '5': '1F 10 1E 01 01 11 0E', '6': '06 08 10 1E 11 11 0E', '7': '1F 01 02 04 08 08 08',
    '8': '0E 11 11 0E 11 11 0E', '9': '0E 11 11 0F 01 02 0C', '.': '00 00 00 00 00 0C 0C', '-': '00 00 00 0E 00 00 00',
    '+': '00 04 04 1F 04 04 00', '%': '18 19 02 04 08 13 03', ':': '00 0C 0C 00 0C 0C 00', '/': '01 01 02 04 08 10 10',
    '(': '02 04 08 08 08 04 02', ')': '08 04 02 02 02 04 08', ' ': '00 00 00 00 00 00 00', '=': '00 00 1F 00 1F 00 00',
    'A': '0E 11 11 1F 11 11 11', 'B': '1E 11 11 1E 11 11 1E', 'C': '0E 11 10 10 10 11 0E', 'D': '1C 12 11 11 11 12 1C',
    'E': '1F 10 10 1E 10 10 1F', 'F': '1F 10 10 1E 10 10 10', 'G': '0E 11 10 17 11 11 0F', 'H': '11 11 11 1F 11 11 11',
    'I': '0E 04 04 04 04 04 0E', 'J': '07 02 02 02 02 12 0C', 'K': '11 12 14 18 14 12 11', 'L': '10 10 10 10 10 10 1F',
    'M': '11 1B 15 15 11 11 11', 'N': '11 11 19 15 13 11 11', 'O': '0E 11 11 11 11 11 0E', 'P': '1E 11 11 1E 10 10 10',
    'Q': '0E 11 11 11 15 12 0D', 'R': '1E 11 11 1E 14 12 11', 'S': '0F 10 10 0E 01 01 1E', 'T': '1F 04 04 04 04 04 04',
    'U': '11 11 11 11 11 11 0E', 'V': '11 11 11 11 11 0A 04', 'W': '11 11 11 15 15 15 0A', 'X': '11 11 0A 04 0A 11 11',
    'Y': '11 11 0A 04 04 04 04', 'Z': '1F 01 02 04 08 10 1F',
}


class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    def blend(self, x, y, col, a=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            p = self.px
            if a >= 1:
                p[i:i + 3] = bytes(col)
            else:
                p[i] = round(p[i] + (col[0] - p[i]) * a)
                p[i + 1] = round(p[i + 1] + (col[1] - p[i + 1]) * a)
                p[i + 2] = round(p[i + 2] + (col[2] - p[i + 2]) * a)

    def rect(self, x0, y0, x1, y1, col, a=1.0):
        x0, x1 = sorted((int(round(x0)), int(round(x1))))
        y0, y1 = sorted((int(round(y0)), int(round(y1))))
        for y in range(max(0, y0), min(self.h, max(y1, y0 + 1))):
            for x in range(max(0, x0), min(self.w, max(x1, x0 + 1))):
                self.blend(x, y, col, a)

    def line(self, x0, y0, x1, y1, col, width=1.0, a=1.0, dash=0):
        """Anti-aliased thick line (distance-to-segment coverage)."""
        r = width / 2
        minx, maxx = int(min(x0, x1) - r - 1), int(max(x0, x1) + r + 2)
        miny, maxy = int(min(y0, y1) - r - 1), int(max(y0, y1) + r + 2)
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-9
        for y in range(max(0, miny), min(self.h, maxy)):
            for x in range(max(0, minx), min(self.w, maxx)):
                t = max(0, min(1, ((x + 0.5 - x0) * dx + (y + 0.5 - y0) * dy) / L2))
                if dash and int(t * math.sqrt(L2) / dash) % 2:
                    continue
                px, py = x0 + t * dx, y0 + t * dy
                d = math.hypot(x + 0.5 - px, y + 0.5 - py)
                cov = max(0.0, min(1.0, r + 0.5 - d))
                if cov > 0:
                    self.blend(x, y, col, a * cov)

    def polyline(self, pts, col, width=1.5, a=1.0):
        pts = [p for p in pts if p[1] is not None]
        for p, q in zip(pts, pts[1:]):
            self.line(p[0], p[1], q[0], q[1], col, width, a)

    def text(self, x, y, s, col, scale=2, anchor='l'):
        s = s.upper()
        tw = len(s) * 6 * scale - scale
        if anchor == 'r':
            x -= tw
        elif anchor == 'c':
            x -= tw // 2
        for ch in s:
            g = FONT.get(ch)
            if g:
                for ry, row in enumerate(g.split()):
                    bits = int(row, 16)
                    for rx in range(5):
                        if bits & (1 << (4 - rx)):
                            self.rect(x + rx * scale, y + ry * scale, x + (rx + 1) * scale, y + (ry + 1) * scale, col)
            x += 6 * scale

    def save(self, path):
        raw = b''.join(b'\x00' + bytes(self.px[y * self.w * 3:(y + 1) * self.w * 3]) for y in range(self.h))
        def chunk(t, d):
            return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        with open(path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0))
                    + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def fmt_price(p):
    return f'{p:.0f}' if p >= 1000 else (f'{p:.1f}' if p >= 100 else (f'{p:.2f}' if p >= 1 else f'{p:.3f}'))


def chart(plot, title, path, cn_colors):
    W, H = 1200, 860
    BG, GRID, AX, TXT = (255, 255, 255), (236, 238, 243), (200, 204, 214), (90, 96, 112)
    UPC, DNC = ((214, 48, 49), (0, 148, 102)) if cn_colors else ((0, 148, 102), (214, 48, 49))
    cv = Canvas(W, H, BG)
    L, R = 90, W - 30
    panes = [(70, 470), (490, 590), (610, 710), (730, 830)]   # price, volume, MACD, RSI
    bars = plot['bars']
    n = len(bars)
    step = (R - L) / n
    xc = lambda i: L + step * (i + 0.5)
    for y0, y1 in panes:
        cv.rect(L, y0, R, y0 + 1, AX); cv.rect(L, y1, R, y1 + 1, AX)
        cv.rect(L, y0, L + 1, y1, AX); cv.rect(R, y0, R + 1, y1, AX)
    cv.text(L, 22, title, (40, 44, 60), 3)

    # price pane
    vals = [b['high'] for b in bars] + [b['low'] for b in bars] + [v for k in ('ma5', 'ma10', 'ma20', 'bu', 'bl') for v in plot[k] if v]
    vals += plot['sup'] + plot['res']
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    y0, y1 = panes[0]
    py = lambda p: y1 - (p - lo) / (hi - lo) * (y1 - y0)
    for k in range(6):
        p = lo + (hi - lo) * k / 5
        cv.line(L, py(p), R, py(p), GRID, 1)
        cv.text(L - 8, py(p) - 7, fmt_price(p), TXT, 2, 'r')
    # bollinger band fill
    for i in range(n):
        if plot['bu'][i] and plot['bl'][i]:
            cv.rect(xc(i) - step / 2, py(plot['bu'][i]), xc(i) + step / 2, py(plot['bl'][i]), (120, 140, 230), 0.07)
    for lvl in plot['sup']:
        cv.line(L, py(lvl), R, py(lvl), (0, 148, 102) if not cn_colors else (60, 120, 220), 1.2, 0.8, dash=8)
        cv.text(R - 4, py(lvl) + 4, fmt_price(lvl), (60, 120, 220) if cn_colors else (0, 148, 102), 2, 'r')
    for lvl in plot['res']:
        cv.line(L, py(lvl), R, py(lvl), (230, 140, 40), 1.2, 0.8, dash=8)
        cv.text(R - 4, py(lvl) - 18, fmt_price(lvl), (230, 140, 40), 2, 'r')
    bw = max(2, step * 0.62)
    for i, b in enumerate(bars):
        up = b['close'] >= b['open']
        col = UPC if up else DNC
        cv.line(xc(i), py(b['high']), xc(i), py(b['low']), col, 1.6)
        top, bot = py(max(b['open'], b['close'])), py(min(b['open'], b['close']))
        cv.rect(xc(i) - bw / 2, top, xc(i) + bw / 2, max(bot, top + 2), col)
        if up and bot - top > 4 and bw > 8:
            cv.rect(xc(i) - bw / 2 + 2, top + 2, xc(i) + bw / 2 - 2, bot - 2, BG)   # hollow up candles
    for k, col in (('ma5', (245, 166, 35)), ('ma10', (155, 89, 182)), ('ma20', (52, 120, 246))):
        cv.polyline([(xc(i), py(v) if v else None) for i, v in enumerate(plot[k])], col, 2.2)
    lx = L + 10
    for label, col in (('MA5', (245, 166, 35)), ('MA10', (155, 89, 182)), ('MA20', (52, 120, 246)), ('BOLL', (120, 140, 230))):
        cv.rect(lx, y0 + 12, lx + 18, y0 + 16, col); cv.text(lx + 24, y0 + 8, label, TXT, 2); lx += 24 + len(label) * 12 + 22

    # volume
    y0, y1 = panes[1]
    vmax = max(b['volume'] for b in bars) or 1
    for i, b in enumerate(bars):
        cv.rect(xc(i) - bw / 2, y1 - b['volume'] / vmax * (y1 - y0 - 8), xc(i) + bw / 2, y1, UPC if b['close'] >= b['open'] else DNC, 0.75)
    cv.text(L + 8, y0 + 6, 'VOL', TXT, 2)
    unit, div = ('B', 1e9) if vmax >= 1e9 else (('M', 1e6) if vmax >= 1e6 else (('K', 1e3) if vmax >= 1e3 else ('', 1)))
    cv.text(L - 8, y0 + 2, f'{vmax / div:.1f}{unit}', TXT, 2, 'r')

    # MACD
    y0, y1 = panes[2]
    mv = max(1e-9, max(abs(v) for k in ('dif', 'dea', 'hist') for v in plot[k]))
    pm = lambda v: (y0 + y1) / 2 - v / mv * (y1 - y0) / 2 * 0.9
    cv.line(L, pm(0), R, pm(0), GRID, 1)
    for i, h in enumerate(plot['hist']):
        cv.rect(xc(i) - bw / 4, pm(0), xc(i) + bw / 4, pm(h), UPC if h >= 0 else DNC, 0.8)
    cv.polyline([(xc(i), pm(v)) for i, v in enumerate(plot['dif'])], (40, 44, 60), 1.8)
    cv.polyline([(xc(i), pm(v)) for i, v in enumerate(plot['dea'])], (245, 166, 35), 1.8)
    cv.text(L + 8, y0 + 6, 'MACD', TXT, 2)

    # RSI
    y0, y1 = panes[3]
    pr = lambda v: y1 - v / 100 * (y1 - y0)
    for lv in (30, 70):
        cv.line(L, pr(lv), R, pr(lv), (210, 214, 224), 1, dash=6)
        cv.text(L - 8, pr(lv) - 7, str(lv), TXT, 2, 'r')
    cv.polyline([(xc(i), pr(v) if v is not None else None) for i, v in enumerate(plot['rsi'])], (155, 89, 182), 2)
    cv.text(L + 8, y0 + 6, 'RSI14', TXT, 2)

    # dates
    every = max(1, n // 8)
    for i in range(0, n, every):
        cv.text(xc(i), y1 + 10, bars[i]['date'][5:], TXT, 2, 'c')
    cv.save(path)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('code')
    ap.add_argument('--weeks', type=int, default=4, help='analysis window in weeks (5 trading days each), default 4')
    ap.add_argument('--out', default='outputs')
    ap.add_argument('--no-chart', action='store_true')
    a = ap.parse_args()
    import socket, threading
    socket.setdefaulttimeout(15)
    def watchdog():   # a stalled DNS lookup / connection must not hang the agent
        print(json.dumps({'error': '行情数据获取超时（100 秒），请检查网络后重试'}, ensure_ascii=False), flush=True)
        os._exit(2)
    t = threading.Timer(100, watchdog); t.daemon = True; t.start()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    r = resolve(a.code)
    bars, name, cur, src = load(r)
    if r['market'] in ('CN', 'HK'):
        r['name'] = r['name'] or cn_name(r['tencent']) or name
    else:
        r['name'] = r['name'] or name
    r['currency'] = cur or r['currency']
    res = analyze(bars, a.weeks * 5)
    plot = res.pop('_plot')
    os.makedirs(a.out, exist_ok=True)
    stamp = res['last']['date']
    base = os.path.join(a.out, f'{r["code"]}-{stamp}')
    out = dict(symbol=dict(query=a.code, market=r['market'], code=r['code'], name=r['name'], currency=r['currency'],
                           yahoo=r['yahoo']),
               data_source=src, volume_unit='手(100股)' if (r['market'] == 'CN' and src.startswith('Tencent')) else '股',
               bars_loaded=len(bars), generated_at=dt.datetime.now().isoformat(timespec='seconds'),
               **res)
    if not a.no_chart:
        try:
            title = f'{r["code"]}  {stamp}  {res["window"]["trading_days"]}D  {res["window"]["change_pct"]:+.2f}%'
            chart(plot, title, base + '.png', r['market'] in ('CN', 'HK'))
            out['chart'] = base + '.png'
        except Exception as e:
            out['chart_error'] = str(e)
    with open(base + '.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    out['json'] = base + '.json'
    out.pop('series')   # in the saved JSON; keep stdout short
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
