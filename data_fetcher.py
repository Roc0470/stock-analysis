# -*- coding: utf-8 -*-
"""
A股市场行情与技术数据获取模块 (V3.0 实战闭环版)
支持：
1. 盘中动态时间进度折算（解决早盘/盘中扫描成交额与量比严重偏低误杀好票的问题）
2. 实时行情 Bar 自动拼接历史日K线（解决新浪日K接口盘中不包含当日实时K线的底层盲区）
3. 批量持仓实时快照抓取（供持仓健康度诊断与首次买入 ATR 科学定锚使用）
"""
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import config

BEIJING_TZ = timezone(timedelta(hours=8))


class AShareDataFetcher:
    def __init__(self):
        self.session = requests.Session()
        # 禁用系统代理环境干扰，直连国内金融数据源
        self.session.trust_env = False
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn/'
        }

    @staticmethod
    def get_intraday_progress_ratio():
        """
        计算当前盘中交易时间进度折算系数 (0.22 ~ 1.0)
        用于动态校准盘中未收盘时的成交额门槛与全天预计成交量（动态量比）。
        非交易日、盘前(<09:30)或收盘后(>=15:00)均返回 1.0。
        """
        now = datetime.now(BEIJING_TZ)
        if now.weekday() >= 5:
            return 1.0
        hm = now.hour * 60 + now.minute
        open_am = 9 * 60 + 30    # 09:30
        close_am = 11 * 60 + 30  # 11:30
        open_pm = 13 * 60        # 13:00
        close_pm = 15 * 60       # 15:00

        if hm < open_am or hm >= close_pm:
            return 1.0
        elif hm <= close_am:
            elapsed = hm - open_am
        elif hm < open_pm:
            elapsed = 120  # 午间休市已完成半天 120 分钟
        else:
            elapsed = 120 + (hm - open_pm)

        # A股早盘前半小时交投最密集，适度赋予 1.18 倍早盘活跃权重，下限保底 0.22
        raw_ratio = (elapsed / 240.0) * 1.18
        return round(min(1.0, max(0.22, raw_ratio)), 3)

    def get_market_indices(self):
        """获取大盘主要指数行情（上证、深证、创业板、科创50）"""
        symbols = ['s_sh000001', 's_sz399001', 's_sz399006', 's_sh000688']
        url = f"http://qt.gtimg.cn/q={','.join(symbols)}"
        indices = []
        try:
            r = self.session.get(url, headers=self.headers, timeout=5)
            lines = r.content.decode('gbk', errors='ignore').strip().split(';')
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split('~')
                if len(parts) >= 8:
                    name = parts[1]
                    code = parts[2]
                    point = float(parts[3])
                    change_amount = float(parts[4])
                    change_pct = float(parts[5])
                    amount_yi = round(float(parts[7]) / 10000, 1)  # 腾讯接口单位是万元，转为亿元
                    indices.append({
                        'code': code,
                        'name': name,
                        'point': point,
                        'change_amount': change_amount,
                        'change_pct': change_pct,
                        'amount_yi': amount_yi
                    })
        except Exception as e:
            print(f"[警告] 获取大盘指数失败: {e}")
        return indices

    def get_realtime_quotes(self, symbols):
        """批量拉取指定股票代码的实时盘口快照"""
        if not symbols:
            return {}
        progress = self.get_intraday_progress_ratio()
        url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
        result = {}
        try:
            r = self.session.get(url, headers=self.headers, timeout=6)
            r.encoding = 'gbk'
            for line in r.text.strip().split('\n'):
                if '=' not in line:
                    continue
                sym = line.split('=')[0].split('_')[-1]
                data = line.split('=')[1].strip('" ;\r\n').split(',')
                if len(data) < 31 or not data[0]:
                    continue
                name = data[0]
                open_p = float(data[1] or 0)
                prev_close = float(data[2] or 0)
                cur = float(data[3] or 0)
                high_p = float(data[4] or 0)
                low_p = float(data[5] or 0)
                vol = float(data[8] or 0)
                amount = float(data[9] or 0)
                date_str = data[30] if len(data) > 30 and data[30] else datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
                if cur <= 0 and prev_close > 0:
                    cur = prev_close
                pct = round((cur - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
                result[sym] = {
                    'symbol': sym,
                    'code': sym[-6:],
                    'name': name,
                    'price': cur,
                    'open': open_p if open_p > 0 else cur,
                    'high': high_p if high_p > 0 else cur,
                    'low': low_p if low_p > 0 else cur,
                    'prev_close': prev_close,
                    'volume': vol,
                    'projected_volume': round(vol / progress, 0),
                    'amount_yi': round(amount / 1e8, 2),
                    'change_pct': pct,
                    'date': date_str
                }
        except Exception as e:
            print(f"[警告] 获取实时快照失败: {e}")
        return result

    def get_active_stocks_pool(self, count=400):
        """
        分页扫描全市场成交额靠前的活跃个股池，并执行第一层【新手风控与防诱多初筛】（支持盘中动态时间折算）
        """
        page_size = 80
        pages = max(1, (count + page_size - 1) // page_size)
        raw_stocks = []

        for page in range(1, pages + 1):
            url = f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num={page_size}&sort=amount&asc=0&node=hs_a&symbol="
            try:
                r = self.session.get(url, headers=self.headers, timeout=8)
                batch = r.json()
                if batch:
                    raw_stocks.extend(batch)
            except Exception as e:
                print(f"[警告] 获取第 {page} 页活跃股票池失败: {e}")

        progress = self.get_intraday_progress_ratio()
        min_amount_dynamic = round(config.MIN_AMOUNT_YI * progress, 2)
        min_turnover_dynamic = round(config.MIN_TURNOVER_PCT * progress, 2)
        today_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

        active_stocks = []
        stats = {
            'total_scanned': len(raw_stocks),
            'filtered_board': 0,
            'filtered_price': 0,
            'filtered_trap_kline': 0,
            'filtered_turnover': 0,
            'progress_ratio': progress,
            'min_amount_used': min_amount_dynamic
        }

        for st in raw_stocks:
            symbol = st['symbol']
            code = st['code']
            name = st['name']

            # 1. 过滤 ST 和退市风险股
            if 'ST' in name or '*ST' in name or '退' in name:
                continue

            # 2. 板块权限过滤：新手默认只选沪深主板
            if config.ONLY_MAIN_BOARD:
                if not code.startswith(('600', '601', '603', '605', '000', '001', '002', '003')):
                    stats['filtered_board'] += 1
                    continue
            else:
                if code.startswith(('8', '4', '92', '200', '900')):
                    stats['filtered_board'] += 1
                    continue

            trade = float(st.get('trade', 0) or 0)
            open_p = float(st.get('open', 0) or 0)
            high_p = float(st.get('high', 0) or 0)
            low_p = float(st.get('low', 0) or 0)
            vol = float(st.get('volume', 0) or 0)
            if trade <= 0 or open_p <= 0:
                continue

            # 3. 过滤股价区间 (3.5 ~ 35.0 元)
            if not (config.MIN_STOCK_PRICE <= trade <= config.MAX_STOCK_PRICE):
                stats['filtered_price'] += 1
                continue

            change_pct = float(st.get('changepercent', 0) or 0)
            amount_yi = round(float(st.get('amount', 0) or 0) / 1e8, 2)
            turnover_pct = round(float(st.get('turnoverratio', 0) or 0), 2)
            nmc_yi = round(float(st.get('nmc', 0) or 0) / 10000, 1)
            pe_ratio = round(float(st.get('per', 0) or 0), 1)

            if amount_yi < min_amount_dynamic:
                continue

            # 4. 换手率过滤（下限支持盘中折算，上限严守 22% 防死亡换手）
            if not (min_turnover_dynamic <= turnover_pct <= config.MAX_TURNOVER_PCT):
                stats['filtered_turnover'] += 1
                continue

            # 5. 日内K线形态防诱多过滤
            if not (config.MIN_DAILY_CHANGE <= change_pct <= config.MAX_DAILY_CHANGE):
                stats['filtered_trap_kline'] += 1
                continue
            if trade < open_p:
                stats['filtered_trap_kline'] += 1
                continue
            upper_shadow_pct = (high_p - trade) / trade * 100
            if upper_shadow_pct > config.MAX_UPPER_SHADOW:
                stats['filtered_trap_kline'] += 1
                continue
            if high_p > low_p and (trade - low_p) / (high_p - low_p) < 0.55:
                stats['filtered_trap_kline'] += 1
                continue

            active_stocks.append({
                'symbol': symbol,
                'code': code,
                'name': name,
                'price': trade,
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'volume': vol,
                'projected_volume': round(vol / progress, 0),
                'date': today_str,
                'change_pct': change_pct,
                'amount_yi': amount_yi,
                'turnover_pct': turnover_pct,
                'projected_turnover_pct': round(turnover_pct / progress, 2),
                'nmc_yi': nmc_yi,
                'pe_ratio': pe_ratio,
                'upper_shadow_pct': round(upper_shadow_pct, 2)
            })

        return active_stocks, stats

    def get_stock_kline(self, symbol, days=60, realtime_bar=None):
        """
        获取单只股票的日K线数据，并在盘中未收盘时自动拼接当日实时行情 Bar
        """
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
        try:
            r = self.session.get(url, headers={'Referer': 'https://finance.sina.com.cn/'}, timeout=6)
            k_list = r.json()
            if not k_list or len(k_list) < 25:
                return None

            records = []
            for item in k_list:
                records.append({
                    'date': item['day'],
                    'open': float(item['open']),
                    'close': float(item['close']),
                    'high': float(item['high']),
                    'low': float(item['low']),
                    'volume': float(item['volume'])
                })

            # 若传入了当日实时行情且新浪历史接口尚未生成今日收盘K线，则无缝拼接今日实时Bar
            if realtime_bar and realtime_bar.get('price', 0) > 0:
                rt_date = realtime_bar.get('date')
                # 仅在工作日或实时成交量 > 0 且日期晚于最后一条历史K线时追加
                if rt_date and records[-1]['date'] < rt_date and realtime_bar.get('volume', 0) > 0:
                    records.append({
                        'date': rt_date,
                        'open': float(realtime_bar.get('open', realtime_bar['price'])),
                        'close': float(realtime_bar['price']),
                        'high': float(realtime_bar.get('high', realtime_bar['price'])),
                        'low': float(realtime_bar.get('low', realtime_bar['price'])),
                        'volume': float(realtime_bar.get('projected_volume') or realtime_bar.get('volume', 0))
                    })
                elif rt_date and records[-1]['date'] == rt_date:
                    # 若已包含当日K线则用最新实时价更新末尾行
                    records[-1]['close'] = float(realtime_bar['price'])
                    records[-1]['high'] = max(records[-1]['high'], float(realtime_bar.get('high', realtime_bar['price'])))
                    records[-1]['low'] = min(records[-1]['low'], float(realtime_bar.get('low', realtime_bar['price'])))
                    records[-1]['volume'] = float(realtime_bar.get('projected_volume') or realtime_bar.get('volume', records[-1]['volume']))

            return pd.DataFrame(records)
        except Exception:
            return None
