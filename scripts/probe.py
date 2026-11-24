"""一次性：抓官方原始回應樣本存到 data/_samples/，給 Claude 檢查格式用（之後會刪）。"""
import urllib.request, time, os, sys
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "_samples")
os.makedirs(OUT, exist_ok=True)
J = [
 ("tpex_insti_20261124.json", "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date=2026/11/24&response=json"),
 ("tpex_index_20261124.json", "https://www.tpex.org.tw/www/zh-tw/indexInfo/inx?date=2026/11/24&response=json"),
 ("tpex_open_index.json", "https://www.tpex.org.tw/openapi/v1/tpex_index"),
 ("twse_open_ann.json", "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"),
 ("tpex_open_ann.json", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"),
 ("twse_open_basic.json", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
 ("tpex_open_basic.json", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"),
 ("twse_open_rev.json", "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"),
 ("tpex_open_rev.json", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"),
]
for name, u in J:
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
        open(os.path.join(OUT, name), "wb").write(b)
        print("OK", name, len(b))
    except Exception as e:
        print("FAIL", name, e)
    time.sleep(3)
