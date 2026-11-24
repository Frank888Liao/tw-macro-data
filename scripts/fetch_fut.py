"""台指期籌碼與期現貨價差（期交所官方下載檔，免費）。格式和 optoptoptopt/taiwan-futures-daily 相同。

產出（data/fut/）：
  chips_daily.csv  日期,大台近月,大台近月結算,結算漲跌,大台近月未平倉,外資台指期淨未平倉,投信台指期淨未平倉,自營台指期淨未平倉,
                   外資買權淨未平倉,外資賣權淨未平倉,十大特定法人台指近月淨部位,散戶多空比_小台(%),散戶多空比_微台(%),
                   PC未平倉比(%),月選未平倉最多_買權履約價,月選未平倉最多_賣權履約價
  basis_daily.csv  日期,加權指數收盤,近月合約,近月收盤,收盤價差,收盤價差(%),近月13:30價,13:30對齊價差,13:30對齊價差(%),次月合約,次月收盤,次月收盤價差
                   （13:30 對齊價需要盤中逐筆資料，官方日檔沒有，留空）

算法：
  大台近月＝台指期 TX 一般時段、到期月份最近的月合約；結算漲跌＝同一合約和前一交易日結算價的差
  法人淨未平倉＝期交所「三大法人－區分各期貨契約」多空未平倉口數淨額
  十大特定法人＝大額交易人未沖銷部位（TX+MTX/4+TMF/20）近月、特定法人前十大買方－賣方
  散戶多空比＝−(三大法人淨未平倉合計)÷全市場未平倉（所有月份）×100（小台 MTX、微台 TMF 各算）
  P/C 未平倉比＝期交所臺指選擇權 Put/Call Ratio
  月選未平倉最多＝與大台近月同月份的臺指選擇權月合約，一般時段未平倉量最大的履約價

用法：python scripts/fetch_fut.py              最近 10 天（排程用）
      python scripts/fetch_fut.py 2024-01 2026-11  依月份回補
"""
import csv, io, os, sys, time, datetime as dt, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
BASE = "https://www.taifex.com.tw/cht/3/"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(ROOT, "fut")
TZ = dt.timezone(dt.timedelta(hours=8))
CH_H = ["日期", "大台近月", "大台近月結算", "結算漲跌", "大台近月未平倉", "外資台指期淨未平倉", "投信台指期淨未平倉", "自營台指期淨未平倉",
        "外資買權淨未平倉", "外資賣權淨未平倉", "十大特定法人台指近月淨部位", "散戶多空比_小台(%)", "散戶多空比_微台(%)",
        "PC未平倉比(%)", "月選未平倉最多_買權履約價", "月選未平倉最多_賣權履約價"]
BS_H = ["日期", "加權指數收盤", "近月合約", "近月收盤", "收盤價差", "收盤價差(%)", "近月13:30價", "13:30對齊價差", "13:30對齊價差(%)",
        "次月合約", "次月收盤", "次月收盤價差"]


def get_csv(path):
    for k in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(BASE + path, headers=UA), timeout=90).read()
            time.sleep(2)
            txt = b.decode("cp950", "replace") if not b.startswith(b"\xef\xbb\xbf") else b.decode("utf-8-sig")
            if txt.lstrip().startswith("<"):
                print("  ! 期交所回傳網頁而不是 CSV（查無資料或區間太長）：", path[:70])
                return []
            return [[c.strip() for c in r] for r in csv.reader(io.StringIO(txt)) if r]
        except Exception as e:  # noqa
            err = e
            time.sleep(10 * (k + 1))
    raise err


def num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def iso(s):
    y, m, d = s.strip().split("/")
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def q(a, b):
    return f"queryStartDate={a:%Y/%m/%d}&queryEndDate={b:%Y/%m/%d}"


def is_month(code):
    return len(code) == 6 and code.isdigit()


def fut_daily(cid, a, b):
    """{date: {month: (close, settle, oi), "_oi": 全部合約未平倉}}（一般時段；月合約另外列出）。"""
    rows = get_csv(f"futDataDown?down_type=1&commodity_id={cid}&{q(a, b)}")
    out = {}
    for r in rows[1:]:
        if len(r) < 18 or r[17] != "一般" or "/" in r[2]:       # 跳過價差委託
            continue
        d = out.setdefault(iso(r[0]), {"_oi": 0})
        d["_oi"] += num(r[11]) or 0                            # 全市場未平倉含週合約
        if is_month(r[2]):
            d[r[2]] = (num(r[6]), num(r[10]), num(r[11]))
    return out


def insti_fut(cid, a, b):
    """{date: {身份別: 多空未平倉口數淨額}}"""
    rows = get_csv(f"futContractsDateDown?{q(a, b)}&commodityId={cid}")
    out = {}
    for r in rows[1:]:
        if len(r) >= 15:
            out.setdefault(iso(r[0]), {})[r[2]] = num(r[13])
    return out


def insti_opt(a, b):
    """{date: {(CALL/PUT, 身份別): 未平倉口數淨額}}"""
    rows = get_csv(f"callsAndPutsDateDown?{q(a, b)}&commodityId=TXO")
    out = {}
    for r in rows[1:]:
        if len(r) >= 16:
            out.setdefault(iso(r[0]), {})[(r[2], r[3])] = num(r[14])
    return out


def pcr(a, b):
    rows = get_csv(f"pcRatioDown?{q(a, b)}")
    return {iso(r[0]): num(r[6]) for r in rows[1:] if len(r) >= 7}


