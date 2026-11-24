"""一次性連線測試：官方來源在 GitHub Actions 是否抓得到。"""
import urllib.request, time, sys
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
D = sys.argv[1] if len(sys.argv) > 1 else "20261124"
M = D[:6] + "01"
U = {
 "twse_MI_INDEX": f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={D}&type=ALLBUT0999&response=json",
 "twse_FMTQIK": f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={M}&response=json",
 "twse_MI_5MINS_HIST": f"https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={M}&response=json",
 "twse_T86": f"https://www.twse.com.tw/rwd/zh/fund/T86?date={D}&selectType=ALLBUT0999&response=json",
 "twse_BFI82U": f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate={D}&type=day&response=json",
 "twse_MI_MARGN": f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={D}&selectType=ALL&response=json",
 "twse_BWIBBU": f"https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={D}&selectType=ALL&response=json",
 "twse_STOCK_DAY": f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={M}&stockNo=2330&response=json",
 "twse_open_STOCK_DAY_ALL": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
 "twse_open_rev": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
 "tpex_daily": f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={D[:4]}/{D[4:6]}/{D[6:]}&response=json",
 "tpex_open_close": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
 "tpex_open_rev": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
 "taifex_pcratio": "https://www.taifex.com.tw/cht/3/pcRatio",
 "taifex_open_pc": "https://openapi.taifex.com.tw/v1/PutCallRatio",
 "taifex_open_fut_insti": "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate",
 "taifex_daily_csv": f"https://www.taifex.com.tw/cht/3/futDataDown?down_type=1&commodity_id=TX&queryStartDate={D[:4]}/{D[4:6]}/{D[6:]}&queryEndDate={D[:4]}/{D[4:6]}/{D[6:]}",
 "mops_rev_html": f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{int(D[:4])-1911}_10_0.html",
}
for k, u in U.items():
    t = time.time()
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()
        head = b[:160].decode("utf-8", "replace").replace("\n", " ")
        print(f"PROBE {k} OK {len(b)}B {time.time()-t:.1f}s :: {head}")
    except Exception as e:
        print(f"PROBE {k} FAIL {type(e).__name__}: {str(e)[:120]}")
    time.sleep(2)
