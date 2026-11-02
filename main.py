# -*- coding: utf-8 -*-
"""
A股每日量化选股、持仓体检与买卖时机分析系统 (V3.0 全自动实战闭环版) - 主运行入口
核心升级：
1. 盘中动态时间折算 + 实时K线无缝拼接（早盘/尾盘/收盘全时段量比与均线零失真）；
2. 本地实盘持仓健康度体检与仓位上限联动（仅展示于本地桌面报告与微信，公开仓库100%隐私隔离）；
3. 大盘冰点空仓保护熔断器（四大指数集体杀跌时强制阻断追高买新）；
4. 支持 --push-wechat 准点向微信推送 Markdown 决策战报（由本地 14:30 计划任务触发，防云端重复轰炸）。
"""
import os
import sys
import json
import webbrowser
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, 'reconfigure') and sys.stdout is not None:
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
    except Exception:
        pass

BEIJING_TZ = timezone(timedelta(hours=8))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

from data_fetcher import AShareDataFetcher
from strategy_engine import ShortTermTrendStrategy
from report_generator import ReportGenerator
from notifier import WeChatNotifier
import config


def safe_print(msg=""):
    """兼容控制台与 pythonw.exe 静默调度的安全日志输出"""
    log_path = os.path.join(LOG_DIR, f"radar_{datetime.now(BEIJING_TZ).strftime('%Y%m%d')}.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass
    if sys.stdout is not None:
        try:
            print(msg, flush=True)
        except Exception:
            pass


def load_local_portfolio():
    """读取本地私有 portfolio.json 持仓（云端不存在此文件时返回 None）"""
    p_file = os.path.join(BASE_DIR, "portfolio.json")
    if not os.path.exists(p_file):
        return None
    try:
        with open(p_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return None


def run_pipeline(scan_count=config.SCAN_POOL_COUNT, top_k=config.TOP_RECOMMEND_COUNT, auto_open=True, push_wechat=False):
    now_dt = datetime.now(BEIJING_TZ)
    report_time_str = now_dt.strftime("%Y年%m月%d日 %H:%M")

    safe_print("=" * 70)
    safe_print("   📊 A股每日短线雷达 V3.0 (盘中实时对齐 · 持仓联动 · 冰点熔断 · 隐私隔离)")
    safe_print(f"   账户本金: ¥{config.TOTAL_CAPITAL:,.0f} 元 | 严选沪深主板 | 最多持仓: {config.MAX_HOLDINGS} 只")
    safe_print(f"   运行时间: {now_dt.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    safe_print("=" * 70)

    fetcher = AShareDataFetcher()
    strategy = ShortTermTrendStrategy()
    generator = ReportGenerator(output_dir=os.path.join(BASE_DIR, "reports"))

    # 1. 获取大盘核心指数与冰点熔断判定
    safe_print("\n[1/5] 正在抓取大盘指数环境与熔断风控判定...")
    indices = fetcher.get_market_indices()
    for idx in indices:
        sign = "+" if idx['change_pct'] >= 0 else ""
        safe_print(f"  • {idx['name']:<5} {idx['point']:>8.2f} ({sign}{idx['change_pct']:.2f}%)  成交额: {idx['amount_yi']}亿元")

    is_cb, cb_reason = strategy.check_market_circuit_breaker(indices)
    if is_cb:
        safe_print(f"  ❄️ {cb_reason}")

    # 2. 本地持仓健康度与去留体检 (若存在本地 portfolio.json)
    local_holdings = load_local_portfolio()
    holdings_diag = None
    holdings_count = 0
    if local_holdings is not None:
        holdings_diag = []
        holdings_count = len(local_holdings)
        safe_print(f"\n[2/5] 正在执行本地实盘持仓健康度体检 (当前持有 {holdings_count}/{config.MAX_HOLDINGS} 只)...")
        if local_holdings:
            syms = [h['symbol'] for h in local_holdings if h.get('symbol')]
            rt_quotes = fetcher.get_realtime_quotes(syms)
            for h in local_holdings:
                sym = h['symbol']
                q = rt_quotes.get(sym)
                df_h = fetcher.get_stock_kline(sym, days=60, realtime_bar=q)
                diag = strategy.diagnose_holding(h, q, df_h)
                holdings_diag.append(diag)
                safe_print(f"  • {diag['name']} ({diag['code']}): 现价 ¥{diag['price']:.2f} | {diag['badge']}")
                safe_print(f"    -> 指引: {diag['advice']}")
    else:
        safe_print("\n[2/5] 云端无状态环境：跳过本地私有持仓读取（确保公开页面零隐私泄露）。")

    # 3. 抓取高流动性活跃候选股票池（含盘中动态时间折算）
    safe_print(f"\n[3/5] 正在扫描全市场成交额前 {scan_count} 名活跃股并执行【五重防诱多排雷】...")
    raw_pool, stats = fetcher.get_active_stocks_pool(count=scan_count)
    safe_print(f"  ✓ 全市场扫描: {stats['total_scanned']} 只 | 盘中时间折算系数: {stats['progress_ratio']} (动态成交门槛 >= {stats['min_amount_used']}亿)")
    safe_print(f"  ✓ 权限与股价过滤: 剔除创业板/科创板 {stats['filtered_board']} 只 | 剔除高价/仙股 {stats['filtered_price']} 只")
    safe_print(f"  ✓ 诱多图形排雷: 剔除假阳线/长上影避雷针 {stats['filtered_trap_kline']} 只 | 剔除异常换手 {stats['filtered_turnover']} 只")
    safe_print(f"  ✓ 晋级深度K线实时对齐建模的主板候选股: {len(raw_pool)} 只")

    # 4. 运行短线爆发与趋势跟踪策略模型（实时Bar无缝拼接）
    safe_print(f"\n[4/5] 正在拼接当日实时K线并计算均线斜率、动态量比、ATR波幅与多因子评分...")
    evaluated_stocks = []
    holding_codes = {h['code'] for h in (local_holdings or [])}

    total = len(raw_pool)
    for i, stock in enumerate(raw_pool, start=1):
        if i % 10 == 0 or i == total:
            safe_print(f"  -> 深度K线建模进度: [{i}/{total}] ...")
        # 自动过滤已在持仓中的股票，避免重复推荐买同一只
        if stock['code'] in holding_codes:
            continue
        df_kline = fetcher.get_stock_kline(stock['symbol'], days=60, realtime_bar=stock)
        res = strategy.evaluate_stock(stock, df_kline, holdings_count=holdings_count, is_circuit_breaker=is_cb)
        if res is not None:
            evaluated_stocks.append(res)

    evaluated_stocks.sort(key=lambda x: x['score'], reverse=True)
    top_recommendations = evaluated_stocks[:top_k]

    safe_print(f"\n[5/5] 筛选完毕！共 {len(evaluated_stocks)} 只通过严格多头检验，精选 TOP {len(top_recommendations)}：")
    for rank, st in enumerate(top_recommendations, start=1):
        sign = "+" if st['change_pct'] >= 0 else ""
        safe_print(f"\n  ⭐ TOP {rank}: {st['name']} ({st['code']}) - 严选评分: {st['score']}分")
        safe_print(f"     现价: ¥{st['price']:.2f} ({sign}{st['change_pct']:.2f}%) | 换手率: {st['turnover_pct']}% | 动态量比: {st['vol_ratio']}倍 | 成交: {st['amount_yi']}亿")
        safe_print(f"     🟢 建议低吸区间: ¥{st['buy_range']} (严禁高于现价追高)")
        safe_print(f"     🎯 第一止盈目标: ¥{st['target_price']:.2f} (+{st['target_pct']}%) | 🛑 严格止损红线: ¥{st['stop_loss_price']:.2f} ({st['stop_loss_pct']}%)")
        safe_print(f"     ⚖️ 盈亏比: {st['risk_reward_ratio']}:1 | 仓位指引: {st['suggest_pos']}")

    # 生成可视化 HTML 分析报告（公共无隐私版 + 本地桌面带持仓版）
    html_file = generator.generate_html_report(
        indices,
        top_recommendations,
        report_date=report_time_str,
        holdings_diag=holdings_diag,
        circuit_breaker=(is_cb, cb_reason)
    )
    safe_print("\n" + "=" * 70)
    safe_print("🎉 V3.0 可视化分析报告已同步更新至桌面（个人持仓隐私已与公开仓库严格物理隔离）！")
    safe_print(f"📄 本地报告路径: {html_file}")
    safe_print("=" * 70)

    # 若指定了 --push-wechat（如本地 14:30 计划任务），准时向手机微信发送综合决策战报
    if push_wechat:
        safe_print("📲 正在向您的微信推送【持仓体检 + 尾盘严选】综合战报...")
        notifier = WeChatNotifier()
        notifier.send_push(
            indices,
            top_recommendations,
            report_time_str,
            holdings_diag=holdings_diag,
            circuit_breaker=(is_cb, cb_reason)
        )

    if auto_open:
        safe_print("🚀 正在默认浏览器中打开分析报告...")
        try:
            webbrowser.open(f"file:///{html_file.replace(os.sep, '/')}")
        except Exception:
            pass

    return html_file


if __name__ == '__main__':
    should_open = '--no-open' not in sys.argv
    should_push = '--push-wechat' in sys.argv
    run_pipeline(
        scan_count=config.SCAN_POOL_COUNT,
        top_k=config.TOP_RECOMMEND_COUNT,
        auto_open=should_open,
        push_wechat=should_push
    )
