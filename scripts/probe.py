"""一次性：抓官方原始回應樣本存到 data/_samples/，給 Claude 檢查格式用（之後會刪）。"""
import urllib.request, time, os, sys
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "_samples")
os.makedirs(OUT, exist_ok=True)
J = [
 ("taifex_insti_MXF.csv", "https://www.taifex.com.tw/cht/3/futContractsDateDown?queryStartDate=2026/11/18&queryEndDate=2026/11/24&commodityId=MXF"),
 ("taifex_insti_TMF.csv", "https://www.taifex.com.tw/cht/3/futContractsDateDown?queryStartDate=2026/11/18&queryEndDate=2026/11/24&commodityId=TMF"),
 ("taifex_MTX.csv", "https://www.taifex.com.tw/cht/3/futDataDown?down_type=1&commodity_id=MTX&queryStartDate=2026/11/18&queryEndDate=2026/11/24"),
 ("taifex_TMF.csv", "https://www.taifex.com.tw/cht/3/futDataDown?down_type=1&commodity_id=TMF&queryStartDate=2026/11/18&queryEndDate=2026/11/24"),
 ("taifex_opt_daily_20261120.csv", "https://www.taifex.com.tw/cht/3/optDataDown?down_type=1&commodity_id=TXO&queryStartDate=2026/11/20&queryEndDate=2026/11/20"),
 ("taifex_large_hist.csv", "https://www.taifex.com.tw/cht/3/largeTraderFutDown?queryStartDate=2026/11/18&queryEndDate=2026/11/20"),
 ("taifex_tx_2015.csv", "https://www.taifex.com.tw/cht/3/futDataDown?down_type=1&commodity_id=TX&queryStartDate=2015/01/05&queryEndDate=2015/01/30"),
 ("taifex_pc_2015.csv", "https://www.taifex.com.tw/cht/3/pcRatioDown?queryStartDate=2015/01/01&queryEndDate=2015/01/30"),
]
for name, u in J:
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
        open(os.path.join(OUT, name), "wb").write(b)
        print("OK", name, len(b))
    except Exception as e:
        print("FAIL", name, e)
    time.sleep(3)
