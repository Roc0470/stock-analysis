# -*- coding: utf-8 -*-
"""
Windows 全自动无人值守调度与标准批处理配置器 (V3.0)
功能：
1. 严格遵循纯 ASCII + CRLF + 绝对路径 + -u 规范生成桌面与本地 .bat 引导器（彻底杜绝 cmd 编码语法崩溃）；
2. 注册 Windows 任务计划程序：
   - AShare_Monitor_0925: 周一至周五 09:25 无黑框静默拉起实盘盯盘守护进程；
   - AShare_Radar_1430  : 周一至周五 14:30 准点静默运行尾盘选股与持仓体检，并主动推送到手机微信；
3. 配置当前用户登录自启兜底（若电脑在 09:25 之后才开机登录，自动静默补拉起盯盘，非交易时间自动秒退）。
"""
import os
import sys
import subprocess

if hasattr(sys.stdout, 'reconfigure') and sys.stdout is not None:
    sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
PYTHONW_EXE = os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe")
DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")


def write_ascii_bat(filepath, lines):
    """严格使用纯 ASCII 与标准 Windows CRLF 写入 .bat 启动脚手架"""
    content = "\r\n".join(lines) + "\r\n"
    with open(filepath, "wb") as f:
        f.write(content.encode("ascii"))


def update_all_bat_launchers():
    """更新本地与桌面所有 .bat 启动器，100% 纯 ASCII 零中文括号隐患"""
    monitor_bat_lines = [
        "@echo off",
        "title A-Share Realtime Portfolio Monitor V3.0",
        f'cd /d "{BASE_DIR}"',
        "cls",
        "echo =========================================================",
        "echo    [Real-Time Monitor V3.0] Starting Portfolio Guard...",
        "echo =========================================================",
        "echo.",
        f'if not exist "{PYTHON_EXE}" (',
        "    echo [ERROR] Python venv not found!",
        "    pause",
        "    exit /b 1",
        ")",
        f'"{PYTHON_EXE}" -u "{os.path.join(BASE_DIR, "realtime_monitor.py")}" --force',
        "echo.",
        "echo [Finished] Press any key to close...",
        "pause > nul"
    ]

    radar_bat_lines = [
        "@echo off",
        "title A-Share Daily Quant Radar V3.0",
        f'cd /d "{BASE_DIR}"',
        "cls",
        "echo =========================================================",
        "echo    [Daily Quant Radar V3.0] Running Market Scan...",
        "echo =========================================================",
        "echo.",
        f'if not exist "{PYTHON_EXE}" (',
        "    echo [ERROR] Python venv not found!",
        "    pause",
        "    exit /b 1",
        ")",
        f'"{PYTHON_EXE}" -u "{os.path.join(BASE_DIR, "main.py")}"',
        "echo.",
        "echo [Finished] Report updated on Desktop! Press any key to close...",
        "pause > nul"
    ]

    sync_bat_lines = [
        "@echo off",
        "title Sync Tonghuashun Portfolio V3.0",
        f'cd /d "{BASE_DIR}"',
        "cls",
        "echo =========================================================",
        "echo    [Sync Portfolio V3.0] Reading Clipboard Data...",
        "echo =========================================================",
        "echo.",
        f'if not exist "{PYTHON_EXE}" (',
        "    echo [ERROR] Python venv not found!",
        "    pause",
        "    exit /b 1",
        ")",
        f'"{PYTHON_EXE}" -u "{os.path.join(BASE_DIR, "sync_portfolio.py")}"',
        "echo.",
        "echo [Finished] Press any key to close...",
        "pause > nul"
    ]

    write_ascii_bat(os.path.join(BASE_DIR, "run_monitor.bat"), monitor_bat_lines)
    write_ascii_bat(os.path.join(BASE_DIR, "run_daily.bat"), radar_bat_lines)

    if os.path.exists(DESKTOP_DIR):
        write_ascii_bat(os.path.join(DESKTOP_DIR, "启动实盘盯盘与卖出报警.bat"), monitor_bat_lines)
        write_ascii_bat(os.path.join(DESKTOP_DIR, "启动A股短线量化雷达.bat"), radar_bat_lines)
        write_ascii_bat(os.path.join(DESKTOP_DIR, "一键同步同花顺持仓.bat"), sync_bat_lines)
        print("  ✓ 桌面与本地 5 个 .bat 引导器已全部升级为纯 ASCII + CRLF 防崩标准格式。")


