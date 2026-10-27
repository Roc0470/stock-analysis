# -*- coding: utf-8 -*-
"""
A股每日量化选股与买卖时机可视化报告生成器
生成独立、直观、高颜值的交互式 HTML 分析报告（适合手机与电脑查看）
"""
import os
import json
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))

class ReportGenerator:
    def __init__(self, output_dir="reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def assess_market_temperature(self, indices):
        """评估大盘市场温度与赚钱效应"""
        if not indices:
            return {
                "status": "震荡整理",
                "color": "#eab308",
                "advice": "市场方向尚不明朗，控制总体仓位在 3~5 成以内，轻仓试探。",
                "temp_score": 60
            }
        
        # 统计主要指数表现
        up_count = sum(1 for idx in indices if idx['change_pct'] > 0)
        total_count = len(indices)
        sh_idx = next((idx for idx in indices if idx['code'] == '000001'), None)
        sh_pct = sh_idx['change_pct'] if sh_idx else 0.0

        if up_count >= 3 and sh_pct >= 0.5:
            return {
                "status": "多头进攻 · 赚钱效应良好",
                "color": "#ef4444",
                "bg_badge": "bg-red-500/10 text-red-500 border-red-500/30",
                "advice": "大盘处于多头进攻环境，热点轮动活跃。新手可按照策略在【建议买入区间】内分批低吸，总体仓位可保持在 5~7 成。",
                "temp_score": 85
            }
        elif up_count >= 2:
            return {
                "status": "结构性分化 · 聚焦核心龙头",
                "color": "#f59e0b",
                "bg_badge": "bg-amber-500/10 text-amber-500 border-amber-500/30",
                "advice": "大盘指数出现分化，存量博弈特征明显。切忌盲目追高杂毛股票，只关注具备成交量支撑的强势主线，总仓位控制在 3~5 成。",
                "temp_score": 68
            }
        else:
            return {
                "status": "弱势防守 · 谨慎防范回调",
                "color": "#10b981",
                "bg_badge": "bg-emerald-500/10 text-emerald-500 border-emerald-500/30",
                "advice": "市场整体受压，空方力量占优。新手建议多看少动，严控仓位在 2 成以下或空仓观望，耐心等待止跌企稳信号。",
                "temp_score": 45
            }

    def generate_sparkline_svg(self, prices):
        """生成极简的 SVG 走势折线图"""
        if not prices or len(prices) < 2:
            return ""
        
        width = 160
        height = 42
        min_p = min(prices)
        max_p = max(prices)
        p_range = max_p - min_p if max_p != min_p else 1.0

        points = []
        n = len(prices)
        for i, p in enumerate(prices):
            x = round(i * (width / (n - 1)), 1)
            y = round(height - 4 - ((p - min_p) / p_range) * (height - 8), 1)
            points.append(f"{x},{y}")
        
        path_data = "M " + " L ".join(points)
        is_up = prices[-1] >= prices[0]
        stroke_color = "#ef4444" if is_up else "#10b981"
        fill_color = "rgba(239, 68, 68, 0.15)" if is_up else "rgba(16, 185, 129, 0.15)"

        # 闭合填充区域
        area_data = f"{path_data} L {width},{height} L 0,{height} Z"

        return f'''
        <svg width="{width}" height="{height}" class="overflow-visible inline-block">
            <path d="{area_data}" fill="{fill_color}" />
            <path d="{path_data}" fill="none" stroke="{stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="{points[-1].split(',')[0]}" cy="{points[-1].split(',')[1]}" r="3" fill="{stroke_color}" />
        </svg>
        '''

    def generate_html_report(self, indices, recommended_stocks, report_date=None):
        """生成高颜值独立 HTML 报告"""
        if report_date is None:
            report_date = datetime.now(BEIJING_TZ).strftime("%Y年%m月%d日 %H:%M")

        market_env = self.assess_market_temperature(indices)

        # 构建指数卡片 HTML
        index_cards_html = ""
        for idx in indices:
            is_up = idx['change_pct'] >= 0
            color_class = "text-red-500" if is_up else "text-emerald-500"
            bg_badge = "bg-red-500/10" if is_up else "bg-emerald-500/10"
            sign = "+" if is_up else ""
            index_cards_html += f'''
            <div class="bg-slate-800/80 rounded-2xl p-4 border border-slate-700/60 shadow-lg flex flex-col justify-between">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-slate-300 font-medium text-sm">{idx['name']}</span>
                    <span class="text-xs text-slate-500 font-mono">{idx['code']}</span>
                </div>
                <div class="flex items-baseline justify-between">
                    <span class="text-2xl font-bold font-mono tracking-tight text-white">{idx['point']:.2f}</span>
                    <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono {bg_badge} {color_class}">
                        {sign}{idx['change_pct']:.2f}%
                    </span>
                </div>
                <div class="text-xs text-slate-400 mt-2 flex justify-between">
                    <span>成交额: {idx['amount_yi']} 亿</span>
                    <span>{sign}{idx['change_amount']:.2f}</span>
                </div>
            </div>
            '''

        # 构建推荐股票卡片 HTML
        stock_cards_html = ""
        for idx_num, st in enumerate(recommended_stocks, start=1):
            is_up = st['change_pct'] >= 0
            change_color = "text-red-500" if is_up else "text-emerald-500"
            change_sign = "+" if is_up else ""
            sparkline_svg = self.generate_sparkline_svg(st.get('recent_closes', []))

            # 标签 HTML
            tags_html = "".join([f'<span class="px-2 py-0.5 rounded-md text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">{t}</span>' for t in st.get('tags', [])])

            # 核心理由 HTML
            reasons_html = "".join([f'<li class="flex items-start text-xs text-slate-300 gap-1.5"><span class="text-red-400 mt-0.5">●</span><span>{r}</span></li>' for r in st.get('reasons', [])])

            stock_cards_html += f'''
            <div class="bg-slate-800/90 rounded-2xl p-5 border border-slate-700/70 shadow-xl hover:border-slate-500/50 transition-all flex flex-col gap-4">
                <!-- 头部信息 -->
                <div class="flex flex-col sm:flex-row sm:items-start justify-between border-b border-slate-700/50 pb-3 gap-3">
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">TOP {idx_num}</span>
                            <a href="https://stockpage.10jqka.com.cn/{st['code']}/" target="_blank" rel="noopener noreferrer" class="text-xl font-bold text-white tracking-wide hover:text-amber-300 hover:underline flex items-center gap-1.5 transition">
                                <span>{st['name']}</span>
                                <span class="text-xs text-slate-400 font-mono">({st['code']})</span>
                            </a>
                        </div>
                        <div class="flex flex-wrap items-center gap-1.5 mt-2">
                            {tags_html}
                        </div>
                        <!-- 直达第三方证券网站快捷通道 -->
                        <div class="flex flex-wrap items-center gap-2 mt-2.5">
                            <a href="https://stockpage.10jqka.com.cn/{st['code']}/" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-red-600/20 text-red-300 border border-red-500/30 hover:bg-red-600 hover:text-white transition">
                                <span>🔥 同花顺行情</span>
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                            </a>
                            <a href="https://quote.eastmoney.com/{st['symbol']}.html" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-blue-600/20 text-blue-300 border border-blue-500/30 hover:bg-blue-600 hover:text-white transition">
                                <span>📈 东方财富</span>
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                            </a>
                            <a href="https://xueqiu.com/S/{st['symbol'].upper()}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-sky-600/20 text-sky-300 border border-sky-500/30 hover:bg-sky-600 hover:text-white transition">
                                <span>💬 雪球讨论</span>
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                            </a>
                        </div>
                    </div>
                    <div class="sm:text-right flex sm:flex-col items-center sm:items-end justify-between sm:justify-start">
                        <div class="text-xs font-medium text-slate-400">严选爆发评分</div>
                        <div class="text-2xl font-black text-amber-400 font-mono">{st['score']}<span class="text-xs text-slate-400">分</span></div>
                    </div>
                </div>

                <!-- 盘面与走势微图 -->
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-900/60 rounded-xl p-3 border border-slate-700/40">
                    <div>
                        <div class="text-xs text-slate-400">最新收盘价</div>
                        <div class="text-lg font-bold font-mono text-white mt-0.5">¥{st['price']:.2f}</div>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">当日涨跌幅</div>
                        <div class="text-lg font-bold font-mono {change_color} mt-0.5">{change_sign}{st['change_pct']:.2f}%</div>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">换手率 / 成交额</div>
                        <div class="text-base font-bold font-mono text-slate-200 mt-1">{st.get('turnover_pct', '--')}% <span class="text-xs text-slate-400">({st['amount_yi']}亿)</span></div>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">量比(主力放量)</div>
                        <div class="text-base font-bold font-mono text-amber-300 mt-1">{st['vol_ratio']} 倍</div>
                    </div>
                </div>

                <!-- 近期15日收盘走势图 -->
                <div class="flex items-center justify-between px-2 text-xs text-slate-400">
                    <span>近15日价格走势图谱:</span>
                    <div>{sparkline_svg}</div>
                </div>

                <!-- 核心看多逻辑 -->
                <div class="bg-slate-900/40 rounded-xl p-3 border border-slate-800">
                    <div class="text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1">
                        <span>💡</span><span>大白话选股逻辑（为什么选它）：</span>
                    </div>
                    <ul class="space-y-1">
                        {reasons_html}
                    </ul>
                </div>

                <!-- 实战买卖时机与防守铁律表 (新手重点) -->
                <div class="bg-gradient-to-br from-slate-900/90 to-slate-950/90 rounded-xl p-3.5 border border-slate-700/80 space-y-2.5">
                    <div class="text-xs font-bold text-slate-200 flex items-center justify-between">
                        <span class="flex items-center gap-1"><span>🎯</span>新手实战买卖操作执行单</span>
                        <span class="text-xs text-slate-400 font-normal">盈亏比: <strong class="text-white font-mono">{st.get('risk_reward_ratio', 1.8)}:1</strong></span>
                    </div>
                    
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                        <!-- 买入区间 -->
                        <div class="bg-slate-800/80 rounded-lg p-2.5 border border-emerald-500/30">
                            <div class="text-emerald-400 font-bold mb-1 flex items-center gap-1">
                                <span>🟢</span><span>建议买入区间</span>
                            </div>
                            <div class="text-sm font-bold font-mono text-white">¥{st['buy_range']}</div>
                            <div class="text-[11px] text-slate-400 mt-1">分批低吸回踩，切忌盘初急追高</div>
                        </div>

                        <!-- 目标止盈 -->
                        <div class="bg-slate-800/80 rounded-lg p-2.5 border border-red-500/30">
                            <div class="text-red-400 font-bold mb-1 flex items-center gap-1">
                                <span>🎯</span><span>第一止盈目标</span>
                            </div>
                            <div class="text-sm font-bold font-mono text-red-400">¥{st['target_price']:.2f} <span class="text-xs">(+{st['target_pct']}%)</span></div>
                            <div class="text-[11px] text-slate-400 mt-1">达标后先卖出一半利润落袋</div>
                        </div>

                        <!-- 止损底线 -->
                        <div class="bg-slate-800/80 rounded-lg p-2.5 border border-amber-500/30">
                            <div class="text-amber-400 font-bold mb-1 flex items-center gap-1">
                                <span>🛑</span><span>严格止损红线</span>
                            </div>
                            <div class="text-sm font-bold font-mono text-amber-300">¥{st['stop_loss_price']:.2f} <span class="text-xs">({st['stop_loss_pct']}%)</span></div>
                            <div class="text-[11px] text-slate-400 mt-1">有效跌破立刻坚决离场，绝不抗单</div>
                        </div>
                    </div>

                    <div class="flex flex-wrap items-center justify-between text-xs px-1 pt-1.5 text-slate-300 border-t border-slate-700/80 gap-2">
                        <span class="flex items-center gap-1.5">
                            <span class="text-amber-400 font-bold">💰 21,000本金建仓指引：</span>
                            <strong class="text-amber-300 font-mono font-bold">{st.get('suggest_pos', '')}</strong>
                        </span>
                        <span class="text-[11px] text-slate-400">最小单位: 1手(100股) · T+1交割</span>
                    </div>
                </div>
            </div>
            '''

        # 完整 HTML 模板
        html = f'''<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="Expires" content="0" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A股每日短线雷达与买卖点分析 - {report_date}</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{
            background: linear-gradient(135deg, #090d16 0%, #0f172a 50%, #080d1a 100%);
            min-height: 100vh;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }}
    </style>
</head>
<body class="text-slate-100 antialiased p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
    
    <!-- 顶部标题栏 -->
    <header class="flex flex-col md:flex-row md:items-center justify-between pb-6 mb-6 border-b border-slate-800 gap-4">
        <div>
            <div class="flex items-center gap-2">
                <span class="inline-block w-3 h-3 rounded-full bg-red-500 animate-pulse"></span>
                <h1 class="text-2xl sm:text-3xl font-black tracking-tight text-white">A股每日短线雷达 · 新手买卖时机导航</h1>
            </div>
            <div class="flex flex-wrap items-center gap-2 mt-2 text-xs text-slate-300">
                <span class="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-medium">总资金设定: ¥21,000</span>
                <span class="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-medium">适合股价: ¥3.0 ~ ¥35.0</span>
                <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium">单笔仓位: 约 ¥4,500 (20%~25%)</span>
                <span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium">最多持仓: 2~3 只</span>
            </div>
        </div>
        <div class="flex items-center gap-3">
            <div class="text-right">
                <div class="text-xs text-slate-400">报告生成时间 (北京时间)</div>
                <div class="text-sm font-bold text-amber-300 font-mono">{report_date}</div>
            </div>
            <button onclick="window.location.reload(true)" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition">
                🔄 刷新最新
            </button>
            <button onclick="window.print()" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition">
                🖨️ 打印 / 存为PDF
            </button>
        </div>
    </header>

    <!-- 市场环境与温度 -->
    <section class="mb-8">
        <div class="bg-slate-800/60 rounded-3xl p-5 border border-slate-700/60 shadow-xl backdrop-blur-md">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                    <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl font-bold bg-slate-900 border border-slate-700">
                        🌡️
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">当前大盘环境判断</div>
                        <div class="text-lg sm:text-xl font-bold text-white flex items-center gap-2 mt-0.5">
                            <span>{market_env['status']}</span>
                            <span class="text-xs px-2.5 py-0.5 rounded-full border {market_env.get('bg_badge', '')}">市场温度 {market_env['temp_score']}℃</span>
                        </div>
                    </div>
                </div>
                <div class="md:max-w-xl text-xs sm:text-sm text-slate-300 bg-slate-900/80 p-3.5 rounded-2xl border border-slate-700/40">
                    <strong class="text-amber-400">【新手今日操作指南】：</strong>{market_env['advice']}
                </div>
            </div>

            <!-- 指数网格 -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mt-5">
                {index_cards_html}
            </div>
        </div>
    </section>

    <!-- 今日推荐股票区 -->
    <section class="mb-10">
        <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2">
                <span class="text-xl">🚀</span>
                <h2 class="text-xl font-bold text-white tracking-wide">今日精选 · 短线爆发与趋势潜力股 ({len(recommended_stocks)}只)</h2>
            </div>
            <span class="text-xs text-slate-400">已自动剔除 ST、冷门无流动性股及高位狂热妖股</span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            {stock_cards_html}
        </div>
    </section>

    <!-- 新手交易军规与避坑秘籍 -->
    <section class="bg-gradient-to-r from-red-950/30 via-slate-900/60 to-slate-900/80 rounded-3xl p-6 border border-red-900/30 shadow-2xl mb-8">
        <div class="flex items-center gap-2 mb-4">
            <span class="text-2xl">🛡️</span>
            <h2 class="text-lg sm:text-xl font-bold text-white">炒股新手生存与防爆仓军规（务必牢记心头）</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            <div class="bg-slate-800/80 rounded-2xl p-4 border border-slate-700">
                <div class="font-bold text-red-400 text-sm mb-1">1. 绝不满仓单只股票</div>
                <p class="text-slate-300 leading-relaxed">新手最忌一次性把所有本金梭哈单只股票。单只持仓建议控制在 <strong>15%~20%</strong> 以内，最多同时持仓 2~3 只，手里永远保留 3~5 成现金应急。</p>
            </div>
            <div class="bg-slate-800/80 rounded-2xl p-4 border border-slate-700">
                <div class="font-bold text-amber-400 text-sm mb-1">2. 破止损线如机器人般执行</div>
                <p class="text-slate-300 leading-relaxed">股票跌破给定的【严格止损红线】时，坚决无脑止损出局！不要心存“等反弹回本”的幻想，小亏割肉保本金，大亏深套悔断肠。</p>
            </div>
            <div class="bg-slate-800/80 rounded-2xl p-4 border border-slate-700">
                <div class="font-bold text-emerald-400 text-sm mb-1">3. 宁可踏空，绝不追高</div>
                <p class="text-slate-300 leading-relaxed">早盘急拉狂冲的股票往往是诱多出货陷阱。买入必须在【建议买入区间】内等它回踩 5 日均线分批低吸，买不到就放弃，机会天天有。</p>
            </div>
            <div class="bg-slate-800/80 rounded-2xl p-4 border border-slate-700">
                <div class="font-bold text-blue-400 text-sm mb-1">4. 达目标分批止盈</div>
                <p class="text-slate-300 leading-relaxed">达到【第一止盈目标】时，果断先卖出一半锁定真金白银利润！剩下的另一半把止损线抬高到买入成本价，让利润去无风险奔跑。</p>
            </div>
        </div>
    </section>

    <!-- 底部免责声明 -->
    <footer class="text-center text-xs text-slate-500 py-6 border-t border-slate-800/80 space-y-1">
        <p>风险提示：本报告由量化算法模型自动生成，所有数据与测算结果仅供学习研究与交易策略辅助参考，不构成任何实质性投资建议与买卖依据。</p>
        <p>股市有风险，入市需谨慎。A股实行 T+1 交易与涨跌幅限制，请务必根据自身风险承受能力独立决策。</p>
    </footer>

</body>
</html>
'''
        # 写入 latest 报告以及按日归档的报告
        latest_file = os.path.join(self.output_dir, "daily_report.html")
        date_str = datetime.now().strftime("%Y%m%d")
        archive_file = os.path.join(self.output_dir, f"report_{date_str}.html")

        with open(latest_file, "w", encoding="utf-8") as f:
            f.write(html)
        with open(archive_file, "w", encoding="utf-8") as f:
            f.write(html)

        # 同步生成并更新到 Windows 桌面（方便用户在桌面直接双击查看）
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        desktop_file = latest_file
        if os.path.exists(desktop_path):
            desktop_file = os.path.join(desktop_path, "今日A股短线雷达.html")
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(html)

        return os.path.abspath(desktop_file)

if __name__ == '__main__':
    from data_fetcher import AShareDataFetcher
    from strategy_engine import ShortTermTrendStrategy
    
    fetcher = AShareDataFetcher()
    strategy = ShortTermTrendStrategy()
    generator = ReportGenerator()

    indices = fetcher.get_market_indices()
    pool = fetcher.get_active_stocks_pool(30)
    evaluated = []
    for st in pool:
        df_k = fetcher.get_stock_kline(st['symbol'])
        res = strategy.evaluate_stock(st, df_k)
        if res:
            evaluated.append(res)
    evaluated.sort(key=lambda x: x['score'], reverse=True)
    top_stocks = evaluated[:4]

    path = generator.generate_html_report(indices, top_stocks)
    print(f"报告已生成: {path}")
