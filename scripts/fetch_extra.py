"""台股附加資料（官方免費來源）。依賴 fetch_tw.py 產生的 data/tw/days/ 與 fetch_insti.py 的 data/insti/latest.json。

產出（data/tw/）：
  ann.json              重大訊息（公開資訊觀測站，上市＋上櫃）：{發言日 YYYY-MM-DD: {代號: [主旨, ...]}}，保留 10 天
  revenue/{code}.csv    月營收：date,revenue_year,revenue_month,revenue（元；date＝次月 1 日，格式同 dmsoul76823-bit/tw-stock-data）
  industry.json         {代號: 產業別}（上市＋上櫃，月營收資料附帶）
  market.json           全市場（上市＋上櫃）快照，格式同 weo001/gushi data/market.json：
                          cols=[c,n,m,ind,close,chg,pct,vol(張),val(億),f,t,d(法人張),cap]、index、breadth、sectors、inst、taiex
  whole.json            大盤摘要，格式同 Andrew810523/taifex-data data/latest.json 的部分欄位（raw／stats）

用法：
  python scripts/fetch_extra.py daily                 重大訊息＋最新月營收＋全市場快照＋大盤摘要
  python scripts/fetch_extra.py revenue-backfill 2015-01 2026-10 [OUTDIR]  月營收回補（公開資訊觀測站，每月約 1～2 分鐘）
  python scripts/fetch_extra.py merge-rev DIR...      合併回補結果
"""
import csv, html, io, json, os, re, sys, time, datetime as dt, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
TW = os.path.join(ROOT, "tw")
TZ = dt.timezone(dt.timedelta(hours=8))
REV_H = ["date", "revenue_year", "revenue_month", "revenue"]


def http(u, tries=3, timeout=90):
    err = None
    for k in range(tries):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout).read()
            time.sleep(2)
            return b
        except Exception as e:  # noqa
            err = e
            time.sleep(10 * (k + 1))
    raise err


def jget(u):
    return json.loads(http(u).decode("utf-8-sig"))


def num(x):
    s = re.sub(r"<[^>]+>", "", str(x)).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def roc(s):
    """1151123 → 2026-11-23"""
    s = str(s).strip()
    if len(s) < 7:
        return None
    return f"{int(s[:-4]) + 1911:04d}-{s[-4:-2]}-{s[-2:]}"


def codes():
    return [l.strip() for l in open(os.path.join(TW, "codes.txt"), encoding="utf-8") if l.strip() and not l.startswith("#")]


def upsert(p, header, rows, key=lambda r: r[0]):
    old = {}
    if os.path.exists(p):
        r = list(csv.reader(open(p, encoding="utf-8")))
        old = {key(x): x for x in r[1:] if x}
    for x in rows:
        old[key(x)] = [str(v) for v in x]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for k in sorted(old):
            w.writerow(old[k])


