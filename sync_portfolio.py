# -*- coding: utf-8 -*-
"""
同花顺持仓一键智能同步器 (V3.0 智能记忆与 ATR 定锚版)
核心升级：
1. 老持仓记忆锁死：再次复制同步时仅更新股数与参考成本，严格保留已锁定的止盈线、移动止损线与跨日最高水位，彻底杜绝目标价随现价被动漂移！
2. 新持仓 ATR 定锚：首次新买入的股票自动拉取 60 日 K 线测算 ATR(14) 真实波幅与均线支撑，生成科学初始止盈止损位。
3. 自动过滤国债逆回购、标准券与已清仓股票（0股）。
"""
import os
import sys
import re
import json
import requests
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, 'reconfigure') and sys.stdout is not None:
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
    except Exception:
        pass

BEIJING_TZ = timezone(timedelta(hours=8))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(BASE_DIR, "portfolio.json")


def get_clipboard_text():
    """读取 Windows 剪贴板文本"""
    try:
        import win32clipboard
        import win32con
        win32clipboard.OpenClipboard()
        text = ""
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        elif win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_TEXT).decode('gbk', errors='ignore')
        win32clipboard.CloseClipboard()
        return text
    except Exception:
        return ""


def load_existing_map():
    """读取本地既有持仓配置字典，用于继承既有止盈止损与历史最高水位"""
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {str(item.get('code')): item for item in data if item.get('code')}
        except Exception:
            pass
    return {}


def parse_ths_table(text, existing_map=None):
    """解析同花顺持仓网格表格数据，区分【老仓锁死继承】与【新仓ATR定锚】"""
    if not text or ('证券代码' not in text and '股票代码' not in text):
        return None

    existing_map = existing_map if existing_map is not None else load_existing_map()
    fetcher = None
    strategy_cls = None

    lines = text.strip().split('\n')
    holdings = []
    now_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")

    for line in lines:
        parts = [p.strip() for p in line.split('\t') if p.strip()]
        code_idx = None
        for i, p in enumerate(parts):
            if re.match(r'^\d{6}$', p):
                code_idx = i
                break

        if code_idx is not None and len(parts) > code_idx + 6:
            code = parts[code_idx]
            name = parts[code_idx + 1]
            # 仅监控沪深 A 股股票，过滤标准券、逆回购、场内货币基金等
            if not re.match(r'^(60|68|00|30)\d{4}$', code) or any(k in name for k in ['标准券', '回购', '质押', '国债']):
                continue

            try:
                shares = int(float(parts[code_idx + 2]))
                if shares <= 0:
                    continue

                cost = float(parts[code_idx + 5])
                market_p = float(parts[code_idx + 6])
                prefix = 'sh' if code.startswith(('60', '68')) else 'sz'
                symbol = f"{prefix}{code}"

                if code in existing_map:
                    # 【老持仓】：严格继承既有止损线、止盈线与跨日最高水位，杜绝目标价乱漂移！
                    old = existing_map[code]
                    stop_loss = float(old.get('stop_loss', round(cost * 0.952, 2)))
                    take_profit = float(old.get('take_profit', round(max(cost * 1.08, market_p * 1.05), 2)))
                    highest_price = round(max(float(old.get('highest_price', 0.0)), market_p, cost), 2)
                    warn_pullback = float(old.get('warn_pullback', 2.5))
                    sync_tag = "继承既有风控"
                else:
                    # 【首次新买入持仓】：自动拉取 60日 K 线测算 ATR(14) 初始科学止盈止损
                    if fetcher is None:
                        from data_fetcher import AShareDataFetcher
                        from strategy_engine import ShortTermTrendStrategy
                        fetcher = AShareDataFetcher()
                        strategy_cls = ShortTermTrendStrategy

                    df_kline = fetcher.get_stock_kline(symbol, days=60)
                    stop_loss, take_profit = strategy_cls.calc_initial_atr_stops(df_kline, cost, market_p)
                    highest_price = round(max(cost, market_p), 2)
                    warn_pullback = 2.5
                    sync_tag = "新仓ATR定锚"

                holdings.append({
                    'symbol': symbol,
                    'code': code,
                    'name': name,
                    'shares': shares,
                    'cost': cost,
                    'market_price': market_p,
                    'highest_price': highest_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'warn_pullback': warn_pullback,
                    'sync_mode': sync_tag,
                    'updated_at': now_str
                })
            except Exception:
                continue

    return holdings


def sync_now(custom_text=None):
    text = custom_text if custom_text is not None else get_clipboard_text()
    existing_map = load_existing_map()
    holdings = parse_ths_table(text, existing_map=existing_map)

    if holdings is None:
        print("❌ 未在剪贴板中检测到有效的同花顺持仓表格数据！")
        print("💡 正确操作方法：")
        print("   1. 打开同花顺客户端【持仓】界面；")
        print("   2. 在持仓列表按【Ctrl + C】复制；")
        print("   3. 后台盯盘机器人会自动秒级静默同步（也可再次运行本脚本）。")
        return False

    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

    print("=" * 66)
    print("🎉 同花顺实盘持仓已成功同步！(老仓锁死防漂移 · 新仓ATR科学定锚)")
    print(f"📊 同步时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')} | 当前活跃持仓: {len(holdings)} 只")
    print("=" * 66)
    for h in holdings:
        print(
            f"  • {h['name']} ({h['code']}) [{h['sync_mode']}]: {h['shares']}股 | 成本: ¥{h['cost']:.3f} "
            f"| 现价: ¥{h['market_price']:.2f} | 防守线: ¥{h['stop_loss']:.2f} | 止盈线: ¥{h['take_profit']:.2f}"
        )
    print("=" * 66)

    # 发送微信同步确认
    try:
        import config
        sct_key = getattr(config, 'SERVERCHAN_KEY', '')
        if sct_key:
            if holdings:
                msg_lines = [
                    f"- **{h['name']} ({h['code']})** `[{h['sync_mode']}]`：{h['shares']}股 | 成本 ¥{h['cost']:.3f} | 防守线 **¥{h['stop_loss']:.2f}** | 目标价 **¥{h['take_profit']:.2f}**"
                    for h in holdings
                ]
                desp = "### 📋 同花顺实盘持仓同步成功\n\n" + "\n".join(msg_lines) + "\n\n🤖 毫秒级盯盘机器人已按上述锁定风控线实时护航。"
            else:
                desp = "### 📋 同花顺实盘持仓已全部清仓（当前空仓 0 只）\n\n🤖 盯盘机器人进入空仓待命状态。"
            requests.post(
                f"https://sctapi.ftqq.com/{sct_key}.send",
                data={'title': f'【持仓同步完成】当前活跃持仓 {len(holdings)} 只', 'desp': desp},
                timeout=5
            )
    except Exception:
        pass

    return True


if __name__ == '__main__':
    sync_now()
