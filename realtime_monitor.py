# -*- coding: utf-8 -*-
"""
A股持仓实盘毫秒级盯盘与智能移动锁利守护机器人 (V3.0 无人值守静默版)
核心升级：
1. 单实例互斥锁 (Singleton PID Lock)：防止开机任务与定时任务重复双开；
2. 跨日最高水位 (High-Water Mark) 持久化记忆：隔夜低开不失忆，严格执行单向棘轮移动锁利；
3. 零黑框静默后台兼容：全面支持 pythonw.exe 无窗口运行，日志自动按日归档至 logs/ 目录，桌面气泡调用隐藏窗口不闪黑框；
4. 同花顺剪贴板静默监听：盘中复制持仓自动无感同步（老仓锁死不漂移，新仓 ATR 科学定锚）。
"""
import time
import os
import sys
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone, timedelta
import requests

BEIJING_TZ = timezone(timedelta(hours=8))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(BASE_DIR, "portfolio.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
PID_FILE = os.path.join(LOG_DIR, "monitor.pid")
LOCAL_API_PORT = 18899

os.makedirs(LOG_DIR, exist_ok=True)


class LocalRadarBridgeHandler(BaseHTTPRequestHandler):
    """本地极速重算 HTTP 桥接服务 (127.0.0.1:18899)，供桌面 HTML 报告点击【一键重算】时毫秒级响应"""

    def log_message(self, format, *args):
        """静默 HTTP 访问日志，避免污染盯盘日志"""
        pass

    def _send_cors_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_cors_json(200, {"ok": True})

    def do_GET(self):
        if self.path.startswith("/ping"):
            self._send_cors_json(200, {
                "ok": True,
                "service": "AShare_Local_Radar_Bridge",
                "time": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            self._send_cors_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path.startswith("/run-radar"):
            log_msg(f"[{datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] ⚡ 收到桌面网页【一键重算】指令，正在本地极速重算并刷新桌面报告...")
            py_exe = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
            if not os.path.exists(py_exe):
                py_exe = sys.executable
            main_script = os.path.join(BASE_DIR, "main.py")
            try:
                CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                proc = subprocess.run(
                    [py_exe, "-u", main_script, "--no-open"],
                    cwd=BASE_DIR,
                    creationflags=CREATE_NO_WINDOW,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=90
                )
                if proc.returncode == 0:
                    now_str = datetime.now(BEIJING_TZ).strftime("%Y年%m月%d日 %H:%M")
                    log_msg(f"[{datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] ✅ 本地极速重算完成！桌面《今日A股短线雷达.html》已更新至 {now_str}。")
                    self._send_cors_json(200, {
                        "ok": True,
                        "report_time": now_str,
                        "message": "本地极速重算完成，桌面报告已更新"
                    })
                else:
                    err_tail = (proc.stderr or proc.stdout or "Unknown error")[-300:]
                    log_msg(f"[错误] 本地重算返回非零状态: {err_tail}")
                    self._send_cors_json(500, {"ok": False, "error": err_tail})
            except Exception as e:
                log_msg(f"[错误] 本地重算执行异常: {e}")
                self._send_cors_json(500, {"ok": False, "error": str(e)})
        else:
            self._send_cors_json(404, {"ok": False, "error": "Not found"})


def start_local_bridge_server():
    """在后台守护线程中启动 127.0.0.1:18899 本地一键重算桥接服务"""
    try:
        server = HTTPServer(("127.0.0.1", LOCAL_API_PORT), LocalRadarBridgeHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        log_msg(f"   🌐 本地网页一键重算桥接服务已就绪: http://127.0.0.1:{LOCAL_API_PORT}/run-radar")
        return server
    except Exception as e:
        log_msg(f"   [提示] 本地桥接端口 {LOCAL_API_PORT} 已被占用或启动跳过: {e}")
        return None


def log_msg(text):
    """同时向日志文件与控制台（若存在）安全输出，完美兼容 pythonw.exe 无黑框后台模式"""
    log_file = os.path.join(LOG_DIR, f"monitor_{datetime.now(BEIJING_TZ).strftime('%Y%m%d')}.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass

    if sys.stdout is not None:
        try:
            print(text, flush=True)
        except Exception:
            pass


def is_pid_running(pid):
    """检测指定 PID 的 Python 盯盘进程是否仍在 Windows 中存活"""
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL
        ).decode('gbk', errors='ignore')
        return str(pid) in out and ("python" in out.lower())
    except Exception:
        return False


def acquire_singleton_lock(force=False):
    """获取单实例进程锁，杜绝多实例重复报警"""
    if os.path.exists(PID_FILE) and not force:
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip() or 0)
            if is_pid_running(old_pid):
                log_msg(f"[{datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] 检测到已有盯盘守护进程正在运行 (PID={old_pid})，当前实例自动退出。")
                return False
        except Exception:
            pass

    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    return True


def release_singleton_lock():
    """退出时清理自身 PID 锁"""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r", encoding="utf-8") as f:
                saved_pid = int(f.read().strip() or 0)
            if saved_pid == os.getpid():
                os.remove(PID_FILE)
    except Exception:
        pass


def get_active_holdings():
    """动态读取本地 portfolio.json 活跃持仓"""
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_active_holdings(holdings):
    """持久化更新活跃持仓（如跨日最高水位与移动止损线）到 portfolio.json"""
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(holdings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_msg(f"[提示] 持久化 portfolio.json 失败: {e}")


class RealTimeMonitor:
    def __init__(self, check_interval=15):
        self.interval = check_interval
        self.alert_history = {}
        self.session = requests.Session()
        self.session.trust_env = False
        self.headers = {'Referer': 'https://finance.sina.com.cn'}

    @staticmethod
    def is_trading_day_window():
        """判断当前是否处于工作日盯盘守候窗口 (周一至周五 09:15 ~ 15:05)"""
        now = datetime.now(BEIJING_TZ)
        if now.weekday() >= 5:
            return False
        hm = now.hour * 100 + now.minute
        return 915 <= hm <= 1505

    @staticmethod
    def is_active_polling_time():
        """判断当前是否处于盘口活跃轮询时段 (09:25~11:32 或 12:58~15:05)，午休时段自动低功耗休眠"""
        now = datetime.now(BEIJING_TZ)
        if now.weekday() >= 5:
            return False
        hm = now.hour * 100 + now.minute
        return (925 <= hm <= 1132) or (1258 <= hm <= 1505)

    def play_alert_sound(self):
        """根据配置播放轻柔提示音或保持纯静音"""
        import config
        mode = getattr(config, 'ALERT_SOUND_MODE', 'silent').lower()
        if mode == 'silent':
            return
        try:
            import winsound
            if mode == 'soft':
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
        """零黑框闪烁触发 Windows 右下角原生气泡通知"""
        self.play_alert_sound()
        try:
            clean_title = title.replace('"', '`"').replace("'", "''")
            clean_msg = message.replace('"', '`"').replace("'", "''")
            ps_cmd = (
                '[void][System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");'
                '$n = New-Object System.Windows.Forms.NotifyIcon;'
                '$n.Icon = [System.Drawing.SystemIcons]::Information;'
                '$n.BalloonTipIcon = "Warning";'
                f'$n.BalloonTipTitle = "{clean_title}";'
                f'$n.BalloonTipText = "{clean_msg}";'
                '$n.Visible = $True;'
                '$n.ShowBalloonTip(10000);'
                'Start-Sleep -Seconds 11;'
                '$n.Dispose();'
            )
            CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            log_msg(f"[提示] Windows 气泡通知发送失败: {e}")

    def send_wechat_alert(self, title, content):
        """通过本地 .env 中的 Server酱密钥热读取推送微信紧急通知"""
        import config
        sct_key = config.get_serverchan_key() if hasattr(config, 'get_serverchan_key') else getattr(config, 'SERVERCHAN_KEY', '')
        if sct_key:
            try:
                self.session.post(
                    f"https://sctapi.ftqq.com/{sct_key}.send",
                    data={'title': title, 'desp': content},
                    timeout=6
                )
            except Exception as e:
                log_msg(f"[提示] 微信推送异常: {e}")

    def check_clipboard_sync(self):
        """静默监听同花顺持仓 Ctrl+C 复制事件"""
        try:
            import sync_portfolio
            text = sync_portfolio.get_clipboard_text()
            if text and ('证券代码' in text or '股票代码' in text) and text != getattr(self, '_last_cb_text', ''):
                self._last_cb_text = text
                log_msg(f"[{datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] 📋 捕获到同花顺持仓复制事件，执行智能无漂移同步...")
                sync_portfolio.sync_now(text)
        except Exception:
            pass

    def check_portfolio(self):
        """执行单次持仓价格拉取、跨日最高水位更新与单向棘轮风控比对"""
        self.check_clipboard_sync()
        holdings = get_active_holdings()
        if not holdings:
            return

        symbols = [h['symbol'] for h in holdings if h.get('symbol')]
        if not symbols:
            return

        url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
        try:
            r = self.session.get(url, headers=self.headers, timeout=6)
            r.encoding = 'gbk'
        except Exception as e:
            log_msg(f"[{datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] 行情轮询超时: {e}")
            return

        now_str = datetime.now(BEIJING_TZ).strftime("%H:%M:%S")
        lines_out = [f"[{now_str}] 实时盘口轮询检查："]
        dirty = False

        for line in r.text.strip().split('\n'):
            if '=' not in line:
                continue
            sym = line.split('=')[0].split('_')[-1]
            data = line.split('=')[1].strip('" ;\r\n').split(',')
            if len(data) < 10 or not data[0]:
                continue

            cfg = next((h for h in holdings if h['symbol'] == sym), None)
            if not cfg:
                continue

            name = data[0]
            pre = float(data[2] or 0)
            cur = float(data[3] or 0)
            high = float(data[4] or 0)
            low = float(data[5] or 0)
            if cur <= 0 or pre <= 0:
                continue

            pct = round((cur - pre) / pre * 100, 2)
            cost = float(cfg.get('cost', 0.0))
            shares = int(cfg.get('shares', 100))
            old_stop = float(cfg.get('stop_loss', 0.0))
            take_profit = float(cfg.get('take_profit', 0.0))
            warn_pullback = float(cfg.get('warn_pullback', 2.5))
            profit_rmb = round((cur - cost) * shares, 1)

            # 更新跨日最高水位 (High-Water Mark)
            prev_highest = float(cfg.get('highest_price', 0.0))
            highest_seen = round(max(prev_highest, high, cur, cost), 2)
            if highest_seen > prev_highest + 0.01:
                cfg['highest_price'] = highest_seen
                cfg['market_price'] = cur
                dirty = True

            lines_out.append(
                f"  • {name:<5} 现价: ¥{cur:>6.2f} ({pct:+5.2f}%) | 最高水位: ¥{highest_seen:.2f} "
                f"| 防守: ¥{old_stop:.2f} | 目标: ¥{take_profit:.2f} | 浮盈: {profit_rmb:+6.1f}元"
            )

            # 0. 智能移动止损自动抬高研判 (单向棘轮，基于真实浮盈阶梯 + 跨日最高水位回撤 3%)
            gain_pct = (cur - cost) / cost * 100 if cost > 0 else 0.0
            calc_stops = [old_stop]
            if cost > 0:
                if gain_pct >= 8.0:
                    calc_stops.append(round(cost * 1.05, 2))
                elif gain_pct >= 5.0:
                    calc_stops.append(round(cost * 1.025, 2))
                elif gain_pct >= 3.0:
                    calc_stops.append(round(cost, 2))

                # 跨日最高水位脱离成本 +5% 后，启动最高水位回撤 3% 追踪锁利
                if highest_seen >= cost * 1.05:
                    calc_stops.append(round(highest_seen * 0.97, 2))

            new_stop = max(calc_stops)
            if new_stop > old_stop + 0.05 and new_stop < cur - 0.03:
                cfg['stop_loss'] = new_stop
                cfg['updated_at'] = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
                dirty = True

                title = f"🛡️【自动抬高止损】{name} 防守线已上调至 ¥{new_stop:.2f}！"
                msg = (
                    f"### 🛡️ 智能移动锁利：止损防守线已自动上调\n\n"
                    f"- **标的**：{name} ({cfg['code']})\n"
                    f"- **现价**：¥{cur:.2f} (持仓最高水位 ¥{highest_seen:.2f})\n"
                    f"- **止损保护线**：原 ¥{old_stop:.2f} ➔ **已自动上调至 ¥{new_stop:.2f}**\n\n"
                    f"💡 **锁利效果**：后台已全自动持久化新防守线（跨日不丢失）。后续若跌破 ¥{new_stop:.2f}，将立即推送微信卖出指引！"
                )
                lines_out.append(f">>> {title}")
                self.send_windows_notification(title, f"{name} 防守线已自动抬高至 ¥{new_stop:.2f} (现价 ¥{cur:.2f})")
                self.send_wechat_alert(title, msg)

            # 1. 触发止损/移动锁利防守线 (最紧急：建议卖出)
            if cfg['stop_loss'] > 0 and cur <= cfg['stop_loss']:
                alert_key = f"{sym}_stop"
                if time.time() - self.alert_history.get(alert_key, 0) > 300:
                    self.alert_history[alert_key] = time.time()
                    title = f"🚨【建议立即卖出】{name} 触碰防守线 ¥{cfg['stop_loss']:.2f}！"
                    msg = (
                        f"### 🚨 操作建议：立即执行卖出平仓\n\n"
                        f"- **标的**：{name} ({cfg['code']})\n"
                        f"- **现价**：¥{cur:.2f} (今低 ¥{low:.2f})\n"
                        f"- **触发原因**：跌破移动止损防守线 ¥{cfg['stop_loss']:.2f}\n\n"
                        f"📱 **同花顺具体委托操作指引**：\n"
                        f"1. 打开同花顺【交易】➔【持仓】找到【{name}】点【卖出】；\n"
                        f"2. 委托类型选择【市价委托】或现价卖出；\n"
                        f"3. 委托数量选择：**全部 {shares} 股**，锁定利润/保住本金！"
                    )
                    lines_out.append(f">>> {title}")
                    self.send_windows_notification(title, f"{name} 触碰防守线 ¥{cfg['stop_loss']:.2f}，建议在同花顺市价清仓！")
                    self.send_wechat_alert(title, msg)

            # 2. 触发止盈目标价 (达标落袋：建议卖出)
            elif take_profit > 0 and cur >= take_profit:
                alert_key = f"{sym}_target"
                if time.time() - self.alert_history.get(alert_key, 0) > 300:
                    self.alert_history[alert_key] = time.time()
                    title = f"🎯【止盈达标·建议卖出】{name} 已达目标价 ¥{take_profit:.2f}！"
                    if shares <= 100:
                        sell_shares = shares
                        sell_desc = "持仓仅剩 100 股底仓，建议**全部清仓落袋**锁定全部战果"
                    else:
                        sell_shares = max(100, (shares // 200) * 100)
                        sell_desc = f"建议**先卖出一半 ({sell_shares} 股)**锁定利润，剩余底仓靠移动止损继续奔跑"

                    msg = (
                        f"### 🎯 操作建议：达到止盈目标，落袋为安\n\n"
                        f"- **标的**：{name} ({cfg['code']})\n"
                        f"- **现价**：¥{cur:.2f} (已达目标价 ¥{take_profit:.2f})\n"
                        f"- **策略指引**：{sell_desc}\n\n"
                        f"📱 **同花顺具体委托操作指引**：\n"
                        f"1. 打开同花顺【交易】➔【持仓】选择【{name}】点击【卖出】；\n"
                        f"2. 建议委托数量：**{sell_shares} 股**；\n"
                        f"3. 卖出成交后按 Ctrl+C 复制持仓即可自动更新剩余股数！"
                    )
                    lines_out.append(f">>> {title}")
                    self.send_windows_notification(title, f"{name} 已达目标价 ¥{take_profit:.2f}，建议卖出 {sell_shares} 股锁定利润！")
                    self.send_wechat_alert(title, msg)

            # 3. 盘中冲高大幅回撤预警
            elif cost > 0 and high > cost * 1.02 and (high - cur) / high * 100 >= warn_pullback:
                alert_key = f"{sym}_pullback"
                if time.time() - self.alert_history.get(alert_key, 0) > 900:  # 15分钟防刷屏
                    self.alert_history[alert_key] = time.time()
                    pull_pct = round((high - cur) / high * 100, 1)
                    title = f"⚠️【冲高回落预警】{name} 距今日高点回撤 {pull_pct}%"
                    msg = (
                        f"### ⚠️ 技术面走弱预警：日内冲高回落\n\n"
                        f"- **标的**：{name} ({cfg['code']})\n"
                        f"- **今日最高**：¥{high:.2f} ➔ **现价**：¥{cur:.2f} (回撤 {pull_pct}%)\n"
                        f"- **当前防守底线**：¥{cfg['stop_loss']:.2f}\n"
                        f"- **应对策略**：关注分时均线承接，若跌破 ¥{cfg['stop_loss']:.2f} 将触发卖出警报。"
                    )
                    lines_out.append(f">>> {title}")
                    self.send_windows_notification(title, f"{name} 冲高 ¥{high:.2f} 后回撤 {pull_pct}%，留意防守线 ¥{cfg['stop_loss']:.2f}！")
                    self.send_wechat_alert(title, msg)

        if dirty:
            save_active_holdings(holdings)

        log_msg("\n".join(lines_out))

    def run_forever(self, auto_exit_at_close=True, force_lock=False):
        now = datetime.now(BEIJING_TZ)
        if auto_exit_at_close and not self.is_trading_day_window():
            log_msg(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 当前为非交易日或已过 15:05 收盘时间，静默守护无需驻留，安全退出。")
            return

        if not acquire_singleton_lock(force=force_lock):
            return

        try:
            holdings = get_active_holdings()
            names = ", ".join([h['name'] for h in holdings]) if holdings else "暂无持仓(监听剪贴板中)"
            log_msg("=" * 68)
            log_msg(f"   🤖 A股持仓实盘毫秒级盯盘机器人 V3.0 启动 (PID={os.getpid()})")
            log_msg(f"   监控标的: {names} | 轮询间隔: {self.interval}s")
            start_local_bridge_server()
            log_msg("=" * 68)

            while True:
                now = datetime.now(BEIJING_TZ)
                if auto_exit_at_close and (now.weekday() >= 5 or now.hour > 15 or (now.hour == 15 and now.minute >= 5)):
                    log_msg(f"[{now.strftime('%H:%M:%S')}] 今日 A股 交易已收盘，盯盘守护进程安全退出。")
                    break

                if self.is_active_polling_time():
                    self.check_portfolio()
                    time.sleep(self.interval)
                else:
                    # 盘前等待 (09:15~09:25) 或午间休市 (11:32~12:58) 仅低频监听剪贴板，不刷行情接口
                    self.check_clipboard_sync()
                    time.sleep(20)
        except KeyboardInterrupt:
            log_msg("[退出] 盯盘服务已手动停止。")
        finally:
            release_singleton_lock()


if __name__ == '__main__':
    force_flag = '--force' in sys.argv
    monitor = RealTimeMonitor(check_interval=15)
    monitor.run_forever(auto_exit_at_close=True, force_lock=force_flag)
