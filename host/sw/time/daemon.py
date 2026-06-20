"""Time Service gRPC Server

讀取 Raspberry Pi 系統時間，透過 gRPC 提供給 client 查詢。
"""

import argparse
import datetime
import logging
import signal
import socket
import sys
import time
from concurrent import futures

import grpc

import time_service_pb2
import time_service_pb2_grpc

_DEFAULT_PORT = 50052
_DEFAULT_WORKERS = 10


class TimeServiceServicer(time_service_pb2_grpc.TimeServiceServicer):
    """實作 TimeService 的業務邏輯。

    繼承自 proto 產生的 TimeServiceServicer 基底類別，
    覆寫 GetTime 方法填入真正的系統時間讀取邏輯。
    """

    def GetTime(self, _request, context):
        """讀取系統時間並回傳給 client。

        Args:
            request: GetTimeRequest（此服務不需要任何輸入參數）
            context: gRPC 連線資訊

        Returns:
            GetTimeResponse: 包含時間戳記、Unix time、時區、hostname
        """
        # 取得奈秒精度的 Unix timestamp
        ns = time.time_ns()
        unix_seconds = ns // 1_000_000_000
        unix_nanos = ns % 1_000_000_000

        # 取得 UTC 時間（ISO 8601 格式）
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # 取得本機時區名稱
        local_tz = datetime.datetime.now().astimezone().tzname() or "UTC"

        logging.info("GetTime request from %s", context.peer())

        return time_service_pb2.GetTimeResponse(
            timestamp=now_utc.isoformat(),
            unix_seconds=unix_seconds,
            unix_nanos=unix_nanos,
            timezone=local_tz,
            hostname=socket.gethostname(),
        )


def serve(port: int = _DEFAULT_PORT, workers: int = _DEFAULT_WORKERS) -> None:
    """啟動 gRPC server 並等待請求。

    Args:
        port:    監聽的 port（預設 50052）
        workers: 最大並行執行緒數（預設 10）
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))

    # 把 Servicer 實作註冊進 server
    time_service_pb2_grpc.add_TimeServiceServicer_to_server(
        TimeServiceServicer(), server
    )

    # [::] 表示監聽所有網路介面（IPv4 + IPv6）
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    server.start()

    logging.info("Time service 已啟動，監聽 %s", listen_addr)

    # 收到 SIGTERM（k8s 關閉 pod 時發送）優雅地停止
    def _handle_sigterm(*_):
        logging.info("收到 SIGTERM，正在關閉...")
        server.stop(grace=5).wait()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    # 阻塞直到 server 停止
    server.wait_for_termination()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Time Service gRPC Server")
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT,
        help=f"監聽的 port（預設 {_DEFAULT_PORT}）"
    )
    parser.add_argument(
        "--workers", type=int, default=_DEFAULT_WORKERS,
        help=f"執行緒池大小（預設 {_DEFAULT_WORKERS}）"
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()
    serve(port=args.port, workers=args.workers)
