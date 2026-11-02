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


def run_pipeline(scan_count=config.SCAN_POOL_COUNT, top_k=config.TOP_RECOMMEND_COUNT, auto_open=True, push_wechat=False, morning_sniper=False):
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

    # 3 & 4. 阶梯式自适应深潜扫描（先扫前 400 名，若 ✅ 绿灯可买股不足 3 只，自动继续向下扩扫，直至凑齐绿灯股或触及 2.0 亿成交额底线）
    step_size = getattr(config, 'SCAN_STEP_COUNT', 400)
    max_scan = getattr(config, 'MAX_SCAN_COUNT', 1600)
    min_green_target = getattr(config, 'MIN_GREEN_TARGET', 3)

    green_stocks = []
    watch_stocks = []
    holding_codes = {h['code'] for h in (local_holdings or [])}
    seen_codes = set(holding_codes)

    current_start = 1
    total_raw_scanned = 0
    while current_start <= max_scan:
        end_rank = current_start + step_size - 1
        safe_print(f"\n[3/5] 正在执行阶梯式扫描：第 {current_start}~{end_rank} 名活跃股并执行【五重防诱多排雷】...")
        raw_pool, stats = fetcher.get_active_stocks_pool(count=step_size, start_rank=current_start)
        total_raw_scanned += stats['total_scanned']
        safe_print(f"  ✓ 本轮扫描: {stats['total_scanned']} 只 (累计 {total_raw_scanned} 只) | 动态成交门槛 >= {stats['min_amount_used']}亿")
        safe_print(f"  ✓ 晋级深度K线实时对齐建模的主板候选股: {len(raw_pool)} 只")

        if raw_pool:
            safe_print(f"[4/5] 正在对本批 {len(raw_pool)} 只候选股拼接实时K线并计算绿灯买点与多因子评分...")
            for stock in raw_pool:
                if stock['code'] in seen_codes:
                    continue
                seen_codes.add(stock['code'])
                df_kline = fetcher.get_stock_kline(stock['symbol'], days=60, realtime_bar=stock)
                res = strategy.evaluate_stock(stock, df_kline, holdings_count=holdings_count, is_circuit_breaker=is_cb)
                if res is not None:
                    if res.get('buy_status') == 'in_zone':
                        green_stocks.append(res)
                    else:
                        watch_stocks.append(res)

        if len(green_stocks) >= min_green_target:
            safe_print(f"  🎯 已捕获 {len(green_stocks)} 只【✅ 绿灯直接可买股】（达到 >= {min_green_target} 只目标），停止继续下探！")
            break
        if stats.get('reached_amount_floor') or stats['total_scanned'] == 0:
            safe_print(f"  🛑 已触及全市场成交额底线 ({stats['min_amount_used']}亿元)，停止继续下探。")
            break
        if current_start + step_size <= max_scan:
            safe_print(f"  🔍 当前仅发现 {len(green_stocks)} 只绿灯可买股（不足 {min_green_target} 只），自动向下扩扫下一阶梯...")
        current_start += step_size

    # 主买榜 100% 仅展示 ✅ 绿灯直接可买股（按评分从高到低排序），⚠️ 黄灯股移入底部折叠观察区
    green_stocks.sort(key=lambda x: x['score'], reverse=True)
    watch_stocks.sort(key=lambda x: x['score'], reverse=True)
    top_recommendations = green_stocks[:top_k]

    safe_print(f"\n[5/5] 筛选完毕！累计扫描 {total_raw_scanned} 只活跃股，共捕获 {len(green_stocks)} 只【✅ 绿灯可买股】与 {len(watch_stocks)} 只【⚠️ 黄灯观察股】，主买榜精选 TOP {len(top_recommendations)}：")
    for rank, st in enumerate(top_recommendations, start=1):
        sign = "+" if st['change_pct'] >= 0 else ""
        safe_print(f"\n  ⭐ TOP {rank}: {st['name']} ({st['code']}) - 严选评分: {st['score']}分")
        safe_print(f"     现价: ¥{st['price']:.2f} ({sign}{st['change_pct']:.2f}%) | 换手率: {st['turnover_pct']}% | 动态量比: {st['vol_ratio']}倍 | 成交: {st['amount_yi']}亿")
        safe_print(f"     🟢 理想低吸区间: ¥{st['buy_range']} | {st.get('buy_tip', '')}")
        safe_print(f"     🎯 第一止盈目标: ¥{st['target_price']:.2f} (+{st['target_pct']}%) | 🛑 严格止损红线: ¥{st['stop_loss_price']:.2f} ({st['stop_loss_pct']}%)")
        safe_print(f"     ⚖️ 盈亏比: {st['risk_reward_ratio']}:1 | 仓位指引: {st['suggest_pos']}")

    # 生成可视化 HTML 分析报告（公共无隐私版 + 本地桌面带持仓版）
    html_file = generator.generate_html_report(
        indices,
        top_recommendations,
        report_date=report_time_str,
        holdings_diag=holdings_diag,
        circuit_breaker=(is_cb, cb_reason),
        watch_stocks=watch_stocks
    )
    safe_print("\n" + "=" * 70)
    safe_print("🎉 V3.0 可视化分析报告已同步更新至桌面（个人持仓隐私已与公开仓库严格物理隔离）！")
    safe_print(f"📄 本地报告路径: {html_file}")
    safe_print("=" * 70)

    # 若为早盘 10:15 狙击手模式 (--morning-sniper)，仅在“大盘多头共振 + 仓位未满 + >=90分温和启动极品”时才触发微信推送
    if morning_sniper:
        up_idx_cnt = sum(1 for idx in indices if idx['change_pct'] > 0)
        sh_up = any(idx['code'] == '000001' and idx['change_pct'] >= 0 for idx in indices)
        min_sc = getattr(config, 'MORNING_SNIPER_MIN_SCORE', 90.0)
        min_chg = getattr(config, 'MORNING_SNIPER_MIN_CHANGE', 1.8)
        max_chg = getattr(config, 'MORNING_SNIPER_MAX_CHANGE', 4.8)

        sniper_picks = [
            st for st in top_recommendations
            if st['score'] >= min_sc and (min_chg <= st['change_pct'] <= max_chg)
        ][:2]

        if not is_cb and up_idx_cnt >= 3 and sh_up and holdings_count < config.MAX_HOLDINGS and sniper_picks:
            safe_print(f"🎯 [早盘极品狙击触发] 大盘多头共振且发现 {len(sniper_picks)} 只 >=90分启动期极品，正在推送微信...")
            notifier = WeChatNotifier()
            notifier.send_push(
                indices,
                sniper_picks,
                report_time_str + " (早盘狙击专报)",
                holdings_diag=holdings_diag,
                circuit_breaker=(is_cb, cb_reason)
            )
        else:
            safe_print("🛡️ [早盘狙击静默] 当前未同时满足“大盘全红共振 + 未满仓 + >=90分温和启动极品”，早盘保持静默不打扰，静候 14:30 尾盘主力战报。")
    elif push_wechat:
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
    is_sniper = '--morning-sniper' in sys.argv
    run_pipeline(
        scan_count=getattr(config, 'SCAN_STEP_COUNT', 400),
        top_k=config.TOP_RECOMMEND_COUNT,
        auto_open=should_open,
        push_wechat=should_push,
        morning_sniper=is_sniper
    )
