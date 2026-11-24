"""台股每日資料（證交所＋櫃買中心官方網站，免費、不需要金鑰）。

產出（data/tw/）：
  taiex.csv                 加權指數日 K：Date,Open,High,Low,Close（2003-12 起）
  prices/{code}.csv         個股日 K：date,open,high,low,close,volume（股數，未還原權息；codes.txt 裡的代號，2015 起）
  margin.csv                上市融資：date,amount_k(融資金額仟元),lots(融資張),short(融券張),value_k(融資部位市值仟元),ratio(維持率%)
  days/YYYY-MM-DD.json      全市場每日檔（最近約 60 個交易日）：
                              ix.taiex=[收盤,漲跌點,漲跌%]
                              L/O（上市／上櫃）{代號:[名稱,收盤,漲跌,成交股數,成交金額元,最高,最低,開盤]}
                              mg{代號:融資餘額張}（上市＋上櫃）、pe{代號:[本益比,殖利率,淨值比]}
                              br 漲跌家數、amt 融資金額仟元、short 融資券
  latest.csv                自選股快照（code,date,close,pct_change,prev_date,prev_close,volume,foreign_net,trust_net,dealer_net）

維持率（我們自己的定義）＝Σ(上市每檔融資張數×1000×收盤)÷上市融資金額（含 ETF）。

用法：
  python scripts/fetch_tw.py auto                     排程用：14:30 前抓前一個平日，之後抓今天
  python scripts/fetch_tw.py daily [YYYY-MM-DD]      抓一天（預設今天，台北時間），更新上面所有檔
  python scripts/fetch_tw.py recent 60                補最近 60 個平日的 days/ 與 margin（已有的略過）
  python scripts/fetch_tw.py taiex 2003-12            重抓加權指數日 K（從指定年月到本月）
  python scripts/fetch_tw.py backfill 2015 OUTDIR     回補一整年的個股日 K 與融資（寫到 OUTDIR，之後用 merge 合併）
  python scripts/fetch_tw.py merge DIR...             把 backfill 的結果併進 data/tw/
"""
import csv, io, json, os, re, sys, time, datetime as dt, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "tw")
TZ = dt.timezone(dt.timedelta(hours=8))
GAP = 3.0           # 證交所同一 IP 請求太密會被暫時封鎖，每次間隔 3 秒
KEEP_DAYS = 60
_last = {"twse": 0.0, "tpex": 0.0}


def today():
    return dt.datetime.now(TZ).date()


def http(url, host, tries=3, timeout=60):
    err = None
    for k in range(tries):
        wait = GAP - (time.time() - _last[host])
        if wait > 0:
            time.sleep(wait)
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
            _last[host] = time.time()
            return b
        except Exception as e:  # noqa
            _last[host] = time.time()
            err = e
            time.sleep(10 * (k + 1))
    raise err


def jget(url, host):
    return json.loads(http(url, host).decode("utf-8"))


