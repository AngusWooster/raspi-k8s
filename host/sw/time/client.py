"""Time Service gRPC Client.

Connects to a running time daemon and prints the returned system time.
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
    """Connect to the daemon and call GetTime.

    Args:
        host: Server hostname or IP address.
        port: Server port number.

    Returns:
        GetTimeResponse from the server.

    Raises:
        grpc.RpcError: On connection failure or server-side error.
    """
    address = f"{host}:{port}"

    # insecure_channel: no TLS encryption (suitable for in-cluster communication)
    # For production use grpc.secure_channel with TLS certificates
    with grpc.insecure_channel(address) as channel:
        stub = time_service_pb2_grpc.TimeServiceStub(channel)
        response = stub.GetTime(
            time_service_pb2.GetTimeRequest(),
            timeout=_TIMEOUT_SECONDS,
        )
    return response


def print_response(response: time_service_pb2.GetTimeResponse) -> None:
    """Print the server response in a human-readable format."""
    print(f"Timestamp  : {response.timestamp}")
    print(f"Unix time  : {response.unix_seconds}.{response.unix_nanos:09d}")
    print(f"Timezone   : {response.timezone}")
    print(f"Hostname   : {response.hostname}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Time Service gRPC Client")
    parser.add_argument(
        "--host", default=_DEFAULT_HOST,
        help=f"Server hostname or IP (default: {_DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT,
        help=f"Server port (default: {_DEFAULT_PORT})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    args = _parse_args()

    try:
        response = get_time(args.host, args.port)
        print_response(response)
    except grpc.RpcError as e:
        print(f"Error: cannot reach {args.host}:{args.port}", file=sys.stderr)
        print(f"Reason: {e.code()} — {e.details()}", file=sys.stderr)
        sys.exit(1)