def large(a, b):
    """{date: {month: 特定法人前十大買方－賣方}}（TX+MTX/4+TMF/20）"""
    rows = get_csv(f"largeTraderFutDown?{q(a, b)}")
    out = {}
    for r in rows[1:]:
        if len(r) >= 10 and r[1] == "TX" and r[4] == "1":
            out.setdefault(iso(r[0]), {})[r[3]] = (num(r[7]) or 0) - (num(r[8]) or 0)
    return out


def opt_maxoi(a, b):
    """{date: {month: {"買權": 履約價, "賣權": 履約價}}}（一般時段月合約，未平倉最大）"""
    rows = get_csv(f"optDataDown?down_type=1&commodity_id=TXO&{q(a, b)}")
    best = {}
    for r in rows[1:]:
        if len(r) < 18 or r[17] != "一般" or not is_month(r[2]):
            continue
        oi = num(r[11])
        if oi is None:
            continue
        k = (iso(r[0]), r[2], r[4])
        if oi > best.get(k, (-1, None))[0]:
            best[k] = (oi, num(r[3]))
    out = {}
    for (d, m, cp), (_, k) in best.items():
        out.setdefault(d, {}).setdefault(m, {})[cp] = k
    return out


def taiex_close():
    p = os.path.join(ROOT, "tw", "taiex.csv")
    if not os.path.exists(p):
        return {}
    return {r["Date"]: float(r["Close"]) for r in csv.DictReader(open(p, encoding="utf-8"))}


def fmt(v, nd=None):
    if v is None:
        return ""
    if nd is not None:
        return str(round(v, nd))
    return str(int(v)) if float(v).is_integer() else str(v)


def build(a, b, prev_settle=None):
    """a～b 的籌碼列與價差列。prev_settle：{(date, month): settle}，給第一天算結算漲跌。"""
    # 多抓前 10 天，第一天才算得出結算漲跌
    a0 = a - dt.timedelta(days=10)
    TX = fut_daily("TX", a0, a - dt.timedelta(days=1))      # 期交所下載一次最多一個月，前 10 天分開抓
    TX.update(fut_daily("TX", a, b))
    MTX, TMF = fut_daily("MTX", a, b), fut_daily("TMF", a, b)
    IF = {k: insti_fut(k, a, b) for k in ("TXF", "MXF", "TMF")}
    IO, PC, LG, OP = insti_opt(a, b), pcr(a, b), large(a, b), opt_maxoi(a, b)
    TI = taiex_close()
    chips, basis = [], []
    days = sorted(TX)
    for i, d in enumerate(days):
        if d < a.isoformat():
            continue
        ms = sorted(k for k in TX[d] if k != "_oi")
        if not ms:
            continue
        near, nxt = ms[0], (ms[1] if len(ms) > 1 else None)
        cl, st, oi = TX[d][near]
        chg = None
        for pd in reversed(days[:i]):
            if near in TX[pd] and TX[pd][near][1] is not None:
                chg = st - TX[pd][near][1] if st is not None else None
                break
        tf = IF["TXF"].get(d, {})

        def retail(px, ins):
            tot = (px.get(d) or {}).get("_oi") or 0
            net = sum(v or 0 for v in (ins.get(d) or {}).values())
            return round(-net / tot * 100, 2) if tot else None
        op = (OP.get(d) or {}).get(near) or {}
        io = IO.get(d) or {}
        chips.append([d, near, fmt(st), fmt(chg), fmt(oi), fmt(tf.get("外資及陸資")), fmt(tf.get("投信")), fmt(tf.get("自營商")),
                      fmt(io.get(("CALL", "外資及陸資"))), fmt(io.get(("PUT", "外資及陸資"))), fmt((LG.get(d) or {}).get(near)),
                      fmt(retail(MTX, IF["MXF"])), fmt(retail(TMF, IF["TMF"])), fmt(PC.get(d)),
                      fmt(op.get("買權")), fmt(op.get("賣權"))])
        ix = TI.get(d)
        if ix and cl:
            nc = TX[d][nxt][0] if nxt else None
            basis.append([d, fmt(ix), near, fmt(cl), fmt(cl - ix, 2), fmt((cl - ix) / ix * 100, 3), "", "", "",
                          nxt or "", fmt(nc), fmt(nc - ix, 2) if nc else ""])
    return chips, basis


def upsert(p, header, rows):
    old = {}
    if os.path.exists(p):
        r = list(csv.reader(open(p, encoding="utf-8-sig")))
        old = {x[0]: x for x in r[1:] if x}
    for x in rows:
        old[x[0]] = x
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for k in sorted(old):
            w.writerow(old[k])


def run(a, b):
    chips, basis = build(a, b)
    upsert(os.path.join(OUT, "chips_daily.csv"), CH_H, chips)
    upsert(os.path.join(OUT, "basis_daily.csv"), BS_H, basis)
    print(a, "～", b, "籌碼", len(chips), "天，價差", len(basis), "天", chips[-1] if chips else "")


if __name__ == "__main__":
    t = dt.datetime.now(TZ).date()
    if len(sys.argv) >= 3:
        y, m = map(int, sys.argv[1].split("-"))
        y2, m2 = map(int, sys.argv[2].split("-"))
        while (y, m) <= (y2, m2):
            a = dt.date(y, m, 1)
            b = min((dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)), t)
            try:
                run(a, b)
            except Exception as e:  # noqa
                print(a, "失敗", e)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    else:
        run(t - dt.timedelta(days=10), t)
