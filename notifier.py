# -*- coding: utf-8 -*-
"""
微信消息推送模块 (支持 PushPlus 推送加)
将每日 A股短线严选结果自动推送到用户手机微信
"""
import requests
import json
import config

class WeChatNotifier:
    def __init__(self, token=None):
        self.token = token or getattr(config, 'PUSHPLUS_TOKEN', '')
        self.api_url = "http://www.pushplus.plus/send"

    def format_html_summary(self, indices, recommended_stocks, report_date):
        """生成适配手机微信卡片展示的高颜值精简 HTML 报文"""
        # 统计指数
        sh_idx = next((idx for idx in indices if idx['code'] == '000001'), None)
        sh_text = f"上证指数: {sh_idx['point']:.2f} ({'+' if sh_idx['change_pct'] >= 0 else ''}{sh_idx['change_pct']:.2f}%)" if sh_idx else ""

        stocks_html = ""
        for rank, st in enumerate(recommended_stocks, start=1):
            sign = "+" if st['change_pct'] >= 0 else ""
            color = "#ef4444" if st['change_pct'] >= 0 else "#10b981"
            ths_url = f"https://stockpage.10jqka.com.cn/{st['code']}/"

            stocks_html += f"""
            <div style="background:#f8fafc; border-left:4px solid #ef4444; border-radius:8px; padding:12px; margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <div>
                        <span style="background:#fef3c7; color:#b45309; font-weight:bold; font-size:11px; padding:2px 6px; border-radius:4px;">TOP {rank}</span>
                        <strong style="font-size:16px; color:#0f172a; margin-left:4px;">{st['name']}</strong>
                        <span style="color:#64748b; font-size:12px;">({st['code']})</span>
                    </div>
                    <span style="font-size:18px; font-weight:bold; color:{color};">{sign}{st['change_pct']:.2f}%</span>
                </div>
                <div style="font-size:12px; color:#475569; margin-bottom:6px; line-height:1.6;">
                    现价: <b>¥{st['price']:.2f}</b> | 换手率: <b>{st['turnover_pct']}%</b> | 评分: <b style="color:#b45309;">{st['score']}分</b>
                </div>
                <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:8px; font-size:12px; line-height:1.7;">
                    <div>🟢 <b>建议低吸区间：</b><span style="color:#10b981; font-weight:bold;">¥{st['buy_range']}</span> (不追高)</div>
                    <div>🎯 <b>第一止盈目标：</b><span style="color:#ef4444; font-weight:bold;">¥{st['target_price']:.2f} (+{st['target_pct']}%)</span> 预计赚 <b>+¥{st['expected_profit_rmb']}</b></div>
                    <div>🛑 <b>严格止损红线：</b><span style="color:#f59e0b; font-weight:bold;">¥{st['stop_loss_price']:.2f} ({st['stop_loss_pct']}%)</span> 最多亏 <b>-¥{st['max_loss_rmb']}</b></div>
                    <div style="border-top:1px dashed #e2e8f0; margin-top:4px; padding-top:4px; color:#334155;">
                        💰 <b>2.1万建仓建议：</b>买入 <b>{st['suggest_shares']}股</b> ({st['suggest_lots']}手，约¥{st['suggest_cost']:,.0f}元)
                    </div>
                </div>
                <div style="margin-top:8px; text-align:right;">
                    <a href="{ths_url}" style="background:#fee2e2; color:#dc2626; text-decoration:none; font-size:11px; padding:4px 8px; border-radius:4px; font-weight:bold;">查看同花顺F10行情 →</a>
                </div>
            </div>
            """

        full_html = f"""
        <div style="font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width:600px; margin:0 auto; color:#1e293b;">
            <div style="background:linear-gradient(135deg, #1e293b, #0f172a); color:#ffffff; padding:16px; border-radius:12px; margin-bottom:14px;">
                <h2 style="margin:0; font-size:18px;">📊 A股每日短线雷达 · 严选推送</h2>
                <div style="font-size:12px; color:#cbd5e1; margin-top:4px;">
                    {report_date} | {sh_text}
                </div>
                <div style="background:rgba(255,255,255,0.1); padding:6px 10px; border-radius:6px; font-size:11px; margin-top:8px;">
                    🎯 针对 21,000 元本金定制 · 严选沪深主板 · 自动排雷防诱多
                </div>
            </div>

            <div style="margin-bottom:14px;">
                {stocks_html}
            </div>

            <div style="background:#fffbeb; border:1px solid #fef3c7; border-radius:8px; padding:10px; font-size:11px; color:#92400e; line-height:1.6;">
                ⚠️ <b>实战纪律：</b><br>
                1. 宁等 14:30 尾盘回踩确认，不抢 9:30 早盘冲动；<br>
                2. 达到第一目标先卖一半锁定利润，破止损红线坚决止损！
            </div>
        </div>
        """
        return full_html

    def send_push(self, indices, recommended_stocks, report_date):
        """执行推送"""
        if not self.token or self.token.strip() == '':
            print("  ℹ️ 未配置 PushPlus Token，跳过微信推送。")
            return False

        content_html = self.format_html_summary(indices, recommended_stocks, report_date)
        title = f"【A股短线雷达】今日严选 TOP {len(recommended_stocks)} 推荐"

        payload = {
            "token": self.token.strip(),
            "title": title,
            "content": content_html,
            "template": "html"
        }

        try:
            r = requests.post(self.api_url, json=payload, timeout=8)
            res = r.json()
            if res.get('code') == 200:
                print(f"  🎉 微信推送成功！消息已送达您的微信。")
                return True
            else:
                print(f"  ⚠️ 微信推送提示: {res.get('msg')} ({res.get('data')})")
                return False
        except Exception as e:
            print(f"  ❌ 微信推送请求异常: {e}")
            return False

if __name__ == '__main__':
    notifier = WeChatNotifier('3055b67348e54de8a45a1ad09507aed0')
    test_stocks = [{
        'code': '002292',
        'name': '奥飞娱乐',
        'price': 9.37,
        'change_pct': 2.63,
        'turnover_pct': 10.24,
        'score': 91.7,
        'buy_range': '9.16 ~ 9.37',
        'target_price': 10.78,
        'target_pct': 15.0,
        'stop_loss_price': 8.92,
        'stop_loss_pct': -4.8,
        'expected_profit_rmb': 846,
        'max_loss_rmb': 270,
        'suggest_shares': 600,
        'suggest_lots': 6,
        'suggest_cost': 5622
    }]
    notifier.send_push([], test_stocks, "2026年10月26日")
