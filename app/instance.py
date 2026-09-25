"""单实例守护：重复启动时唤醒已打开的窗口，避免多实例同时写数据。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance:
    def __init__(self, key: str):
        self.key = key
        self.server: QLocalServer | None = None
        self._on_activate: Callable[[], None] = lambda: None

    def try_acquire(self, on_activate: Callable[[], None]) -> bool:
        """返回 True 表示获得实例权；False 表示已有实例在运行（已发送唤醒消息）。"""
        self._on_activate = on_activate
        sock = QLocalSocket()
        sock.connectToServer(self.key)
        if sock.waitForConnected(200):
            sock.write(b"raise\n")
            sock.flush()
            sock.waitForBytesWritten(200)
            sock.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.key)   # 清理异常退出遗留的管道
        self.server = QLocalServer()
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(self.key)
        return True

    def _on_connection(self) -> None:
        if self.server is None:
            return
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            if conn:
                conn.readyRead.connect(lambda c=conn: self._on_activate())

    def shutdown(self) -> None:
        if self.server is not None:
            self.server.close()
            self.server = None
