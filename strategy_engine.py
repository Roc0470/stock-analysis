# -*- coding: utf-8 -*-
"""
A股短线爆发与趋势跟踪量化策略引擎 (V3.0 全自动实战闭环版)
核心升级：
1. 盘中动态换手与实时 K 线对齐建模；
2. 大盘冰点空仓熔断器（四大指数共振大跌时强制阻断追高买新）；
3. 现有持仓健康度与去留诊断引擎（均线支撑、MACD动量、防守距离一站式体检）；
4. 新股首次同步 ATR(14) 科学初始止盈止损定锚器。
"""
import pandas as pd
import numpy as np
import config


class ShortTermTrendStrategy:
    def __init__(self):
        pass

    @staticmethod
    def calculate_technical_indicators(df):
        """计算核心技术指标：均线系统、动态量比、ATR真实波幅、MACD、RSI等"""
        if df is None or len(df) < 25:
            return None

        df = df.copy()
        # 1. 均线系统 (MA5, MA10, MA20, MA60)
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean() if len(df) >= 60 else df['ma20']

        # 2. 成交量均线与动态量比 (当日预计全天量 vs 过去5日真实均量)
        df['vol_ma5_prev'] = df['volume'].shift(1).rolling(5).mean()
        df['vol_ratio'] = df['volume'] / (df['vol_ma5_prev'] + 1e-6)

        # 3. 过去20日最高价（不含今日，用于判断今日是否突破前期箱体）
        df['high_20_prev'] = df['high'].shift(1).rolling(20).max()
        df['high_20'] = df['high'].rolling(20).max()

        # 4. ATR (14日平均真实波幅)
        prev_close = df['close'].shift(1)
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - prev_close).abs()
        tr3 = (df['low'] - prev_close).abs()
        df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr14'] = df['tr'].rolling(14).mean()

        # 5. MACD 指标 (12, 26, 9)
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['dif'] = exp12 - exp26
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd_bar'] = (df['dif'] - df['dea']) * 2

        # 6. RSI 强弱指标 (6日)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=6).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=6).mean()
        rs = gain / (loss + 1e-6)
        df['rsi_6'] = 100 - (100 / (1 + rs))

        return df

    @staticmethod
    def check_market_circuit_breaker(indices):
        """
        大盘冰点空仓熔断判定：
        当核心指数集体杀跌（全部绿盘且均幅 <= -1.2%，或至少3大指数跌幅 <= -1.2%）时，
        强制触发空仓保护熔断，严禁当日逆势开新仓。
        """
        if not indices:
            return False, ""
        threshold = getattr(config, 'CIRCUIT_BREAKER_DROP_PCT', -1.2)
        down_all = all(idx['change_pct'] < 0 for idx in indices)
        avg_pct = sum(idx['change_pct'] for idx in indices) / len(indices)
        heavy_drop_cnt = sum(1 for idx in indices if idx['change_pct'] <= threshold)

        if (down_all and avg_pct <= threshold) or heavy_drop_cnt >= 3:
            reason = f"四大指数集体杀跌（平均跌幅 {avg_pct:.2f}%，{heavy_drop_cnt} 大指数跌超 {abs(threshold)}%），触发系统级【冰点空仓保护熔断】！今日严禁开新仓接飞刀。"
            return True, reason
        return False, ""

    @classmethod
    def calc_initial_atr_stops(cls, df_kline, cost, market_p):
        """
        为同花顺首次新同步入库的持仓科学测算初始 ATR 止盈与止损位（仅在首次入库时定锚一次）
        """
        anchor = market_p if market_p > 0 else cost
        if anchor <= 0:
            return round(cost * 0.952, 2), round(cost * 1.08, 2)

        df = cls.calculate_technical_indicators(df_kline) if df_kline is not None else None
        if df is not None and len(df) >= 20:
            curr = df.iloc[-1]
            atr = float(curr['atr14']) if not np.isnan(curr['atr14']) else anchor * 0.03
            ma10 = float(curr['ma10']) if not np.isnan(curr['ma10']) else anchor * 0.96
            ma20 = float(curr['ma20']) if not np.isnan(curr['ma20']) else anchor * 0.95

            if cost > 0 and market_p >= cost * 1.05:
                # 若同步时已有 5%+ 浮盈（或摊薄成本），设利润保护线
                stop_loss = round(max(cost, market_p * 0.97, market_p - 1.2 * atr), 2)
            elif cost > 0 and market_p >= cost * 1.03:
                stop_loss = round(cost, 2)
            else:
                base_c = cost if cost > 0 else anchor
                raw_stop = min(anchor - 1.5 * atr, max(ma10 * 0.99, ma20 * 0.995))
                stop_loss = round(float(np.clip(raw_stop, base_c * 0.952, base_c * 0.974)), 2)

            take_profit = round(max(anchor + 2.4 * atr, max(cost, anchor) * 1.065), 2)
            return stop_loss, take_profit

        # 兜底计算（无K线时）
        if cost > 0 and market_p >= cost * 1.03:
            stop_loss = round(max(cost, market_p * 0.97), 2)
        else:
            stop_loss = round((cost if cost > 0 else anchor) * 0.952, 2)
        take_profit = round(max(cost * 1.08, anchor * 1.065), 2)
        return stop_loss, take_profit

    @classmethod
    def diagnose_holding(cls, holding, quote, df_kline):
        """
        对用户现有持仓股票进行技术面与风控去留体检
        """
        code = holding['code']
        name = holding['name']
        shares = holding.get('shares', 100)
        cost = holding.get('cost', 0.0)
        stop_loss = holding.get('stop_loss', 0.0)
        take_profit = holding.get('take_profit', 0.0)
        highest_price = holding.get('highest_price', 0.0)

        price = quote['price'] if quote else holding.get('market_price', cost)
        change_pct = quote['change_pct'] if quote else 0.0
        high_today = quote['high'] if quote else price
        low_today = quote['low'] if quote else price
        highest_seen = max(highest_price, high_today, price)

        profit_rmb = round((price - cost) * shares, 1) if cost > 0 else 0.0
        profit_pct = round((price - cost) / cost * 100, 2) if cost > 0 else 0.0
        dist_to_stop_pct = round((price - stop_loss) / price * 100, 2) if price > 0 and stop_loss > 0 else 0.0
        dist_to_target_pct = round((take_profit - price) / price * 100, 2) if price > 0 and take_profit > 0 else 0.0

        df = cls.calculate_technical_indicators(df_kline) if df_kline is not None else None
        ma5, ma20, macd_bull = None, None, True
        if df is not None and len(df) >= 20:
            curr = df.iloc[-1]
            ma5 = round(float(curr['ma5']), 2)
            ma20 = round(float(curr['ma20']), 2)
            macd_bull = bool(curr['dif'] >= curr['dea'])

        # 综合状态与操作建议判定
        if stop_loss > 0 and price <= stop_loss:
            badge = "🚨 破位警报 · 建议清仓"
            level = "danger"
            advice = f"现价 ¥{price:.2f} 已跌破移动止损防守线 ¥{stop_loss:.2f}！请严格执行纪律，在同花顺市价清仓全部 {shares} 股。"
        elif take_profit > 0 and price >= take_profit:
            badge = "🎯 止盈达标 · 落袋为安"
            level = "target"
            act = f"全部清仓 {shares} 股锁定战果" if shares <= 100 else f"先卖出一半 ({(shares // 200) * 100} 股) 锁定利润"
            advice = f"现价 ¥{price:.2f} 已触及目标价 ¥{take_profit:.2f}！建议{act}。"
        elif ma20 and price < ma20:
            badge = "⚠️ 跌破20日线 · 严密防守"
            level = "warn"
            advice = f"股价已滑落至20日生命线(¥{ma20:.2f})下方，趋势转弱；死守止损红线 ¥{stop_loss:.2f}，反抽无力建议逢高减仓。"
        elif ma5 and price >= ma5 and macd_bull:
            badge = "🔥 多头强势 · 安心让利润奔跑"
            level = "strong"
            rem_tip = "（100股纯利润底仓）" if shares <= 100 else ""
            advice = f"稳站5日线(¥{ma5:.2f})之上且MACD多头{rem_tip}，趋势健康！继续持股待涨看齐 ¥{take_profit:.2f}，防守底线严锁 ¥{stop_loss:.2f}。"
        else:
            badge = "🛡️ 良性震荡 · 持仓观察"
            level = "normal"
            ma_info = f"5日线 ¥{ma5:.2f} / 20日线 ¥{ma20:.2f}" if ma5 and ma20 else "短期均线附近"
            advice = f"围绕 {ma_info} 正常震荡换手，未破防守线 ¥{stop_loss:.2f} 前无需恐慌，耐心持有。"

        return {
            'code': code,
            'name': name,
            'shares': shares,
            'cost': cost,
            'price': price,
            'change_pct': change_pct,
            'profit_rmb': profit_rmb,
            'profit_pct': profit_pct,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'highest_price': round(highest_seen, 2),
            'dist_to_stop_pct': dist_to_stop_pct,
            'dist_to_target_pct': dist_to_target_pct,
            'ma5': ma5,
            'ma20': ma20,
            'badge': badge,
            'level': level,
            'advice': advice
        }

    def evaluate_stock(self, stock_info, df_kline, holdings_count=0, is_circuit_breaker=False):
        """
        对单只股票进行 V3.0 严选多因子评分与 ATR 动态买卖点测算（结合实时仓位与大盘熔断状态）
        """
        df = self.calculate_technical_indicators(df_kline)
        if df is None:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev5 = df.iloc[-6] if len(df) >= 6 else df.iloc[0]

        close = stock_info['price']
        open_p = stock_info.get('open', curr['open'])
        high_p = stock_info.get('high', curr['high'])
        low_p = stock_info.get('low', curr['low'])
        turnover_pct = stock_info.get('turnover_pct', 3.0)
        eff_turnover = stock_info.get('projected_turnover_pct', turnover_pct)
        upper_shadow_pct = stock_info.get('upper_shadow_pct', 0.5)

        ma5 = curr['ma5']
        ma10 = curr['ma10']
        ma20 = curr['ma20']
        vol_ratio = curr['vol_ratio']
        atr = curr['atr14'] if not np.isnan(curr['atr14']) else close * 0.03
        dif = curr['dif']
        dea = curr['dea']
        macd_bar = curr['macd_bar']
        rsi = curr['rsi_6']
        high_20_prev = curr['high_20_prev'] if not np.isnan(curr['high_20_prev']) else curr['high_20']

        # ================= 第二层：趋势与位置硬性排雷 =================
        if close < ma20 or close < ma5:
            return None

        ma20_rising = ma20 >= prev5['ma20'] * 0.992
        strong_turnaround = (ma5 > prev['ma5']) and (close > ma20 * 1.015) and (vol_ratio >= 1.3)
        if not (ma20_rising or strong_turnaround):
            return None

        gain_5d = (close - prev5['close']) / prev5['close'] * 100
        bias_20 = (close - ma20) / ma20 * 100
        if gain_5d > 22.0 or bias_20 > 15.5:
            return None

        # ================= 第三层：多因子连续评分模型 (满分 100) =================
        score = 42.0
        reasons = []
        tags = []

        # 【因子 1：均线趋势与排列强度 (满分 18 分)】
        if close > ma5 > ma10 > ma20:
            score += 12.0
            tags.append("均线多头")
            if 1.5 <= bias_20 <= 9.0:
                score += 6.0 - abs(bias_20 - 5.0) * 0.35
                reasons.append(f"5/10/20日均线标准多头排列，距20日线 +{bias_20:.1f}%，处于安全主升通道")
            else:
                score += 3.5
                reasons.append("短中期均线多头排列，上升通道保持完整")
        elif close > ma5 and close > ma20:
            score += 9.0 + min(4.5, max(0.0, 4.5 - abs(bias_20 - 4.5) * 0.4))
            tags.append("突破生命线")
            reasons.append(f"股价强势站稳5日与20日生命线之上（乖离率 +{bias_20:.1f}%），底部右侧转势确立")

        # 【因子 2：动态量价配合与换手活跃度 (满分 16 分)】
        if 1.25 <= vol_ratio <= 2.8:
            vol_score = 9.0 - abs(vol_ratio - 1.85) * 1.2
            score += max(6.0, vol_score)
            tags.append("主力倍量进攻")
            reasons.append(f"动态量比 {vol_ratio:.2f} 倍，温和倍量放大，主力增量资金进场明显")
        elif vol_ratio > 2.8:
            score += 5.5
            tags.append("放量突破")
            reasons.append(f"动态量比达 {vol_ratio:.2f} 倍，资金交投高度活跃")
        else:
            score += max(2.5, vol_ratio * 4.5)

        if 3.0 <= eff_turnover <= 14.0:
            turn_score = 7.0 - abs(eff_turnover - 6.5) * 0.25
            score += max(4.5, turn_score)
            tags.append(f"换手{turnover_pct}%")
            reasons.append(f"当前换手率 {turnover_pct}%（预计全天 {eff_turnover}%）处于黄金活跃区间，筹码锁定良好")
        else:
            score += 3.8

        # 【因子 3：K线日内质量与突破形态 (满分 14 分)】
        day_range = max(0.01, high_p - low_p)
        close_pos = (close - low_p) / day_range
        kline_quality = close_pos * 7.5 - upper_shadow_pct * 0.8
        score += max(2.5, min(7.5, kline_quality))
        if upper_shadow_pct <= 0.9 and close > open_p * 1.012:
            tags.append("饱满真阳线")
            reasons.append(f"日内收出饱满实体真阳线（上影线仅 {upper_shadow_pct}%），资金承接有力")

        dist_to_high = (close - high_20_prev) / high_20_prev * 100
        if -2.0 <= dist_to_high <= 3.5:
            score += 6.5 - abs(dist_to_high - 0.5) * 0.5
            tags.append("箱体突破")
            reasons.append("股价临近或已突破近20日震荡箱体高点，上方套牢盘阻力极轻")
        elif -7.0 <= dist_to_high < -2.0:
            score += 4.2
            reasons.append("股价在箱体中上部蓄势推进，具备向上挑战前高的动能")
        else:
            score += 2.8

        # 【因子 4：MACD 与 RSI 动量共振 (满分 10 分)】
        if dif > dea:
            score += 4.0
            if macd_bar > prev['macd_bar']:
                score += 2.5
                tags.append("MACD金叉加速")
                reasons.append("MACD处于金叉多头状态且红柱持续放大，上涨动量充沛")
        elif dif > prev['dif']:
            score += 2.5

        if 52 <= rsi <= 74:
            rsi_score = 3.5 - abs(rsi - 63.0) * 0.1
            score += max(2.0, rsi_score)
        else:
            score += 1.5

        score = round(min(max(score, 65.0), 96.8), 1)

        # ================= 第四层：ATR 动态买卖点与仓位联动精算 =================
        buy_low = round(max(ma5 * 0.998, close - 0.55 * atr, close * 0.978), 2)
        buy_high = round(close, 2)
        if buy_low >= buy_high:
            buy_low = round(close * 0.985, 2)

        atr_stop = close - 1.5 * atr
        support_stop = max(ma10 * 0.99, ma20 * 0.995)
        raw_stop = min(atr_stop, support_stop)
        stop_loss_price = round(float(np.clip(raw_stop, close * 0.952, close * 0.974)), 2)
        stop_loss_pct = round((stop_loss_price - close) / close * 100, 1)

        atr_target = close + 2.4 * atr
        min_required_target = close * (1 + abs(stop_loss_pct) / 100 * 1.75)
        target_price = round(max(atr_target, min_required_target, close * 1.065), 2)
        target_pct = round((target_price - close) / close * 100, 1)

        risk_reward_ratio = round(target_pct / (abs(stop_loss_pct) + 1e-6), 1)
        if risk_reward_ratio < config.MIN_RISK_REWARD:
            return None

        budget_target = config.TOTAL_CAPITAL * config.DEFAULT_POS_RATIO
        suggest_lots = max(1, int(budget_target / (close * 100)))
        suggest_shares = suggest_lots * 100
        suggest_cost = round(suggest_shares * close, 2)
        actual_pos_pct = round(suggest_cost / config.TOTAL_CAPITAL * 100, 1)

        expected_profit_rmb = int(round((target_price - close) * suggest_shares))
        max_loss_rmb = int(round((close - stop_loss_price) * suggest_shares))

        if is_circuit_breaker:
            suggest_pos_desc = "❄️ 【大盘冰点熔断】今日强制空仓保护，仅作强势股复盘观察，严禁开新仓！"
        elif holdings_count >= config.MAX_HOLDINGS:
            suggest_pos_desc = f"⚠️ 【已满 {config.MAX_HOLDINGS} 只持仓上限】仅作备选观察，除非先清仓旧股，否则不开新仓！"
        else:
            suggest_pos_desc = (
                f"买 {suggest_shares}股 ({suggest_lots}手) · 约 ¥{suggest_cost:,.0f} (占本金 {actual_pos_pct}%) "
                f"| 达标预计赚 +¥{expected_profit_rmb} / 止损最多亏 -¥{max_loss_rmb}"
            )

        recent_closes = [round(c, 2) for c in df['close'].tail(15).tolist()]

        return {
            'symbol': stock_info['symbol'],
            'code': stock_info['code'],
            'name': stock_info['name'],
            'price': close,
            'change_pct': stock_info['change_pct'],
            'amount_yi': stock_info['amount_yi'],
            'turnover_pct': turnover_pct,
            'nmc_yi': stock_info.get('nmc_yi', 0),
            'vol_ratio': round(vol_ratio, 2),
            'atr_pct': round(atr / close * 100, 2),
            'score': score,
            'tags': tags[:4],
            'reasons': reasons,
            'buy_range': f"{buy_low:.2f} ~ {buy_high:.2f}",
            'target_price': target_price,
            'target_pct': target_pct,
            'stop_loss_price': stop_loss_price,
            'stop_loss_pct': stop_loss_pct,
            'risk_reward_ratio': risk_reward_ratio,
            'suggest_shares': suggest_shares,
            'suggest_lots': suggest_lots,
            'suggest_cost': suggest_cost,
            'expected_profit_rmb': expected_profit_rmb,
            'max_loss_rmb': max_loss_rmb,
            'suggest_pos': suggest_pos_desc,
            'recent_closes': recent_closes
        }
