# -*- coding: utf-8 -*-
"""
手机端局域网看盘服务器与二维码生成器
无需任何第三方收费平台，完全免费、零注册、手机扫码直接打开高颜值报告
"""
import os
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import qrcode

def get_local_ip():
    """获取本机局域网 IPv4 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

class MobileReportHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        report_path = os.path.join(os.path.dirname(__file__), "reports", "daily_report.html")
        if not os.path.exists(report_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Report not generated yet.")
            return

        with open(report_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # 静默日志，不刷屏终端
        pass

def generate_desktop_qr(url):
    """在用户桌面生成【手机看盘二维码.png】"""
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.exists(desktop_path):
        return None

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")

    qr_file = os.path.join(desktop_path, "手机扫码看盘.png")
    img.save(qr_file)
    return qr_file

def print_terminal_qr(url):
    """在控制台打印字符二维码"""
    qr = qrcode.QRCode(box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

def start_mobile_server_background(port=8888):
    """在后台线程启动局域网微服务"""
    local_ip = get_local_ip()
    url = f"http://{local_ip}:{port}"

    try:
        server = HTTPServer(('0.0.0.0', port), MobileReportHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        # 生成桌面二维码图片
        qr_file = generate_desktop_qr(url)
        return url, qr_file
    except Exception as e:
        # 如果端口被占用，尝试 8889
        try:
            port = 8889
            url = f"http://{local_ip}:{port}"
            server = HTTPServer(('0.0.0.0', port), MobileReportHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            qr_file = generate_desktop_qr(url)
            return url, qr_file
        except Exception:
            return None, None

if __name__ == '__main__':
    url, qr_file = start_mobile_server_background(8888)
    print("服务已启动:", url)
    print("桌面二维码已保存至:", qr_file)
    print_terminal_qr(url)
    import time
    time.sleep(2)
