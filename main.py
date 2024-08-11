import traceback
import os
import socket
import sys
import threading
from io import StringIO
from sty import fg
import colorama
from src.analyzer import Analyzer
from src.utils import color

VERSION = 'v2.7.0'


def error_msg():
    print(color('\n发生未知错误。请截图并报告此错误，并附上您的EE.log文件。', fg.li_red))
    input('按 ENTER 退出..')


def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')


class ConsoleOutputRedirector:
    def __init__(self):
        self.buffer = StringIO()  # 缓存所有控制台输出
        self.clients = []

    def write(self, message):
        sys.__stdout__.write(message)  # 输出到主机的原始控制台
        sys.__stdout__.flush()
        self.buffer.write(message)  # 将输出内容缓存
        for conn in self.clients:  # 向所有连接的客机发送实时内容
            try:
                conn.sendall(message.encode('utf-8'))
            except BrokenPipeError:
                self.clients.remove(conn)

    def flush(self):
        sys.__stdout__.flush()
        self.buffer.flush()

    def add_client(self, conn):
        self.clients.append(conn)
        conn.sendall(self.buffer.getvalue().encode('utf-8'))  # 发送之前缓存的内容


def handle_client(conn, redirector):
    redirector.add_client(conn)
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            sys.stdout.write(data.decode('utf-8', errors='replace'))
            sys.stdout.flush()
    except ConnectionAbortedError:
        pass  # 忽略连接中断错误
    finally:
        conn.close()


def start_server(redirector, port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('', port))
    server_socket.listen(5)
    print(f"服务器已启动，端口：{port}")

    while True:
        conn, addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(conn, redirector)).start()


def host_mode():
    clear_console()
    print("请使用内网穿透工具对此程序进行穿透")
    port = int(input('请输入端口号：'))
    clear_console()
    redirector = ConsoleOutputRedirector()
    sys.stdout = redirector  # 重定向控制台输出到自定义的redirector

    threading.Thread(target=start_server, args=(redirector, port), daemon=True).start()
    Analyzer().run()


def client_mode():
    clear_console()
    host = input('请输入主机地址（格式：IP:PORT）：')
    clear_console()
    ip, port = host.split(':')
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((ip, int(port)))
    print("已连接主机")

    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            print(data.decode('utf-8', errors='replace'), end='')

    finally:
        client_socket.close()


def multiplayer_mode():
    clear_console()
    print("1. 主机模式")
    print("2. 客机模式")
    choice = input("请选择模式: ")

    if choice == '1':
        host_mode()
    elif choice == '2':
        client_mode()
    else:
        print("无效选择，请重新启动程序。")
        input('按 ENTER 退出..')


def main():
    colorama.init()  # 使ANSI颜色工作。
    print(f'{fg.cyan}利润收割者圆蛛分析器 {VERSION} by {fg.li_cyan}ReVoltage#3425{fg.cyan}, 重写者 '
          f'{fg.li_cyan}Iterniam#5829{fg.cyan}, 翻译者'
          f'{fg.li_cyan} 小昕 [Q群:2941992901].')
    print(color("https://github.com/revoltage34/ptanalyzer \n", fg.li_grey))

    print("1. 单人模式")
    print("2. 多人模式")
    choice = input("请选择模式: ")

    if choice == '1':
        clear_console()
        Analyzer().run()  # 直接进入单人模式
    elif choice == '2':
        multiplayer_mode()
    else:
        print("无效选择，请重新启动程序。")
        input('按 ENTER 退出..')


if __name__ == "__main__":
    # noinspection PyBroadException
    try:
        main()
    except KeyboardInterrupt:  # 用于优雅地退出 ctrl + c
        pass
    except Exception:
        error_msg()
