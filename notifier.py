# -*- coding: utf-8 -*-
"""
微信消息主动推送模块 (V3.0 Server酱 Markdown 闭环版)
支持将每日【大盘熔断判定 + 个人持仓去留体检 + 14:30 尾盘严选推荐】一键推送至手机微信
"""
import requests
import config


class WeChatNotifier:
    def __init__(self, sct_key=None, pushplus_token=None):
        default_sct = config.get_serverchan_key() if hasattr(config, 'get_serverchan_key') else getattr(config, 'SERVERCHAN_KEY', '')
        self.sct_key = sct_key if sct_key is not None else default_sct
        self.pushplus_token = pushplus_token if pushplus_token is not None else getattr(config, 'PUSHPLUS_TOKEN', '')
        self.session = requests.Session()
        self.session.trust_env = False

    def format_markdown_report(self, indices, recommended_stocks, report_date, holdings_diag=None, circuit_breaker=(False, "")):
        """生成适配 Server酱 微信卡片阅读的精炼 Markdown 战报"""
        is_cb, cb_reason = circuit_breaker
        holdings_diag = holdings_diag or []
        holdings_cnt = len(holdings_diag)

        lines = [f"> 📅 **扫描时间**：{report_date} (北京时间)\n"]

        # 1. 大盘环境与冰点熔断横幅
        lines.append("### 🌡️ 一、大盘环境与风控总纲")
        if indices:
            idx_strs = []
            for idx in indices:
                sign = "+" if idx['change_pct'] >= 0 else ""
                idx_strs.append(f"- **{idx['name']}**：`{idx['point']:.2f}` ({sign}{idx['change_pct']:.2f}%) · 成交 {idx['amount_yi']}亿")
            lines.extend(idx_strs)

        if is_cb:
            lines.append(f"\n> ❄️ **【大盘冰点空仓熔断已触发】**\n> {cb_reason}\n")
        elif holdings_cnt >= config.MAX_HOLDINGS:
            lines.append(f"\n> ⚠️ **【仓位上限提醒】**：您当前已持有 **{holdings_cnt}/{config.MAX_HOLDINGS} 只** 股票，达到系统风控上限；今日新选标的**仅作观察备选，严禁超额加仓**。\n")
        else:
            remain_slots = config.MAX_HOLDINGS - holdings_cnt
            lines.append(f"\n> ✅ **【仓位状态】**：当前持有 **{holdings_cnt}/{config.MAX_HOLDINGS} 只**，剩余可开新仓额度：**{remain_slots} 只**（宁等尾盘回踩低吸，绝不早盘追高）。\n")

        # 2. 现有持仓去留体检
        lines.append("\n---\n### 💼 二、我的实盘持仓去留诊断")
        if not holdings_diag:
            lines.append("- 当前账户 **空仓 (0 只)**，资金安全充沛，可静待尾盘高胜率买点。")
        else:
            for h in holdings_diag:
                sign = "+" if h['change_pct'] >= 0 else ""
                p_sign = "+" if h['profit_rmb'] >= 0 else ""
                lines.append(
                    f"#### {h['name']} ({h['code']}) — {h['badge']}\n"
                    f"- **持仓/现价**：{h['shares']}股 | 现价 **¥{h['price']:.2f}** ({sign}{h['change_pct']:.2f}%) | 浮盈 **{p_sign}¥{h['profit_rmb']:.1f}**\n"
                    f"- **风控锚点**：移动防守线 **¥{h['stop_loss']:.2f}** | 止盈目标 **¥{h['take_profit']:.2f}** (最高水位 ¥{h['highest_price']:.2f})\n"
                    f"- **操作指引**：{h['advice']}\n"
                )

        # 3. 今日尾盘严选推荐
        lines.append("\n---\n### 🚀 三、今日严选短线潜力标的")
        if not recommended_stocks:
            lines.append("- 🛡️ **今日全市场无标的通过五重防诱多与多头严选（0 只）**。主动空仓观望就是最好的防守！")
        else:
            for rank, st in enumerate(recommended_stocks, start=1):
                sign = "+" if st['change_pct'] >= 0 else ""
                lines.append(
                    f"#### ⭐ TOP {rank}：{st['name']} ({st['code']}) · 评分 `{st['score']}分`\n"
                    f"- **盘口表现**：现价 **¥{st['price']:.2f}** ({sign}{st['change_pct']:.2f}%) | 换手 {st['turnover_pct']}% | 动态量比 {st['vol_ratio']}倍\n"
                    f"- **🟢 低吸区间**：`¥{st['buy_range']}` (严禁高于现价追涨)\n"
                    f"- **🎯 第一止盈**：`¥{st['target_price']:.2f}` (+{st['target_pct']}%) · 预计赚 +¥{st['expected_profit_rmb']}\n"
                    f"- **🛑 严格止损**：`¥{st['stop_loss_price']:.2f}` ({st['stop_loss_pct']}%) · 最多亏 -¥{st['max_loss_rmb']}\n"
                    f"- **💰 仓位建议**：{st['suggest_pos']}\n"
                )

        return "\n".join(lines)

    def send_push(self, indices, recommended_stocks, report_date, holdings_diag=None, circuit_breaker=(False, "")):
        """执行微信推送（优先使用本地 .env 中的 Server酱）"""
        is_cb, _ = circuit_breaker
        holdings_cnt = len(holdings_diag or [])
        rec_cnt = len(recommended_stocks or [])

        if is_cb:
            title = f"❄️【冰点空仓熔断】尾盘雷达(禁开新仓·持仓{holdings_cnt}只)"
        elif rec_cnt == 0:
            title = f"🛡️【空仓防守】今日严选0只达标(持仓{holdings_cnt}只体检已出)"
        elif holdings_cnt >= config.MAX_HOLDINGS:
            title = f"📊【满仓观察】持仓{holdings_cnt}只体检 + 尾盘备选TOP{rec_cnt}"
        else:
            top_name = recommended_stocks[0]['name']
            title = f"🚀【尾盘严选TOP{rec_cnt}】首选{top_name} + 持仓{holdings_cnt}只体检"

        if self.sct_key and self.sct_key.strip():
            md_body = self.format_markdown_report(indices, recommended_stocks, report_date, holdings_diag, circuit_breaker)
            try:
                r = self.session.post(
                    f"https://sctapi.ftqq.com/{self.sct_key.strip()}.send",
                    data={'title': title, 'desp': md_body},
                    timeout=8
                )
                res = r.json()
                if res.get('code') == 0:
                    print("  🎉 微信 Server酱 推送成功！尾盘战报与持仓体检已直达您的手机。")
                    return True
                else:
                    print(f"  ⚠️ Server酱推送返回提示: {res.get('message')}")
            except Exception as e:
                print(f"  ❌ Server酱推送网络异常: {e}")

        print("  ℹ️ 未检测到有效的本地微信推送密钥 (.env SERVERCHAN_KEY)，跳过微信推送。")
        return False
