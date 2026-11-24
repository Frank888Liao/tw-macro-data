"""每天抓證交所資料，存成 data/insti/YYYY-MM-DD.json、latest.json，以及 twse_flows.csv（最新一天，voidful 格式）：
  T86     三大法人買賣超日報（上市全部個股，股數）
  BFI82U  三大法人買賣金額統計（上市，元→億）
  MI_INDEX 漲跌證券數合計（上市官方漲跌家數、漲停跌停）
用法：python scripts/fetch_insti.py            （抓今天，台北時間）
      python scripts/fetch_insti.py 2026-11-06 （抓指定日）
      python scripts/fetch_insti.py backfill 10 （往回補最近 10 個平日）"""
import json, os, sys, time, datetime as dt, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (tw-market-data; daily fetch)", "Accept": "application/json"}
URLS = ["https://www.twse.com.tw/rwd/zh/fund/T86?date={d}&selectType=ALLBUT0999&response=json",
        "https://www.twse.com.tw/fund/T86?response=json&date={d}&selectType=ALLBUT0999"]
EXTRA = {
    "bfi82u": ["https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={d}&response=json",
               "https://www.twse.com.tw/fund/BFI82U?response=json&dayDate={d}&type=day"],
    "breadth": ["https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={d}&type=MS&response=json",
                "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={d}&type=MS"],
}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "insti")


def num(x):
    try:
        return int(str(x).replace(",", "").strip())
    except ValueError:
        return None


def col(fields, *keys, exact=None):
    for i, f in enumerate(fields):
        if exact and f == exact:
            return i
    for i, f in enumerate(fields):
        if all(k in f for k in keys):
            return i
    return None


def fetch(day):
    last = None
    for u in URLS:
        try:
            req = urllib.request.Request(u.format(d=day.strftime("%Y%m%d")), headers=UA)
            j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
        except Exception as e:  # noqa
            last = str(e); continue
        if j.get("stat") != "OK" or not j.get("data"):
            last = j.get("stat"); continue
        F = j["fields"]
        ic, iname = col(F, "證券代號"), col(F, "證券名稱")
        i_f = col(F, "外陸資買賣超股數", "不含")
        i_fd = col(F, "外資自營商買賣超股數")
        i_t = col(F, "投信買賣超股數")
        i_d = col(F, "自營商買賣超股數", exact="自營商買賣超股數")
        i_all = col(F, "三大法人買賣超股數")
        rows = {}
        for r in j["data"]:
            c = str(r[ic]).strip()
            v = [num(r[k]) if k is not None else None for k in (i_f, i_t, i_d, i_all)]
            if i_fd is not None and v[0] is not None:
                v[0] += num(r[i_fd]) or 0          # 外資＝外陸資＋外資自營商
            rows[c] = [str(r[iname]).strip()] + v
        return {"date": day.isoformat(), "source": "TWSE T86", "unit": "股",
                "fields": ["name", "foreign", "trust", "dealer", "total"], "rows": rows}, None
    return None, last


def get_json(urls, day):
    for u in urls:
        try:
            req = urllib.request.Request(u.format(d=day.strftime("%Y%m%d")), headers=UA)
            j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
            if j.get("stat") == "OK":
                return j
        except Exception:  # noqa
            pass
        time.sleep(2)
    return None


def extras(day):
    """附加資料；失敗就略過，不影響 T86。"""
    out = {}
    j = get_json(EXTRA["bfi82u"], day)
    if j and j.get("data"):
        rows = []
        for r in j["data"]:
            v = [num(x) for x in r[1:4]]
            rows.append([str(r[0]).strip()] + [None if x is None else round(x / 1e8, 2) for x in v])
        out["totals"] = {"unit": "億元", "fields": ["類別", "買進", "賣出", "差額"], "rows": rows}
    time.sleep(3)
    j = get_json(EXTRA["breadth"], day)
    if j:
        tabs = j.get("tables") or []
        if not tabs:   # 舊格式：fields7/data7 之類
            tabs = [{"title": j.get(k.replace("fields", "subtitle"), ""), "fields": j[k], "data": j.get(k.replace("fields", "data"), [])}
                    for k in j if k.startswith("fields")]
        for t in tabs:
            title = str(t.get("title", "")) + " ".join(map(str, t.get("fields", [])))
            data = t.get("data") or []
            if "漲跌" in title and any("漲停" in str(r[0]) for r in data):
                out["breadth"] = {"fields": t.get("fields"), "data": data}
                break
    return out


def save(res):
    os.makedirs(OUT, exist_ok=True)
    for name in (res["date"] + ".json", "latest.json"):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    # 同一天的資料另存一份 voidful/tw-institutional-stocker 的格式（date,code,name,foreign_net,trust_net,dealer_net,market；股）
    with open(os.path.join(OUT, "twse_flows.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("date,code,name,foreign_net,trust_net,dealer_net,market\n")
        for c, v in sorted(res["rows"].items()):
            g = lambda x: "" if x is None else str(x)
            f.write(f"{res['date']},{c},{v[0].replace(',', ' ')},{g(v[1])},{g(v[2])},{g(v[3])},TWSE\n")


def main(argv):
    tz = dt.timezone(dt.timedelta(hours=8))
    today = dt.datetime.now(tz).date()
    if argv and argv[0] == "backfill":
        n, days, d = int(argv[1]) if len(argv) > 1 else 10, [], today
        while len(days) < n:
            if d.weekday() < 5:
                days.append(d)
            d -= dt.timedelta(days=1)
        days.reverse()
    else:
        days = [dt.date.fromisoformat(argv[0]) if argv else today]
    ok = 0
    for d in days:
        if d.weekday() >= 5:
            print(d, "週末，略過"); continue
        if os.path.exists(os.path.join(OUT, d.isoformat() + ".json")) and len(days) > 1:
            print(d, "已存在"); continue
        res, err = fetch(d)
        if res:
            time.sleep(3)
            res.update(extras(d))
            # backfill 時不要讓舊日期覆蓋 latest
            latest = os.path.join(OUT, "latest.json")
            if os.path.exists(latest) and json.load(open(latest, encoding="utf-8"))["date"] > res["date"]:
                os.makedirs(OUT, exist_ok=True)
                json.dump(res, open(os.path.join(OUT, res["date"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            else:
                save(res)
            ok += 1; print(d, "OK", len(res["rows"]), "檔")
        else:
            print(d, "沒有資料（休市或尚未公布）：", err)
        time.sleep(4)   # 證交所有限流，間隔幾秒
    print("完成", ok, "天")


if __name__ == "__main__":
    main(sys.argv[1:])