# ---------- 重大訊息 ----------
def ann():
    p = os.path.join(TW, "ann.json")
    store = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    n = 0
    for u, kc, ks in (("https://openapi.twse.com.tw/v1/opendata/t187ap04_L", "公司代號", "主旨 "),
                      ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O", "SecuritiesCompanyCode", "主旨")):
        try:
            for x in jget(u):
                d = roc(x.get("發言日期"))
                c = str(x.get(kc, "")).strip()
                t = re.sub(r"\s+", " ", str(x.get(ks) or x.get("主旨") or x.get("主旨 ") or "")).strip()
                if not (d and c and t):
                    continue
                lst = store.setdefault(d, {}).setdefault(c, [])
                if t not in lst:
                    lst.append(t); n += 1
        except Exception as e:  # noqa
            print("! 重大訊息", u[-30:], e)
    for d in sorted(store)[:-10]:
        del store[d]
    json.dump(store, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("重大訊息 新增", n, "則，日期", sorted(store)[-3:])


# ---------- 月營收 ----------
def rev_row(ym_y, ym_m, k_thousand):
    y2, m2 = (ym_y + 1, 1) if ym_m == 12 else (ym_y, ym_m + 1)
    return [f"{y2:04d}-{m2:02d}-01", ym_y, ym_m, int(round(k_thousand * 1000))]


def revenue_latest():
    cs = set(codes())
    ind = {}
    pi = os.path.join(TW, "industry.json")
    if os.path.exists(pi):
        ind = json.load(open(pi, encoding="utf-8"))
    got = 0
    for u in ("https://openapi.twse.com.tw/v1/opendata/t187ap05_L", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"):
        try:
            for x in jget(u):
                c = str(x.get("公司代號", "")).strip()
                if x.get("產業別"):
                    ind[c] = x["產業別"].strip()
                ym = str(x.get("資料年月", "")).strip()
                v = num(x.get("營業收入-當月營收"))
                if c in cs and len(ym) >= 4 and v is not None:
                    y, m = int(ym[:-2]) + 1911, int(ym[-2:])
                    upsert(os.path.join(TW, "revenue", c + ".csv"), REV_H, [rev_row(y, m, v)])
                    got += 1
                    pm = num(x.get("營業收入-上月營收"))      # 順便補上月（避免某月沒抓到）
                    if pm is not None:
                        py, pmm = (y - 1, 12) if m == 1 else (y, m - 1)
                        upsert(os.path.join(TW, "revenue", c + ".csv"), REV_H, [rev_row(py, pmm, pm)])
        except Exception as e:  # noqa
            print("! 月營收", u[-30:], e)
    json.dump(ind, open(pi, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("月營收 更新", got, "檔；產業別", len(ind), "家")


def mops_month(mk, y, m):
    """公開資訊觀測站月營收彙總表（國內＋國外公司）→ {代號: 仟元}"""
    out = {}
    for kind in (0, 1):
        u = f"https://mopsov.twse.com.tw/nas/t21/{mk}/t21sc03_{y - 1911}_{m}_{kind}.html"
        try:
            b = http(u, timeout=120)
        except Exception as e:  # noqa
            print("  !", mk, y, m, kind, e); continue
        t = b.decode("cp950", "replace")
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)]
            if len(cells) >= 3 and re.match(r"^\d{4}[A-Z]?$", cells[0]):
                v = num(cells[2])
                if v is not None:
                    out[cells[0]] = v
    return out


def revenue_backfill(a, b, outdir=None):
    cs = set(codes())
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    rows = {c: [] for c in cs}
    while (y, m) <= (y2, m2):
        n = 0
        for mk in ("sii", "otc"):
            for c, v in mops_month(mk, y, m).items():
                if c in cs:
                    rows[c].append(rev_row(y, m, v)); n += 1
        print(f"{y}-{m:02d}", n, "檔", flush=True)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    base = os.path.join(outdir, "revenue") if outdir else os.path.join(TW, "revenue")
    for c, rs in rows.items():
        if rs:
            upsert(os.path.join(base, c + ".csv"), REV_H, rs)
    print("回補完成", sum(1 for r in rows.values() if r), "檔")


# ---------- 全市場快照 ----------
IND_MAP = {"電腦及週邊設備業": "電腦週邊", "紡織纖維": "紡織", "建材營造業": "建材營造", "油電燃氣業": "油電燃氣",
           "其他電子業": "其他電子", "電子零組件業": "電子零組件", "通信網路業": "通信網路", "電子通路業": "電子通路",
           "資訊服務業": "資訊服務", "生技醫療業": "生技醫療", "金融保險業": "金融保險", "貿易百貨業": "貿易百貨",
           "觀光餐旅": "觀光餐旅", "文化創意業": "文化創意", "居家生活": "居家生活", "數位雲端": "數位雲端", "運動休閒": "運動休閒",
           "綠能環保": "綠能環保", "農業科技": "農業科技", "電機機械": "電機機械", "電器電纜": "電器電纜"}


def ind_name(s):
    if not s:
        return "其他"
    s = s.strip()
    if s in IND_MAP:
        return IND_MAP[s]
    for suf in ("工業", "業"):
        if s.endswith(suf) and len(s) > len(suf) + 1:
            return s[:-len(suf)]
    return s


def tpex_insti(d):
    j = jget(f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={d.replace('-', '/')}&response=json")
    out = {}
    for t in j.get("tables") or []:
        F = t.get("fields") or []
        if len(F) < 23:
            continue
        for r in t.get("data") or []:
            v = [num(r[i]) for i in (10, 13, 22)]          # 外資及陸資合計、投信、自營商合計（股）
            out[str(r[0]).strip()] = [None if x is None else round(x / 1000) for x in v]
    return out


def otc_index():
    try:
        rows = jget("https://www.tpex.org.tw/openapi/v1/tpex_index")
        r = sorted(rows, key=lambda x: x["Date"])[-1]
        cl, ch = num(r["Close"]), num(r["Change"])
        return {"date": f"{r['Date'][:4]}-{r['Date'][4:6]}-{r['Date'][6:]}", "close": cl, "chg": ch,
                "pct": round(ch / (cl - ch) * 100, 2) if cl and ch is not None else None}
    except Exception as e:  # noqa
        print("! 櫃買指數", e)
        return None


def market():
    dd = os.path.join(TW, "days")
    ks = sorted(f for f in os.listdir(dd) if f.endswith(".json"))
    day = json.load(open(os.path.join(dd, ks[-1]), encoding="utf-8"))
    d = day["date"]
    ind = json.load(open(os.path.join(TW, "industry.json"), encoding="utf-8")) if os.path.exists(os.path.join(TW, "industry.json")) else {}
    ins_l = {}
    pi = os.path.join(ROOT, "insti", "latest.json")
    if os.path.exists(pi):
        j = json.load(open(pi, encoding="utf-8"))
        if j.get("date") == d:
            ins_l = {c: [None if x is None else round(x / 1000) for x in v[1:4]] for c, v in j["rows"].items()}
    try:
        ins_o = tpex_insti(d)
    except Exception as e:  # noqa
        print("! 上櫃法人", e); ins_o = {}
    cols = ["c", "n", "m", "ind", "close", "chg", "pct", "vol", "val", "f", "t", "d", "cap"]
    rows = []
    for m, book, ins in (("L", day["L"], ins_l), ("O", day["O"], ins_o)):
        for c, r in book.items():
            name, cl, ch, vol, val = r[0], r[1], r[2], r[3], r[4]
            if not cl or ch is None:
                continue
            if m == "O" and not re.match(r"^\d{4,6}[A-Z]?$", c):
                continue
            prev = cl - ch
            pct = round(ch / prev * 100, 2) if prev else None
            etf = c.startswith("00")
            if not etf and not re.match(r"^\d{4}$", c):            # 只留普通股與 ETF（排除特別股、債券等）
                continue
            f_, t_, d_ = ins.get(c) or (None, None, None)
            rows.append([c, name, m, "ETF" if etf else ind_name(ind.get(c)), cl, ch, pct,
                         round((vol or 0) / 1000), round((val or 0) / 1e8, 2), f_, t_, d_, None])
    st = [dict(zip(cols, r)) for r in rows if r[3] != "ETF" and r[6] is not None]
    sect = {}
    for x in st:
        sect.setdefault(x["ind"], []).append(x["pct"])
    sectors = sorted(({"ind": k, "pct": round(sum(v) / len(v), 2), "n": len(v)} for k, v in sect.items()), key=lambda s: -s["pct"])
    inst = {}
    for k in ("f", "t", "d"):
        inst[k] = round(sum((x[k] or 0) * x["close"] * 1000 for x in st if x["m"] == "O") / 1e8, 2)
    tx = day["ix"].get("taiex") or [None, None, None]
    index = [{"name": "加權指數", "close": tx[0], "chg": tx[1], "pct": tx[2]}]
    oi = otc_index()
    if oi and oi["date"] == d:
        index.append({"name": "櫃買指數", "close": oi["close"], "chg": oi["chg"], "pct": oi["pct"]})
    hist = []
    for k in ks[-16:]:
        x = json.load(open(os.path.join(dd, k), encoding="utf-8"))
        t = (x.get("ix") or {}).get("taiex")
        if t and t[0]:
            hist.append([x["date"], t[0], round((x.get("tv") or 0) / 1e8)])
    res = {"date": d, "updated": dt.datetime.now(TZ).isoformat(timespec="seconds"), "otc": True, "src": "twse+tpex",
           "histDays": len(hist), "instScope": "all", "index": index,
           "breadth": {"up": sum(x["pct"] > 0 for x in st), "down": sum(x["pct"] < 0 for x in st), "flat": sum(x["pct"] == 0 for x in st)},
           "inst": inst, "taiex": hist, "sectors": sectors, "cols": cols, "rows": rows}
    json.dump(res, open(os.path.join(TW, "market.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("全市場", d, "個股", len(rows), "類股", len(sectors), "漲跌", res["breadth"], "上櫃法人", len(ins_o))
    whole(day, ks, dd, d)


def whole(day, ks, dd, d):
    prev = json.load(open(os.path.join(dd, ks[-2]), encoding="utf-8")) if len(ks) > 1 else {}
    tot = {}
    pi = os.path.join(ROOT, "insti", "latest.json")
    if os.path.exists(pi):
        j = json.load(open(pi, encoding="utf-8"))
        if j.get("date") == d:
            for r in (j.get("totals") or {}).get("rows") or []:
                tot[r[0]] = r[3]
    fx = [v for k, v in tot.items() if k.startswith("外資")]
    rng = None
    pt = os.path.join(TW, "taiex.csv")
    if os.path.exists(pt):
        for r in csv.DictReader(open(pt, encoding="utf-8")):
            if r["Date"] == d:
                rng = round(float(r["High"]) - float(r["Low"]), 2)
    yi = lambda v: None if v is None else v * 1e8
    raw = {"日期": d, "加權指數成交量": round(day["tv"] / 1e8, 2) if day.get("tv") else None, "加權指數當日高低差": rng,
           "外資現貨買賣超": yi(sum(fx)) if fx else None, "自營(自行)現貨買賣超": yi(tot.get("自營商(自行買賣)")),
           "自營(避險)現貨買賣超": yi(tot.get("自營商(避險)")), "融資金額": day.get("amt"), "融券": day.get("short")}
    stats = {"融資金額變化量(億)": round((day["amt"] - prev["amt"]) / 1e5, 2) if day.get("amt") and prev.get("amt") else None,
             "融券單位變化量": (day["short"] - prev["short"]) if day.get("short") and prev.get("short") else None}
    json.dump({"updated_at": dt.datetime.now(TZ).isoformat(timespec="seconds"), "raw": raw, "stats": stats},
              open(os.path.join(TW, "whole.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("大盤摘要", raw)


if __name__ == "__main__":
    a = sys.argv[1:] or ["daily"]
    if a[0] == "daily":
        for fn in (ann, revenue_latest, market):
            try:
                fn()
            except Exception as e:  # noqa
                print("!", fn.__name__, "失敗：", e)
    elif a[0] == "revenue-backfill":
        revenue_backfill(a[1], a[2], a[3] if len(a) > 3 else None)
    elif a[0] == "merge-rev":            # 把各年份回補結果併進 data/tw/revenue
        for d in a[1:]:
            for root, _, files in os.walk(d):
                for f in files:
                    if f.endswith(".csv"):
                        r = list(csv.reader(open(os.path.join(root, f), encoding="utf-8")))
                        upsert(os.path.join(TW, "revenue", f), REV_H, r[1:])
        print("merge-rev 完成")
    else:
        print(__doc__)
