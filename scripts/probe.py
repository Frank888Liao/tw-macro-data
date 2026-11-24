"""一次性：抓官方原始回應樣本存到 data/_samples/，給 Claude 檢查格式用（之後會刪）。"""
import urllib.request, time, os, sys
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "_samples")
os.makedirs(OUT, exist_ok=True)
J = []
for D in ("20261124", "20150105", "20200103"):
    J += [
     (f"twse_MI_INDEX_{D}.json", f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={D}&type=ALLBUT0999&response=json"),
     (f"twse_MI_MARGN_{D}.json", f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={D}&selectType=ALL&response=json"),
     (f"tpex_daily_{D}.json", f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={D[:4]}/{D[4:6]}/{D[6:]}&response=json"),
     (f"tpex_margin_{D}.json", f"https://www.tpex.org.tw/www/zh-tw/margin/balance?date={D[:4]}/{D[4:6]}/{D[6:]}&response=json"),
    ]
J += [("twse_MI_5MINS_HIST_200312.json", "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date=20031201&response=json"),
      ("twse_BWIBBU_20261124.json", "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date=20261124&selectType=ALL&response=json"),
      ("tpex_pe_20261124.json", "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate?date=2026/11/24&response=json"),
      ("mops_rev_sii_115_10.html", "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_10_0.html"),
      ("mops_rev_otc_104_1.html", "https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_104_1_0.html"),
      ("taifex_open_pc.csv", "https://openapi.taifex.com.tw/v1/PutCallRatio"),
      ("taifex_open_fut_insti.json", "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"),
      ("taifex_tx_20261124.csv", "https://www.taifex.com.tw/cht/3/futDataDown?down_type=1&commodity_id=TX&queryStartDate=2026/11/20&queryEndDate=2026/11/24"),
      ("taifex_insti_20261124.csv", "https://www.taifex.com.tw/cht/3/futContractsDateDown?queryStartDate=2026/11/20&queryEndDate=2026/11/24&commodityId=TXF"),
      ("taifex_pc_20261124.csv", "https://www.taifex.com.tw/cht/3/pcRatioDown?queryStartDate=2026/11/01&queryEndDate=2026/11/24"),
      ("taifex_large_20261124.csv", "https://www.taifex.com.tw/cht/3/largeTraderFutDown?queryStartDate=2026/11/20&queryEndDate=2026/11/24"),
      ("taifex_opt_insti_20261124.csv", "https://www.taifex.com.tw/cht/3/callsAndPutsDateDown?queryStartDate=2026/11/20&queryEndDate=2026/11/24&commodityId=TXO"),
      ("taifex_opt_daily_20261124.csv", "https://www.taifex.com.tw/cht/3/optDataDown?down_type=1&commodity_id=TXO&queryStartDate=2026/11/24&queryEndDate=2026/11/24"),
      ]
for name, u in J:
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
        open(os.path.join(OUT, name), "wb").write(b)
        print("OK", name, len(b))
    except Exception as e:
        print("FAIL", name, e)
    time.sleep(3)