def register_scheduled_tasks():
    """使用 PowerShell Register-ScheduledTask 注册零黑框静默定时任务（支持唤醒补跑与电池运行）"""
    ps_script = f'''
$ErrorActionPreference = "Stop"

# 1. 周一至周五 09:25 静默实盘盯盘任务
$action1 = New-ScheduledTaskAction -Execute '{PYTHONW_EXE}' -Argument '"{os.path.join(BASE_DIR, "realtime_monitor.py")}"' -WorkingDirectory '{BASE_DIR}'
$trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:25AM
$settings1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)
Register-ScheduledTask -TaskName "AShare_Monitor_0925" -Action $action1 -Trigger $trigger1 -Settings $settings1 -Description "A股实盘持仓毫秒级静默盯盘与移动锁利守护 (交易日09:25自启)" -Force | Out-Null

# 2. 周一至周五 10:15 早盘条件狙击手任务 (仅在大盘全红+未满仓+>=90分温和启动极品时才推微信，否则静默)
$action_sniper = New-ScheduledTaskAction -Execute '{PYTHONW_EXE}' -Argument '"{os.path.join(BASE_DIR, "main.py")}" --no-open --morning-sniper' -WorkingDirectory '{BASE_DIR}'
$trigger_sniper = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 10:15AM
$settings_sniper = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "AShare_Radar_1015_Sniper" -Action $action_sniper -Trigger $trigger_sniper -Settings $settings_sniper -Description "A股10:15早盘极品条件狙击扫描 (严苛条件触发，防诱多噪音)" -Force | Out-Null

# 3. 周一至周五 14:30 尾盘黄金窗口选股 + 持仓体检微信推送任务
$action2 = New-ScheduledTaskAction -Execute '{PYTHONW_EXE}' -Argument '"{os.path.join(BASE_DIR, "main.py")}" --no-open --push-wechat' -WorkingDirectory '{BASE_DIR}'
$trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 14:30
$settings2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "AShare_Radar_1430" -Action $action2 -Trigger $trigger2 -Settings $settings2 -Description "A股14:30尾盘严选雷达扫描与持仓体检微信准点推送" -Force | Out-Null

Write-Output "TASKS_REGISTERED_OK"
'''
    res = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True
    )
    if "TASKS_REGISTERED_OK" in res.stdout:
        print("  ✓ Windows 任务计划已成功注册：[AShare_Monitor_0925]、[AShare_Radar_1015_Sniper] 与 [AShare_Radar_1430]。")
    else:
        print(f"  ⚠️ PowerShell 注册返回提示: {res.stderr.strip() or res.stdout.strip()}")

    # 3. 配置用户登录静默自启脚本（防止晚于 09:25 开机时漏跑，非交易时段自动秒退）
    if os.path.exists(STARTUP_DIR):
        vbs_path = os.path.join(STARTUP_DIR, "AShare_Monitor_AutoGuard.vbs")
        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\r\n'
            f'WshShell.CurrentDirectory = "{BASE_DIR}"\r\n'
            f'WshShell.Run """{PYTHONW_EXE}"" ""{os.path.join(BASE_DIR, "realtime_monitor.py")}""", 0, False\r\n'
        )
        with open(vbs_path, "wb") as f:
            f.write(vbs_content.encode("ascii"))
        print(f"  ✓ 开机登录静默补跑守护已就位：{vbs_path}")


if __name__ == '__main__':
    print("=" * 66)
    print("🔧 正在部署 V3.0 全自动无人值守调度系统...")
    print("=" * 66)
    update_all_bat_launchers()
    register_scheduled_tasks()
    print("=" * 66)
    print("🎉 部署完成！今后交易日无需任何手动点击，系统将全自动静默护航。")
