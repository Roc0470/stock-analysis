# -*- coding: utf-8 -*-
"""
A股持仓实盘毫秒级盯盘与主动卖出报警机器人 (Real-Time Portfolio Monitor)
功能：
1. 盘中每 15~20 秒自动拉取最新分时行情；
2. 触碰【止盈目标】或【保本止损红线】时，立即触发主动报警；
3. 支持：Windows 桌面悬浮气泡弹窗、系统提示音报警、微信服务号推送；
4. 带有防重复骚扰冷却机制（同一警报 10 分钟内不重复轰炸）。
"""
import time
import os
import sys
from datetime import datetime, timezone, timedelta
import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

BEIJING_TZ = timezone(timedelta(hours=8))

# 当前实盘监控持仓名单与风控底线 (默认后备)
DEFAULT_HOLDINGS = [
    {
        'symbol': 'sz002129',
        'code': '002129',
        'name': 'TCL中环',
        'cost': 9.178,
        'stop_loss': 9.20,       # 绝对保本红线：跌破坚决一键市价平仓
        'take_profit': 10.11,    # 第一止盈目标
        'warn_pullback': 2.5,    # 盘中高点回撤超 2.5% 预警
        'shares': 600
    },
    {
        'symbol': 'sh600741',
        'code': '600741',
        'name': '华域汽车',
        'cost': 14.162,          # 摊薄后底仓成本
        'stop_loss': 15.90,      # 抬高后的移动锁利止损线
        'take_profit': 16.50,    # 清仓止盈目标
        'warn_pullback': 2.0,
        'shares': 100
    }
]

