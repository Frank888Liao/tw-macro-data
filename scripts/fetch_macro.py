"""每天抓總經原始數據，存成 data/macro/latest.json（只存原始數字，計算都在看板端做）。
  美國：FRED（聖路易聯準銀行）免費 CSV，不需要金鑰
  台灣：政府資料開放平臺 data.gov.tw
        6099 景氣指標及燈號（燈號分數、海關出口值、外銷訂單動向指數、M1B…）
        6100 臺灣採購經理人指數（PMI、NMI）
用法：python scripts/fetch_macro.py
某一項抓失敗只會記在 errors，不影響其他項目。"""
import csv, zipfile, io, json, os, time, datetime as dt, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (tw-market-data; macro fetch)"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "macro")

# (FRED 代號, 從哪天開始抓)
FRED = [
    # 利率與央行（日）
    ("DFEDTARU", "2019-01-01"), ("DFEDTARL", "2019-01-01"), ("DGS10", "2019-01-01"), ("DGS2", "2019-01-01"),
    ("T10Y2Y", "2019-01-01"), ("T10Y3M", "2019-01-01"),
    # 風險與情緒（日／週）
    ("VIXCLS", "2019-01-01"), ("BAMLH0A0HYM2", "2019-01-01"), ("BAA10Y", "2019-01-01"),
    ("DTWEXBGS", "2019-01-01"), ("DCOILWTICO", "2019-01-01"), ("NFCI", "2015-01-01"),
    # 匯率：新台幣、日圓兌美元（日）；實質利率（日）；Fed 資產負債表（週）
    ("DEXTAUS", "2019-01-01"), ("DEXJPUS", "2019-01-01"), ("DFII10", "2019-01-01"), ("WALCL", "2019-01-01"),
    # 通膨（月）
    ("CPIAUCSL", "2010-01-01"), ("CPILFESL", "2010-01-01"), ("PCEPILFE", "2010-01-01"), ("PPIFIS", "2010-01-01"),
    # 就業（月／週）
    ("PAYEMS", "2010-01-01"), ("UNRATE", "2010-01-01"), ("ICSA", "2015-01-01"),
    # 景氣（月／季）
    ("RSAFS", "2010-01-01"), ("A191RL1Q225SBEA", "2010-01-01"),
]
TW = ["6099", "6100"]


def http(url, timeout=60, tries=3):
    last = None
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:  # noqa
            last = e
            time.sleep(3 * (k + 1))
    raise last


def fred(sid, start):
    raw = http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}").decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw)))
    out = []
    for r in rows[1:]:
        if len(r) < 2 or r[1] in ("", "."):
            continue
        try:
            out.append([r[0], float(r[1])])
        except ValueError:
            pass
    if not out:
        raise ValueError("沒有資料：" + raw[:120])
    return out


def decode(b):
    for enc in ("utf-8-sig", "cp950", "big5"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def parse_csv(b):
    txt = decode(b).replace("\r\n", "\n").replace("\r", "\n")      # 舊式 \r 換行也能讀
    return [r for r in csv.reader(io.StringIO(txt, newline="")) if any(c.strip() for c in r)]


def zname(n):
    try:
        return n.encode("cp437").decode("cp950")                  # zip 內中文檔名
    except Exception:  # noqa
        return n


def from_zip(b):
    """zip 內所有 CSV 依第一欄（日期）合併成一張表。"""
    zf = zipfile.ZipFile(io.BytesIO(b))
    names = zf.namelist()
    tabs = []
    for n in names:
        if n.lower().endswith(".csv"):
            rows = parse_csv(zf.read(n))
            if len(rows) > 1:
                tabs.append((zname(n), rows))
    if not tabs:
        raise ValueError("zip 內沒有 CSV：" + ", ".join(zname(n) for n in names)[:200])
    header, data, order = [tabs[0][1][0][0]], {}, []
    for _, rows in tabs:
        cols = [c.strip() for c in rows[0]]
        idx = []
        for i, c in enumerate(cols[1:], 1):
            if c and c not in header:
                header.append(c)
                idx.append((i, c))
        for r in rows[1:]:
            k = r[0].strip()
            if k not in data:
                data[k] = {}
                order.append(k)
            for i, c in idx:
                if i < len(r):
                    data[k][c] = r[i]
    out = [[k] + [data[k].get(c, "") for c in header[1:]] for k in order]
    return header, out, [{"name": n, "header": rows[0][:30], "rows": len(rows) - 1} for n, rows in tabs]


def datagov(ds):
    meta = json.loads(http(f"https://data.gov.tw/api/v2/rest/dataset/{ds}").decode("utf-8"))
    res = meta.get("result", meta)
    dists = res.get("distribution") or []
    urls = [d.get("resourceDownloadUrl") for d in dists if str(d.get("resourceFormat", "")).upper() == "CSV"]
    urls += [d.get("resourceDownloadUrl") for d in dists if d.get("resourceDownloadUrl") not in urls]
    errs = []
    for u in [x for x in urls if x]:
        try:
            b = http(u)
            if b[:2] == b"PK":
                h, rows, files = from_zip(b)
                return {"title": res.get("title"), "url": u, "header": h, "rows": rows, "files": files}
            rows = parse_csv(b)
            if len(rows) > 1:
                return {"title": res.get("title"), "url": u, "header": rows[0], "rows": rows[1:]}
            errs.append(f"{u[-40:]}: 只有 {len(rows)} 列")
        except Exception as e:  # noqa
            errs.append(f"{u[-40:]}: {e}")
    raise ValueError("找不到可用的 CSV（" + " | ".join(errs)[:400] + "）")


def main():
    tz = dt.timezone(dt.timedelta(hours=8))
    res = {"updated": dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M"), "fred": {}, "tw": {}, "errors": {}}
    old = {}
    p = os.path.join(OUT, "latest.json")
    if os.path.exists(p):
        try:
            old = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa
            old = {}
    for sid, start in FRED:
        try:
            res["fred"][sid] = fred(sid, start)
            print(sid, "OK", res["fred"][sid][-1])
        except Exception as e:  # noqa
            res["errors"][sid] = str(e)[:200]
            if sid in old.get("fred", {}):          # 抓不到就沿用昨天的
                res["fred"][sid] = old["fred"][sid]
            print(sid, "失敗：", e)
        time.sleep(1)
    for ds in TW:
        try:
            res["tw"][ds] = datagov(ds)
            print("data.gov.tw", ds, "OK", len(res["tw"][ds]["rows"]), "列")
        except Exception as e:  # noqa
            res["errors"]["tw" + ds] = str(e)[:500]
            if ds in old.get("tw", {}):
                res["tw"][ds] = old["tw"][ds]
            print("data.gov.tw", ds, "失敗：", e)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("完成：成功", len(FRED) + len(TW) - len(res["errors"]), "項，失敗", len(res["errors"]), "項")


if __name__ == "__main__":
    main()
