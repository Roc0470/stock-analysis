# -*- coding: utf-8 -*-
"""
A股市场行情与技术数据获取模块 (V2.0 实战严选版)
支持多页全市场高流动性扫描、主板权限过滤、换手率与日内防诱多初筛
"""
import requests
import pandas as pd
import numpy as np
import config

class AShareDataFetcher:
    def __init__(self):
        self.session = requests.Session()
        # 禁用系统代理环境干扰，直连国内金融数据源
        self.session.trust_env = False
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn/'
        }

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

    def get_active_stocks_pool(self, count=400):
        """
        分页扫描全市场成交额靠前的活跃个股池，并执行第一层【新手风控与防诱多初筛】：
        1. 剔除 ST/*ST/退市风险股；
        2. 严格匹配新手交易权限：仅保留沪深主板(600/601/603/605/000/001/002/003)，剔除创业板(300)、科创板(688)、北交所；
        3. 股价区间过滤 (3.5 ~ 35.0 元)，适配 21,000 元总资金；
        4. 换手率过滤 (1.2% ~ 22.0%)，剔除死水银行巨无霸与高位 40%+ 死亡换手出货股；
        5. 日内K线排雷：剔除“高开低走假阳线/大阴线”与“长上影线避雷针”诱多股。
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

        active_stocks = []
        stats = {
            'total_scanned': len(raw_stocks),
            'filtered_board': 0,
            'filtered_price': 0,
            'filtered_trap_kline': 0,
            'filtered_turnover': 0
        }

        for st in raw_stocks:
            symbol = st['symbol']
            code = st['code']
            name = st['name']

            # 1. 过滤 ST 和退市风险股
            if 'ST' in name or '*ST' in name or '退' in name:
                continue

            # 2. 板块权限过滤：新手默认只选沪深主板，剔除 300/301(创业板)、688(科创板)、8/4/92(北交所)
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
            if trade <= 0 or open_p <= 0:
                continue

            # 3. 过滤股价区间 (3.5 ~ 35.0 元)
            if not (config.MIN_STOCK_PRICE <= trade <= config.MAX_STOCK_PRICE):
                stats['filtered_price'] += 1
                continue

            change_pct = float(st.get('changepercent', 0) or 0)
            amount_yi = round(float(st.get('amount', 0) or 0) / 1e8, 2)
            turnover_pct = round(float(st.get('turnoverratio', 0) or 0), 2)
            nmc_yi = round(float(st.get('nmc', 0) or 0) / 10000, 1)  # 流通市值(亿元)
            pe_ratio = round(float(st.get('per', 0) or 0), 1)

            if amount_yi < config.MIN_AMOUNT_YI:
                continue

            # 4. 换手率过滤：剔除死水巨无霸 (<1.2%) 与高位死亡换手股 (>22%)
            if not (config.MIN_TURNOVER_PCT <= turnover_pct <= config.MAX_TURNOVER_PCT):
                stats['filtered_turnover'] += 1
                continue

            # 5. 日内K线形态防诱多过滤 (核心升级！)
            # (a) 当日涨幅必须在温和走强区间 (0.5% ~ 8.0%)
            if not (config.MIN_DAILY_CHANGE <= change_pct <= config.MAX_DAILY_CHANGE):
                stats['filtered_trap_kline'] += 1
                continue
            # (b) 必须是日内真阳线 (收盘价 >= 开盘价)，彻底杜绝“高开低走瀑布假红盘”(如天娱数科开盘8.83跌到8.15)
            if trade < open_p:
                stats['filtered_trap_kline'] += 1
                continue
            # (c) 拒绝长上影线“避雷针”图形 (上影线 <= 2.8%)
            upper_shadow_pct = (high_p - trade) / trade * 100
            if upper_shadow_pct > config.MAX_UPPER_SHADOW:
                stats['filtered_trap_kline'] += 1
                continue
            # (d) 收盘价必须位于全天波动的上半区，确认为尾盘资金承接有力
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
                'change_pct': change_pct,
                'amount_yi': amount_yi,
                'turnover_pct': turnover_pct,
                'nmc_yi': nmc_yi,
                'pe_ratio': pe_ratio,
                'upper_shadow_pct': round(upper_shadow_pct, 2)
            })

        return active_stocks, stats

    def get_stock_kline(self, symbol, days=60):
        """
        获取单只股票的日K线数据（新浪财经官方接口，高稳定无阻断）
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
            df = pd.DataFrame(records)
            return df
        except Exception:
            return None
