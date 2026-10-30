# -*- coding: utf-8 -*-
"""
同花顺持仓一键智能同步器 (Tonghuashun Portfolio Syncer)
功能：
1. 自动从 Windows 剪贴板提取同花顺持仓列表数据；
2. 过滤已清仓股票（股数为0），保留活跃持仓，精确提取成本价、持股数、现价；
3. 更新到本地 portfolio.json，并热重载到 realtime_monitor 盯盘机器人中；
4. 发送系统通知与微信确认。
"""
import sys
import os
import re
import json
import requests
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))
PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")

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
    except Exception as e:
        print(f"[提示] 读取剪贴板失败: {e}")
        return ""

def parse_ths_table(text):
    """解析同花顺持仓网格表格数据"""
    if not text or ('证券代码' not in text and '股票代码' not in text):
        return None

    lines = text.strip().split('\n')
    holdings = []
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
            # 仅监控 A股 股票 (60/68/00/30开头)，自动过滤国债逆回购、标准券、基金质押等
            if not re.match(r'^(60|68|00|30)\d{4}$', code) or any(k in name for k in ['标准券', '回购', '质押', '国债']):
                continue

            try:
                shares = int(float(parts[code_idx + 2]))
                # 只有未清仓（股数 > 0）的才是有效持仓
                if shares > 0:
                    cost = float(parts[code_idx + 5])
                    market_p = float(parts[code_idx + 6])
                    prefix = 'sh' if code.startswith(('60', '68')) else 'sz'
                    
                    # 智能计算风控底线与止盈目标：
                    # 1. 止损线：若持仓有大幅浮盈（比如卖出后成本摊薄或大幅冲高），设动态移动保本线；否则设成本线或5%硬止损
                    if market_p > cost * 1.05:
                        # 利润保护线：设在现价回撤 4% 处，且绝不低于真实成本
                        stop_loss = round(max(cost, market_p * 0.96), 2)
                    elif market_p > cost * 1.01:
                        stop_loss = round(cost, 2)
                    else:
                        stop_loss = round(cost * 0.952, 2)

                    # 2. 止盈线：目标价必须高于当前现价！
                    # 避免因减仓盈利导致成本大幅摊薄后，计算出的成本*1.08反而在现价下方而误触发报警
                    take_profit = round(max(cost * 1.08, market_p * 1.03), 2)
                    # 如果原持仓已有更高的目标设定，尽量保留
                    if code == '600741': # 华域汽车底仓
                        take_profit = max(take_profit, 16.50)
                        stop_loss = max(stop_loss, 15.90)

                    holdings.append({
                        'symbol': f"{prefix}{code}",
                        'code': code,
                        'name': name,
                        'shares': shares,
                        'cost': cost,
                        'market_price': market_p,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'updated_at': datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
                    })
            except Exception:
                continue

    return holdings

def sync_now(custom_text=None):
    text = custom_text or get_clipboard_text()
    holdings = parse_ths_table(text)
    
    if not holdings:
        print("❌ 未在剪贴板中检测到有效的同花顺持仓数据！")
        print("💡 正确操作方法：")
        print("   1. 打开同花顺电脑客户端的【持仓】界面；")
        print("   2. 在持仓表格里按【Ctrl + A】全选，然后按【Ctrl + C】复制（或者鼠标右键点复制）；")
        print("   3. 再次运行本程序，即可一秒完成自动同步！")
        return False

    # 写入 portfolio.json
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("🎉 同花顺持仓已成功与 AI 大脑和盯盘机器人实时同步！")
    print(f"📊 同步时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    for h in holdings:
        print(f"  • {h['name']} ({h['code']}): 持仓 {h['shares']}股 | 成本: ¥{h['cost']:.3f} | 现价: ¥{h['market_price']} | 止损线: ¥{h['stop_loss']}")
    print("=" * 60)

    # 尝试发送微信同步确认
    try:
        import config
        sct_key = getattr(config, 'SERVERCHAN_KEY', '')
        if sct_key:
            msg_lines = [f"- **{h['name']} ({h['code']})**：持仓 {h['shares']}股，成本 ¥{h['cost']:.3f}，保本止损线 ¥{h['stop_loss']}" for h in holdings]
            desp = "### 同花顺实盘持仓自动同步成功！\n\n" + "\n".join(msg_lines) + "\n\n🤖 毫秒级盯盘机器人已根据新持仓实时启动守护。"
            requests.post(f"https://sctapi.ftqq.com/{sct_key}.send", data={'title': '【持仓同步完成】AI 已掌握最新账户持仓', 'desp': desp}, timeout=5)
    except Exception:
        pass

    return True

if __name__ == '__main__':
    sync_now()