def get_active_holdings():
    """动态读取由同花顺一键同步的 portfolio.json 活跃持仓"""
    p_file = os.path.join(os.path.dirname(__file__), "portfolio.json")
    if os.path.exists(p_file):
        try:
            import json
            with open(p_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and isinstance(data, list):
                    res = []
                    for d in data:
                        res.append({
                            'symbol': d['symbol'],
                            'code': d['code'],
                            'name': d['name'],
                            'cost': d['cost'],
                            'stop_loss': d.get('stop_loss', round(d['cost'] * 0.95, 2)),
                            'take_profit': d.get('take_profit', round(d['cost'] * 1.08, 2)),
                            'warn_pullback': 2.5,
                            'shares': d.get('shares', 100)
                        })
                    return res
        except Exception:
            pass
    return DEFAULT_HOLDINGS

def save_active_holdings(holdings):
    """持久化更新活跃持仓到 portfolio.json"""
    p_file = os.path.join(os.path.dirname(__file__), "portfolio.json")
    try:
        import json
        with open(p_file, "w", encoding="utf-8") as f:
            json.dump(holdings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[提示] 持久化 portfolio.json 失败: {e}")

class RealTimeMonitor:
    def __init__(self, check_interval=20):
        self.interval = check_interval
        self.alert_history = {} # 记录警报时间防刷屏
        self.session = requests.Session()
        self.session.trust_env = False
        self.headers = {'Referer': 'https://finance.sina.com.cn'}

    def is_trading_time(self):
        """判断当前是否为 A股 交易时间 (工作日 9:25~11:35, 12:55~15:05)"""
        now = datetime.now(BEIJING_TZ)
        if now.weekday() >= 5: # 周六周日
            return False
        h_m = now.hour * 100 + now.minute
        return (925 <= h_m <= 1135) or (1255 <= h_m <= 1505)

    def play_alert_sound(self):
        """根据用户偏好播放柔和轻音或保持纯静音"""
        import config
        mode = getattr(config, 'ALERT_SOUND_MODE', 'silent').lower()
        if mode == 'silent':
            return  # 纯静音模式：不发出任何刺耳声音，仅弹窗提醒

        try:
            import winsound
            if mode == 'soft':
                # Windows 官方轻柔水滴/邮件提示音
                soft_wav = r"C:\Windows\Media\Windows Notify Messaging.wav"
                if not os.path.exists(soft_wav):
                    soft_wav = r"C:\Windows\Media\Windows Notify Email.wav"
                if os.path.exists(soft_wav):
                    winsound.PlaySound(soft_wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
            elif mode == 'loud':
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    def send_windows_notification(self, title, message):
        """调用 Windows 原生通知弹窗（静音/柔和可选）"""
        self.play_alert_sound()

        try:
            # 使用 PowerShell 原生触发 Windows 气泡通知 (免安装第三方库)
            clean_title = title.replace('"', '`"')
            clean_msg = message.replace('"', '`"')
            ps_cmd = f'''
            [void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");
            $objNotifyIcon = New-Object System.Windows.Forms.NotifyIcon;
            $objNotifyIcon.Icon = [System.Drawing.SystemIcons]::Exclamation;
            $objNotifyIcon.BalloonTipIcon = "Warning";
            $objNotifyIcon.BalloonTipTitle = "{clean_title}";
            $objNotifyIcon.BalloonTipText = "{clean_msg}";
            $objNotifyIcon.Visible = $True;
            $objNotifyIcon.ShowBalloonTip(10000);
            '''
            os.system(f'powershell -Command "{ps_cmd}" > nul 2>&1')
        except Exception as e:
            print(f"[提示] Windows 通知发送失败: {e}")

    def send_wechat_alert(self, title, content):
        """向微信推送紧急预警消息 (支持 Server酱 / WxPusher / Webhook)"""
        import config
        # 1. 尝试 Server酱
        sct_key = getattr(config, 'SERVERCHAN_KEY', '')
        if sct_key:
            try:
                requests.post(f"https://sctapi.ftqq.com/{sct_key}.send", data={'title': title, 'desp': content}, timeout=5)
            except Exception:
                pass

        # 2. 尝试 WxPusher
        wx_token = getattr(config, 'WXPUSHER_TOKEN', '')
        wx_uids = getattr(config, 'WXPUSHER_UIDS', [])
        if wx_token and wx_uids:
            try:
                requests.post("http://wxpusher.zjiecode.com/api/send/message", json={
                    'appToken': wx_token,
                    'content': f"### {title}\n\n{content}",
                    'contentType': 3,
                    'uids': wx_uids
                }, timeout=5)
            except Exception:
                pass

    def check_clipboard_sync(self):
        """若检测到用户在同花顺中执行了复制操作，全自动静默捕获并同步更新持仓"""
        try:
            import sync_portfolio
            text = sync_portfolio.get_clipboard_text()
            if text and ('证券代码' in text or '股票代码' in text) and text != getattr(self, '_last_cb_text', ''):
                self._last_cb_text = text
                print(f"[{datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] 📋 捕获到同花顺持仓复制事件，全自动智能同步中...")
                sync_portfolio.sync_now(text)
        except Exception:
            pass

    def check_portfolio(self):
        """执行单次持仓价格拉取与风控比对"""
        self.check_clipboard_sync()
        holdings = get_active_holdings()
        symbols = [h['symbol'] for h in holdings]
        if not symbols:
            return
        url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
        try:
            r = self.session.get(url, headers=self.headers, timeout=6)
            r.encoding = 'gbk'
        except Exception as e:
            print(f"[{datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] 网络请求超时: {e}")
            return

        now_str = datetime.now(BEIJING_TZ).strftime("%H:%M:%S")
        print(f"\n[{now_str}] 实时盘口轮询检查：")

        for line in r.text.strip().split('\n'):
            if '=' not in line:
                continue
            sym = line.split('=')[0].split('_')[-1]
            data = line.split('=')[1].strip('" ;\n').split(',')
            if len(data) < 10:
                continue

            cfg = next((h for h in holdings if h['symbol'] == sym), None)
            if not cfg:
                continue

            name = data[0]
            pre = float(data[2])
            cur = float(data[3])
            high = float(data[4])
            low = float(data[5])
            amount_yi = round(float(data[9]) / 1e8, 2)
            pct = round((cur - pre) / pre * 100, 2)
            profit_rmb = round((cur - cfg['cost']) * cfg['shares'], 2)

            print(f"  • {name:<5} 现价: ¥{cur:>6.2f} ({pct:+5.2f}%) | 成本: ¥{cfg['cost']:.3f} | 浮盈: {profit_rmb:+6.1f}元 | 今低: ¥{low:.2f}")

            # 0. 智能移动止损自动抬高研判 (Trailing Stop Ratchet - 只升不降保护利润)
            cost = cfg['cost']
            old_stop = cfg['stop_loss']
            gain_pct = (cur - cost) / cost * 100 if cost > 0 else 0
            
            # 计算建议防守线：
            # (1) 浮盈阶梯：>=3% 保本(cost)；>=5% 锁利(cost*1.025)；>=8% 锁利(cost*1.05)
            # (2) 冲高回撤保护：若冲高幅度较大，回撤保护线设在 high * 0.97 (最高点下浮 3%)
            calc_stops = [old_stop]
            if cfg['code'] == '600741':
                calc_stops.append(15.90) # 保持用户确认的最低防守线
            if gain_pct >= 8.0:
                calc_stops.append(round(cost * 1.05, 2))
            elif gain_pct >= 5.0:
                calc_stops.append(round(cost * 1.025, 2))
            elif gain_pct >= 3.0:
                calc_stops.append(round(cost, 2))
            
            if high >= cost * 1.05:
                calc_stops.append(round(high * 0.97, 2))

            new_stop = max(calc_stops)
            # 新止损必须低于现价至少 0.05 元，且较原止损抬高 0.05 元以上才触发更新
            if new_stop > old_stop + 0.05 and new_stop < cur:
                cfg['stop_loss'] = new_stop
                # 同步持久化到 portfolio.json
                all_holdings = get_active_holdings()
                for item in all_holdings:
                    if item['symbol'] == sym:
                        item['stop_loss'] = new_stop
                        item['updated_at'] = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
                save_active_holdings(all_holdings)

                title = f"🛡️【自动抬高止损】{name} 保护线已上调至 ¥{new_stop}！"
                msg = (
                    f"### 🛡️ 智能移动锁利：止损防守线已自动上调\n\n"
                    f"- **标的**：{name} ({cfg['code']})\n"
                    f"- **现价**：¥{cur:.2f} (当前浮盈 {gain_pct:+.2f}%)\n"
                    f"- **日内最高**：¥{high:.2f}\n"
                    f"- **止损保护线**：原 ¥{old_stop:.2f} ➔ **已自动上调至 ¥{new_stop:.2f}**\n\n"
                    f"💡 **锁利效果**：系统已全自动更新后台风控参数。后续若跌破 ¥{new_stop:.2f}，将立即触发微信卖出警报，确保稳稳落袋大部分利润！"
                )
                print(f"\n>>> {title}\n{msg}\n")
                self.send_windows_notification(title, f"{name} 保护线已自动抬高至 ¥{new_stop} (现价 ¥{cur:.2f})")
                self.send_wechat_alert(title, msg)

            # 1. 触发保本 / 止损红线 (最紧急：执行卖出)
            if cur <= cfg['stop_loss']:
                alert_key = f"{sym}_stop"
                if time.time() - self.alert_history.get(alert_key, 0) > 300: # 5分钟防重复
                    self.alert_history[alert_key] = time.time()
                    title = f"🚨【建议立即卖出】{name} 触碰止损防守线 ¥{cfg['stop_loss']}！"
                    sell_shares = cfg['shares']
                    msg = (
                        f"### 🚨 操作建议：立即执行卖出平仓\n\n"
                        f"- **标的**：{name} ({cfg['code']})\n"
                        f"- **现价**：¥{cur:.2f} (今低 ¥{low:.2f})\n"
                        f"- **触发原因**：跌破移动止损防守线 ¥{cfg['stop_loss']:.2f}\n\n"
                        f"📱 **同花顺具体委托操作指引**：\n"
                        f"1. 打开同花顺 App 或电脑端；\n"
                        f"2. 进入【交易】➔【持仓】找到【{name}】点【卖出】；\n"
                        f"3. 委托类型选择【市价委托】或现价卖出；\n"
                        f"4. 委托数量选择：**全部 {sell_shares} 股**；\n"
                        f"5. 点击确认卖出，锁定利润/防守本金！"
                    )
                    print(f"\n>>> {title}\n{msg}\n")
                    self.send_windows_notification(title, f"{name} 触碰防守线 ¥{cfg['stop_loss']}，建议在同花顺市价清仓！")
                    self.send_wechat_alert(title, msg)

            # 2. 触发止盈目标价 (达标落袋：建议卖出)
            elif cur >= cfg['take_profit']:
                alert_key = f"{sym}_target"
                if time.time() - self.alert_history.get(alert_key, 0) > 300:
                    self.alert_history[alert_key] = time.time()
                    title = f"🎯【止盈达标·建议卖出】{name} 已达到目标价 ¥{cfg['take_profit']}！"
                    if cfg['shares'] <= 100:
                        sell_desc = f"持仓仅剩 100 股底仓，建议**全部卖出清仓**锁定全部战果"
                        sell_shares = cfg['shares']
                    else:
                        sell_desc = f"建议**卖出一半 ({cfg['shares'] // 100 * 50} 股)**锁定利润，剩余底仓继续博更高"
                        sell_shares = (cfg['shares'] // 200) * 100

                    msg = (
                        f"### 🎯 操作建议：达到止盈目标，落袋为安\n\n"
                        f"- **标的**：{name} ({cfg['code']})\n"
                        f"- **现价**：¥{cur:.2f} (已达目标价 ¥{cfg['take_profit']:.2f})\n"
                        f"- **策略指引**：{sell_desc}\n\n"
                        f"📱 **同花顺具体委托操作指引**：\n"
                        f"1. 打开同花顺【交易】➔【持仓】；\n"
                        f"2. 选择【{name}】点击【卖出】；\n"
                        f"3. 建议委托数量：**{sell_shares} 股**；\n"
                        f"4. 提交委托，大获全胜！"
                    )
                    print(f"\n>>> {title}\n{msg}\n")
                    self.send_windows_notification(title, f"{name} 已达目标价 ¥{cfg['take_profit']}，建议在同花顺卖出锁定利润！")
                    self.send_wechat_alert(title, msg)

            # 3. 盘中冲高大幅回撤预警 (走弱提醒)
            elif high > cfg['cost'] * 1.02 and (high - cur) / high * 100 >= cfg['warn_pullback']:
                alert_key = f"{sym}_pullback"
                if time.time() - self.alert_history.get(alert_key, 0) > 600:
                    self.alert_history[alert_key] = time.time()
                    pull_pct = round((high - cur) / high * 100, 1)
                    title = f"⚠️【冲高回落预警】{name} 距高点回撤达 {pull_pct}%"
                    msg = (
                        f"### ⚠️ 技术面走弱预警：冲高回落\n\n"
                        f"- **标的**：{name} ({cfg['code']})\n"
                        f"- **早盘最高**：¥{high:.2f} ➔ **现价**：¥{cur:.2f} (回撤 {pull_pct}%)\n"
                        f"- **研判分析**：分时出现冲高滞涨，买盘动能减弱。\n"
                        f"- **应对策略**：密切注意分时均线得失，若无力反包，建议提前在同花顺减仓或择机卖出。"
                    )
                    print(f"\n>>> {title}\n{msg}\n")
                    self.send_windows_notification(title, f"{name} 早盘冲高 ¥{high} 后回撤 {pull_pct}%，注意防守！")
                    self.send_wechat_alert(title, msg)

    def run_forever(self, auto_exit_at_close=True):
        holdings = get_active_holdings()
        print("=" * 68)
        print("   🤖 A股持仓实盘毫秒级盯盘机器人启动")
        print(f"   监控标的: {', '.join([h['name'] for h in holdings])}")
        print(f"   刷新频率: 每 {self.interval} 秒自动比对一次盘口")
        print("   报警方式: Windows 弹窗提示音 + 微信主动推送 (触碰自动报警)")
        print("=" * 68)

        while True:
            try:
                now = datetime.now(BEIJING_TZ)
                # 若非交易时间且设定了收盘自动退出，在 15:05 后自动停止
                if auto_exit_at_close and (now.hour > 15 or (now.hour == 15 and now.minute >= 5)):
                    print(f"\n[{now.strftime('%H:%M:%S')}] 今日 A股 交易已收盘，盯盘守护进程安全退出。")
                    break

                self.check_portfolio()
                time.sleep(self.interval)
            except KeyboardInterrupt:
                print("\n[退出] 盯盘服务已手动停止。")
                break
            except Exception as e:
                print(f"[异常] 轮询出错: {e}")
                time.sleep(5)

if __name__ == '__main__':
    monitor = RealTimeMonitor(check_interval=15)
    monitor.run_forever()
