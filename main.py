# -*- coding: utf-8 -*-
"""
A股每日量化选股与买卖时机分析系统 (V2.0 实战严选版) - 主运行入口
一键全自动执行：
1. 抓取大盘核心指数与全市场 TOP 400 高流动性股票行情
2. 第一层防诱多排雷：仅限沪深主板权限、剔除假阳真阴瀑布线、剔除长上影避雷针、过滤死水与死亡换手
3. 第二层多因子连续打分 + ATR(14) 真实波幅动态测算买卖点与盈亏金额
4. 生成独立可视化 HTML 交互报告同步至桌面并自动打开
"""
import os
import sys
import webbrowser
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))

from data_fetcher import AShareDataFetcher
from strategy_engine import ShortTermTrendStrategy
from report_generator import ReportGenerator
from mobile_server import start_mobile_server_background, print_terminal_qr, get_local_ip
import config

def run_pipeline(scan_count=config.SCAN_POOL_COUNT, top_k=config.TOP_RECOMMEND_COUNT, auto_open=True):
    print("=" * 68)
    print("   📊 A股每日短线雷达 V2.0 (主板严选 · 防诱多 · ATR动态风控)")
    print(f"   账户本金: ¥{config.TOTAL_CAPITAL:,.0f} 元 | 严选沪深主板 | 股价区间: ¥{config.MIN_STOCK_PRICE} ~ ¥{config.MAX_STOCK_PRICE}")
    print(f"   运行时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print("=" * 68)

    fetcher = AShareDataFetcher()
    strategy = ShortTermTrendStrategy()
    generator = ReportGenerator()

    # 1. 获取大盘核心指数
    print("\n[1/4] 正在抓取大盘指数环境...")
    indices = fetcher.get_market_indices()
    for idx in indices:
        sign = "+" if idx['change_pct'] >= 0 else ""
        print(f"  • {idx['name']:<5} {idx['point']:>8.2f} ({sign}{idx['change_pct']:.2f}%)  成交额: {idx['amount_yi']}亿元")

    # 2. 抓取高流动性活跃候选股票池并执行第一层防诱多排雷
    print(f"\n[2/4] 正在扫描全市场成交额前 {scan_count} 名活跃股并执行【五重防诱多排雷】...")
    raw_pool, stats = fetcher.get_active_stocks_pool(count=scan_count)
    print(f"  ✓ 全市场扫描: {stats['total_scanned']} 只")
    print(f"  ✓ 权限与股价过滤: 剔除创业板/科创板 {stats['filtered_board']} 只 | 剔除高价/仙股 {stats['filtered_price']} 只")
    print(f"  ✓ 诱多图形排雷: 剔除高开低走假红盘/长上影避雷针 {stats['filtered_trap_kline']} 只 | 剔除异常换手 {stats['filtered_turnover']} 只")
    print(f"  ✓ 晋级深度K线技术建模的优质主板候选股: {len(raw_pool)} 只")

    # 3. 运行短线爆发与趋势跟踪策略模型
    print(f"\n[3/4] 正在计算 60日K线、均线斜率、ATR真实波幅与多因子连续评分...")
    evaluated_stocks = []

    total = len(raw_pool)
    for i, stock in enumerate(raw_pool, start=1):
        if i % 5 == 0 or i == total:
            print(f"  -> 深度K线建模进度: [{i}/{total}] ...")
        df_kline = fetcher.get_stock_kline(stock['symbol'], days=60)
        res = strategy.evaluate_stock(stock, df_kline)
        if res is not None:
            evaluated_stocks.append(res)

    # 按短线爆发评分降序排列
    evaluated_stocks.sort(key=lambda x: x['score'], reverse=True)
    top_recommendations = evaluated_stocks[:top_k]

    print(f"\n[4/4] 筛选完毕！共 {len(evaluated_stocks)} 只通过严格多头检验，精选 TOP {len(top_recommendations)} 推荐：")
    for rank, st in enumerate(top_recommendations, start=1):
        sign = "+" if st['change_pct'] >= 0 else ""
        print(f"\n  ⭐ TOP {rank}: {st['name']} ({st['code']}) - 严选评分: {st['score']}分")
        print(f"     现价: ¥{st['price']:.2f} ({sign}{st['change_pct']:.2f}%) | 换手率: {st['turnover_pct']}% | 量比: {st['vol_ratio']}倍 | 成交: {st['amount_yi']}亿")
        print(f"     🟢 建议低吸区间: ¥{st['buy_range']} (严禁高于现价追高)")
        print(f"     🎯 第一止盈目标: ¥{st['target_price']:.2f} (+{st['target_pct']}%) -> 预计获利 +¥{st['expected_profit_rmb']}元")
        print(f"     🛑 严格止损红线: ¥{st['stop_loss_price']:.2f} ({st['stop_loss_pct']}%) -> 最大亏损 -¥{st['max_loss_rmb']}元")
        print(f"     ⚖️ 盈亏比: {st['risk_reward_ratio']}:1 | 建议建仓: {st['suggest_shares']}股 ({st['suggest_lots']}手, 约¥{st['suggest_cost']:,.0f}元)")

    # 4. 生成可视化 HTML 分析报告
    html_file = generator.generate_html_report(indices, top_recommendations, datetime.now(BEIJING_TZ).strftime("%Y年%m月%d日 %H:%M"))
    print("\n" + "=" * 68)
    print(f"🎉 V2.0 可视化分析报告已同步更新至桌面！")
    print(f"📄 桌面报告路径: {html_file}")
    print("=" * 68)

    # 5. 开启局域网手机查看服务与生成二维码
    print("\n[5/5] 正在生成【手机扫码即看】服务...")
    mobile_url, qr_file = start_mobile_server_background(8888)
    if mobile_url:
        print(f"  📱 手机看盘链接 (同一Wi-Fi下直接打开): {mobile_url}")
        if qr_file:
            print(f"  🖼️ 桌面二维码已生成: {qr_file} (手机扫此图即可秒开)")
        print("\n  👇 手机微信 / 相机扫码直达 (需连接同一Wi-Fi)：")
        try:
            print_terminal_qr(mobile_url)
        except Exception:
            pass

    if auto_open:
        print("🚀 正在自动在默认浏览器中打开分析报告...")
        try:
            webbrowser.open(f"file:///{html_file.replace(os.sep, '/')}")
        except Exception:
            pass

    return html_file

if __name__ == '__main__':
    should_open = '--no-open' not in sys.argv
    run_pipeline(scan_count=config.SCAN_POOL_COUNT, top_k=config.TOP_RECOMMEND_COUNT, auto_open=should_open)