def num(x):
    s = re.sub(r"<[^>]+>", "", str(x)).replace(",", "").strip()
    if s in ("", "--", "---", "----", "X", "除權息", "除息", "除權"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def sign(x):
    s = str(x)
    return -1 if ("green" in s or s.strip().startswith("-")) else 1


def tables(j):
    out = list(j.get("tables") or [])
    if not out:     # 舊格式 fields1/data1...
        for k in j:
            if k.startswith("fields"):
                n = k[6:]
                out.append({"title": j.get("subtitle" + n) or j.get("title" + n) or "", "fields": j[k], "data": j.get("data" + n) or []})
    return [t for t in out if t.get("fields")]


def find(tabs, *keys):
    for t in tabs:
        if all(k in (t.get("title") or "") for k in keys):
            return t
    return None


def idx(fields, *names):
    for n in names:
        for i, f in enumerate(fields):
            if f.strip() == n:
                return i
    for n in names:
        for i, f in enumerate(fields):
            if n in f:
                return i
    return None


# ---------- 一天的資料 ----------
def twse_quotes(d):
    """上市：收盤行情、加權指數、漲跌家數。休市回傳 None。"""
    j = jget(f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={d:%Y%m%d}&type=ALLBUT0999&response=json", "twse")
    if j.get("stat") != "OK":
        return None
    T = tables(j)
    q = find(T, "每日收盤行情")
    if not q or not q.get("data"):
        return None
    F = q["fields"]
    ic, iname, ivol, ival, iop, ihi, ilo, icl, isg, ich = (idx(F, x) for x in
        ("證券代號", "證券名稱", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"))
    L = {}
    for r in q["data"]:
        c = str(r[ic]).strip()
        cl = num(r[icl])
        ch = num(r[ich])
        if ch is not None:
            ch = round(ch * sign(r[isg]), 4)
        L[c] = [str(r[iname]).strip(), cl, ch, num(r[ivol]), num(r[ival]), num(r[ihi]), num(r[ilo]), num(r[iop])]
    ix = None
    for t in T:
        if "價格指數" in (t.get("title") or "") and t.get("data"):
            for r in t["data"]:
                if str(r[0]).strip() == "發行量加權股價指數":
                    ix = [num(r[1]), round((num(r[3]) or 0) * sign(r[2]), 2), num(r[4])]
            if ix:
                break
    br = {}
    b = find(T, "漲跌證券數合計")
    if b:
        for r in b.get("data") or []:
            m = re.match(r"\s*([\d,]+)\s*(?:\(([\d,]+)\))?", str(r[2]))
            if m:
                br[str(r[0]).strip()] = [int(m.group(1).replace(",", "")), int((m.group(2) or "0").replace(",", ""))]
    return {"L": L, "taiex": ix, "br": br}


def tpex_quotes(d):
    j = jget(f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={d:%Y/%m/%d}&response=json", "tpex")
    O = {}
    for t in tables(j):
        if t.get("title") not in ("上櫃股票行情", "管理股票"):
            continue
        F = t["fields"]
        ic, iname, icl, ich, iop, ihi, ilo, ivol, ival = (idx(F, x) for x in
            ("代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "成交股數", "成交金額(元)"))
        for r in t.get("data") or []:
            c = str(r[ic]).strip()
            O[c] = [str(r[iname]).strip(), num(r[icl]), num(r[ich]), num(r[ivol]), num(r[ival]), num(r[ihi]), num(r[ilo]), num(r[iop])]
    return O


def twse_margin(d):
    """上市：融資金額（仟元）、融資張、融券張、每檔融資餘額張。"""
    j = jget(f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d:%Y%m%d}&selectType=ALL&response=json", "twse")
    if j.get("stat") != "OK":
        return None
    T = tables(j)
    res = {"mg": {}}
    s = find(T, "信用交易統計")
    if s:
        for r in s.get("data") or []:
            k = str(r[0])
            v = num(r[5])
            if "融資金額" in k:
                res["amt"] = v
            elif "融資" in k:
                res["lots"] = v
            elif "融券" in k:
                res["short"] = v
    t = find(T, "融資融券彙總")
    if t:
        F = t["fields"]
        # 欄位名稱重複（融資、融券各一組），融資的「今日餘額」是第一個
        i_bal = F.index("今日餘額")
        for r in t.get("data") or []:
            v = num(r[i_bal])
            if v:
                res["mg"][str(r[0]).strip()] = int(v)
    return res


def tpex_margin(d):
    j = jget(f"https://www.tpex.org.tw/www/zh-tw/margin/balance?date={d:%Y/%m/%d}&response=json", "tpex")
    out = {}
    for t in tables(j):
        F = t["fields"]
        ic, ib = idx(F, "代號"), idx(F, "資餘額")
        if ic is None or ib is None:
            continue
        for r in t.get("data") or []:
            v = num(r[ib])
            if v:
                out[str(r[ic]).strip()] = int(v)
    return out


def pe_all(d):
    pe = {}
    try:
        j = jget(f"https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={d:%Y%m%d}&selectType=ALL&response=json", "twse")
        for t in tables(j) or [{"fields": j.get("fields") or [], "data": j.get("data") or []}]:
            F = t["fields"]
            ic, ipe, idy, ipb = idx(F, "證券代號"), idx(F, "本益比"), idx(F, "殖利率(%)", "殖利率"), idx(F, "股價淨值比")
            if None in (ic, ipe):
                continue
            for r in t.get("data") or []:
                pe[str(r[ic]).strip()] = [num(r[ipe]), num(r[idy]) if idy is not None else None, num(r[ipb]) if ipb is not None else None]
    except Exception as e:  # noqa
        print("  ! 上市本益比", e)
    try:
        j = jget(f"https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate?date={d:%Y/%m/%d}&response=json", "tpex")
        for t in tables(j):
            F = t["fields"]
            ic, ipe, idy, ipb = idx(F, "股票代號", "代號"), idx(F, "本益比"), idx(F, "殖利率(%)", "殖利率"), idx(F, "股價淨值比")
            if None in (ic, ipe):
                continue
            for r in t.get("data") or []:
                pe[str(r[ic]).strip()] = [num(r[ipe]), num(r[idy]) if idy is not None else None, num(r[ipb]) if ipb is not None else None]
    except Exception as e:  # noqa
        print("  ! 上櫃本益比", e)
    return pe


def fetch_day(d, with_pe=True, with_otc_margin=True):
    q = twse_quotes(d)
    if not q:
        return None
    day = {"date": d.isoformat(), "ix": {"taiex": q["taiex"]}, "L": q["L"], "br": q["br"]}
    try:
        day["O"] = tpex_quotes(d)
    except Exception as e:  # noqa
        print("  ! 上櫃行情", d, e); day["O"] = {}
    try:
        m = twse_margin(d) or {}
        day["mg"] = m.get("mg", {})
        day["amt"], day["lots"], day["short"] = m.get("amt"), m.get("lots"), m.get("short")
    except Exception as e:  # noqa
        print("  ! 上市融資", d, e); day["mg"] = {}
    if with_otc_margin:
        try:
            for c, v in tpex_margin(d).items():
                day["mg"].setdefault(c, v)
        except Exception as e:  # noqa
            print("  ! 上櫃融資", d, e)
    if with_pe:
        day["pe"] = pe_all(d)
    return day


def margin_row(day):
    """上市融資維持率（只用上市個股的融資張數）。"""
    a = day.get("amt")
    if not a:
        return None
    v = 0.0
    for c, n in day.get("mg", {}).items():
        r = day["L"].get(c)
        if r and r[1]:
            v += n * r[1]          # 張×收盤×1000 ÷1000 → 仟元
    return [day["date"], int(a), int(day.get("lots") or 0), int(day.get("short") or 0), int(v), round(v / a * 100, 2) if v else ""]


# ---------- 檔案 ----------
def codes():
    p = os.path.join(ROOT, "codes.txt")
    return [l.strip() for l in open(p, encoding="utf-8") if l.strip() and not l.startswith("#")]


def read_csv(p):
    if not os.path.exists(p):
        return None, []
    rows = list(csv.reader(open(p, encoding="utf-8")))
    return (rows[0], rows[1:]) if rows else (None, [])


def upsert_csv(p, header, new_rows):
    """依第一欄（日期）合併、排序；同一天以新資料為準。"""
    h, old = read_csv(p)
    m = {r[0]: r for r in old}
    for r in new_rows:
        m[str(r[0])] = [str(x) if x is not None else "" for x in r]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for k in sorted(m):
            w.writerow(m[k])


def fmt(v):
    if v is None:
        return ""
    return str(int(v)) if float(v).is_integer() else str(round(v, 4))


def price_row(d, r):
    """r＝[名稱,收盤,漲跌,股數,金額,高,低,開]；沒成交（收盤空白）回傳 None。"""
    if not r or not r[1]:
        return None
    op, hi, lo = r[7] or r[1], r[5] or r[1], r[6] or r[1]
    return [d, fmt(op), fmt(hi), fmt(lo), fmt(r[1]), fmt(r[3] or 0)]


PRICE_H = ["date", "open", "high", "low", "close", "volume"]
MARGIN_H = ["date", "amount_k", "lots", "short", "value_k", "ratio"]


def write_day(day):
    d = day["date"]
    os.makedirs(os.path.join(ROOT, "days"), exist_ok=True)
    json.dump(day, open(os.path.join(ROOT, "days", d + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    keep = sorted(f for f in os.listdir(os.path.join(ROOT, "days")) if f.endswith(".json"))
    for f in keep[:-KEEP_DAYS]:
        os.remove(os.path.join(ROOT, "days", f))
    for c in codes():
        r = day["L"].get(c) or day["O"].get(c)
        pr = price_row(d, r)
        if pr:
            upsert_csv(os.path.join(ROOT, "prices", c + ".csv"), PRICE_H, [pr])
    mr = margin_row(day)
    if mr:
        upsert_csv(os.path.join(ROOT, "margin.csv"), MARGIN_H, [mr])


def write_latest():
    """自選股快照（格式同 dmsoul76823-bit/tw-stock-data data/latest.csv）。法人取 data/insti/latest.json（若有）。"""
    dd = os.path.join(ROOT, "days")
    ks = sorted(f for f in os.listdir(dd) if f.endswith(".json"))
    if len(ks) < 2:
        return
    a, b = (json.load(open(os.path.join(dd, k), encoding="utf-8")) for k in ks[-1:-3:-1])
    ins = {}
    pi = os.path.join(ROOT, "..", "insti", "latest.json")
    if os.path.exists(pi):
        j = json.load(open(pi, encoding="utf-8"))
        if j.get("date") == a["date"]:
            ins = j.get("rows", {})
    rows = []
    ta, tb = a["ix"].get("taiex"), b["ix"].get("taiex")
    if ta and tb and ta[0] and tb[0]:
        rows.append(["TAIEX", a["date"], fmt(ta[0]), round((ta[0] / tb[0] - 1) * 100, 2), b["date"], fmt(tb[0]), 0, "", "", ""])
    for c in codes():
        x = a["L"].get(c) or a["O"].get(c)
        y = b["L"].get(c) or b["O"].get(c)
        if not x or not x[1]:
            continue
        pc = y[1] if y and y[1] else None
        i = ins.get(c)
        rows.append([c, a["date"], fmt(x[1]), round((x[1] / pc - 1) * 100, 2) if pc else "", b["date"], fmt(pc) if pc else "", fmt(x[3] or 0),
                     *(fmt(v) if v is not None else "" for v in (i[1:4] if i else (None, None, None)))])
    with open(os.path.join(ROOT, "latest.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["code", "date", "close", "pct_change", "prev_date", "prev_close", "volume", "foreign_net", "trust_net", "dealer_net"])
        w.writerows(rows)


def taiex(start_ym):
    """加權指數日 K（MI_5MINS_HIST，一次一個月）。"""
    y, m = map(int, start_ym.split("-")[:2])
    end = today()
    rows = []
    while (y, m) <= (end.year, end.month):
        try:
            j = jget(f"https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={y:04d}{m:02d}01&response=json", "twse")
            for r in j.get("data") or []:
                p = str(r[0]).strip().split("/")
                d = dt.date(int(p[0]) + 1911, int(p[1]), int(p[2]))
                o, h, l, c = (num(x) for x in r[1:5])
                if c:
                    rows.append([d.isoformat(), fmt(o or c), fmt(h or c), fmt(l or c), fmt(c)])
        except Exception as e:  # noqa
            print("  ! 加權指數", y, m, e)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    upsert_csv(os.path.join(ROOT, "taiex.csv"), ["Date", "Open", "High", "Low", "Close"], rows)
    print("taiex", len(rows), "筆", rows[-1] if rows else "")


def weekdays(a, b):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def cmd_daily(d):
    day = fetch_day(d)
    if not day:
        print(d, "休市或尚未公布"); return False
    write_day(day)
    taiex(f"{d.year}-{d.month:02d}")
    write_latest()
    print(d, "OK 上市", len(day["L"]), "上櫃", len(day["O"]), "融資", len(day["mg"]), "本益比", len(day.get("pe", {})),
          "加權", day["ix"]["taiex"], "維持率", (margin_row(day) or [None] * 6)[5])
    return True


def cmd_recent(n):
    have = set(f[:10] for f in os.listdir(os.path.join(ROOT, "days"))) if os.path.isdir(os.path.join(ROOT, "days")) else set()
    ds = list(weekdays(today() - dt.timedelta(days=int(n * 1.5) + 10), today()))[-n:]
    for d in ds:
        if d.isoformat() in have:
            continue
        try:
            day = fetch_day(d)
        except Exception as e:  # noqa
            print(d, "失敗", e); continue
        if day:
            write_day(day)
            print(d, "OK")
    write_latest()


def cmd_backfill(year, outdir):
    """一整年：每天只抓上市行情、上櫃行情、上市融資（約 9 秒／天）。"""
    cs = set(codes())
    px = {c: [] for c in cs}
    mg = []
    end = min(dt.date(year, 12, 31), today())
    for d in weekdays(dt.date(year, 1, 1), end):
        try:
            day = fetch_day(d, with_pe=False, with_otc_margin=False)
        except Exception as e:  # noqa
            print(d, "失敗", e); continue
        if not day:
            continue
        for c in cs:
            pr = price_row(day["date"], day["L"].get(c) or day["O"].get(c))
            if pr:
                px[c].append(pr)
        mr = margin_row(day)
        if mr:
            mg.append(mr)
        print(d, "上市", len(day["L"]), "上櫃", len(day["O"]), "維持率", mr[5] if mr else None, flush=True)
    os.makedirs(os.path.join(outdir, "prices"), exist_ok=True)
    for c, rows in px.items():
        if rows:
            upsert_csv(os.path.join(outdir, "prices", c + ".csv"), PRICE_H, rows)
    upsert_csv(os.path.join(outdir, "margin.csv"), MARGIN_H, mg)
    print("backfill", year, "完成：個股", sum(1 for r in px.values() if r), "檔，融資", len(mg), "天")


def cmd_merge(dirs):
    for d in dirs:
        for root, _, files in os.walk(d):
            for f in files:
                if not f.endswith(".csv"):
                    continue
                src = os.path.join(root, f)
                h, rows = read_csv(src)
                rel = "prices/" + f if os.path.basename(root) == "prices" else f
                upsert_csv(os.path.join(ROOT, rel), h, rows)
    print("merge 完成")


if __name__ == "__main__":
    a = sys.argv[1:] or ["daily"]
    if a[0] == "auto":            # 排程用：14:30 前抓前一個平日（補齊晚上才公布的融資），之後抓今天
        now = dt.datetime.now(TZ)
        d = now.date() if now.hour * 60 + now.minute >= 14 * 60 + 30 else now.date() - dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
        print("目標日", d)
        cmd_daily(d)
    elif a[0] == "daily":
        cmd_daily(dt.date.fromisoformat(a[1]) if len(a) > 1 else today())
    elif a[0] == "recent":
        cmd_recent(int(a[1]) if len(a) > 1 else 60)
    elif a[0] == "taiex":
        taiex(a[1] if len(a) > 1 else "2003-12")
    elif a[0] == "backfill":
        cmd_backfill(int(a[1]), a[2])
    elif a[0] == "merge":
        cmd_merge(a[1:])
    else:
        print(__doc__)
