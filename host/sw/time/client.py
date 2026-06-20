"""Time Service gRPC Client

連到 time daemon，查詢 Raspberry Pi 系統時間並印出結果。
"""

import argparse
import logging
import sys

import grpc

import time_service_pb2
import time_service_pb2_grpc

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 50052
_TIMEOUT_SECONDS = 5


def get_time(host: str, port: int) -> time_service_pb2.GetTimeResponse:
    """連到 daemon 並查詢系統時間。

    Args:
        host: server 的 hostname 或 IP
        port: server 監聽的 port

    Returns:
        GetTimeResponse

    Raises:
        grpc.RpcError: 連線失敗或 server 回傳錯誤
    """
    address = f"{host}:{port}"

    # insecure_channel：不加密（測試用）
    # 正式環境應改用 grpc.secure_channel + TLS 憑證
    with grpc.insecure_channel(address) as channel:
        stub = time_service_pb2_grpc.TimeServiceStub(channel)
        response = stub.GetTime(
            time_service_pb2.GetTimeRequest(),
            timeout=_TIMEOUT_SECONDS,
        )
    return response


def print_response(response: time_service_pb2.GetTimeResponse) -> None:
    """格式化印出 server 回傳的時間資訊。"""
    print(f"Timestamp  : {response.timestamp}")
    print(f"Unix time  : {response.unix_seconds}.{response.unix_nanos:09d}")
    print(f"Timezone   : {response.timezone}")
    print(f"Hostname   : {response.hostname}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Time Service gRPC Client")
    parser.add_argument(
        "--host", default=_DEFAULT_HOST,
        help=f"Server hostname 或 IP（預設 {_DEFAULT_HOST}）",
    )
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT,
        help=f"Server port（預設 {_DEFAULT_PORT}）",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    args = _parse_args()

    try:
        response = get_time(args.host, args.port)
        print_response(response)
    except grpc.RpcError as e:
        print(f"錯誤：無法連到 {args.host}:{args.port}", file=sys.stderr)
        print(f"原因：{e.code()} — {e.details()}", file=sys.stderr)
        sys.exit(1)
