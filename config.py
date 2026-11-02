# -*- coding: utf-8 -*-
"""
用户专属交易风控与账户配置 (V3.0 全自动实战闭环版)
针对【总资金 21,000 元 + 沪深主板严选 + 智能移动锁利 + 隐私隔离】量身定制
"""
import os

def _load_local_env():
    """原生轻量加载本地私有 .env 配置文件（免第三方库依赖，防止密钥泄露至公开仓库）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_vars = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    return env_vars

_LOCAL_ENV = _load_local_env()

# 1. 账户资金与仓位规划 (元)
TOTAL_CAPITAL = 21000.0

# 单笔建议建仓比例：约 25% ~ 30% (约 5,000 ~ 6,300 元)
# 原因：A股单笔最低佣金通常为 5 元，单笔 5000~6000 元能将佣金损耗率压低至 0.1% 以内，
# 同时每次最多持仓 2 只（占用 50%~60% 资金），永远保留 40%+ 现金防守。
DEFAULT_POS_RATIO = 0.28
MAX_HOLDINGS = 2

# 2. 交易权限过滤 (极其重要)
# 开启 ONLY_MAIN_BOARD 后，100% 只筛选沪深主板(600/601/603/605/000/001/002/003)，确保每只都能直接下单
ONLY_MAIN_BOARD = True

# 3. 股价与流动性过滤区间
MIN_STOCK_PRICE = 3.5     # 剔除低于 3.5 元的垃圾股/面值退市高危股
MAX_STOCK_PRICE = 35.0    # 剔除高于 35 元的高价股，确保 5000 元预算能灵活买卖 2~10 手
MIN_AMOUNT_YI = 3.0       # 全天收盘最低成交额基准 (亿元)，盘中扫描会自动按交易时间进度折算

# 4. 换手率黄金区间 (%)
MIN_TURNOVER_PCT = 2.0
MAX_TURNOVER_PCT = 22.0

# 5. 日内K线防诱多过滤
MIN_DAILY_CHANGE = 0.5    # 当日最低涨幅 (%)，只做当天红盘走强的多头票
MAX_DAILY_CHANGE = 8.0    # 当日最高涨幅 (%)，不追已经涨停或濒临涨停的票，防次日炸板
MAX_UPPER_SHADOW = 2.8    # 最大允许上影线比例 (%)，剔除“冲高回落避雷针”诱多出货图形

# 6. 止损与盈亏比底线 + 大盘冰点熔断阈值
MAX_STOP_LOSS_PCT = -4.8          # 单笔最大硬止损红线 (单笔最大亏损控制在 250 元以内)
MIN_RISK_REWARD = 1.6             # 最低盈亏比要求 (潜在收益必须 >= 1.6 倍潜在风险)
CIRCUIT_BREAKER_DROP_PCT = -1.2   # 大盘冰点熔断红线：当主要指数集体下跌且均幅跌破 -1.2% 时强制触发空仓保护

# 7. 扫描广度与输出数量
SCAN_POOL_COUNT = 400     # 扫描全市场成交额前 400 名活跃股
TOP_RECOMMEND_COUNT = 5   # 每日严选 TOP 5 精品（宁缺毋滥）

# 8. 微信主动推送配置 (从本地私有 .env 或环境变量读取，公开仓库零明文泄露)
def get_serverchan_key():
    """支持运行期热读取最新 .env 中的微信密钥，修改 .env 无需重启进程"""
    latest_env = _load_local_env()
    return os.environ.get("SERVERCHAN_KEY") or latest_env.get("SERVERCHAN_KEY", "")

SERVERCHAN_KEY = get_serverchan_key()
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN") or _LOCAL_ENV.get("PUSHPLUS_TOKEN", "")

# 9. 电脑端报警提示音模式 ('silent' 纯静音气泡 | 'soft' 柔和轻声 | 'loud' 蜂鸣重音)
ALERT_SOUND_MODE = "silent"
