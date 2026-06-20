"""Time Service gRPC Server.

Reads the Raspberry Pi system time and serves it to clients via gRPC.
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
    """Implements the TimeService RPC methods.

    Inherits from the proto-generated base class and overrides GetTime
    with the actual system time reading logic.
    """

    def GetTime(self, _request, context):
        """Read the system clock and return time information to the client.

        Args:
            _request: GetTimeRequest (unused, no input parameters needed).
            context:  gRPC servicer context; used here to log the caller.

        Returns:
            GetTimeResponse populated with timestamp, unix time, timezone,
            and hostname.
        """
        # nanosecond-precision unix timestamp
        ns = time.time_ns()
        unix_seconds = ns // 1_000_000_000
        unix_nanos   = ns %  1_000_000_000

        # UTC wall-clock time in ISO 8601 format
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # local timezone abbreviation (e.g. "CST", "UTC")
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
    """Start the gRPC server and block until terminated.

    Args:
        port:    TCP port to listen on (default 50052).
        workers: Maximum number of concurrent request threads (default 10).
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))

    # Register our Servicer implementation with the gRPC server
    time_service_pb2_grpc.add_TimeServiceServicer_to_server(
        TimeServiceServicer(), server
    )

    # [::] listens on all interfaces (IPv4 + IPv6), required inside Kubernetes
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    server.start()

    logging.info("Time service listening on %s", listen_addr)

    # Graceful shutdown on SIGTERM (sent by Kubernetes before killing the pod)
    def _handle_sigterm(*_):
        logging.info("Received SIGTERM, shutting down gracefully...")
        server.stop(grace=5).wait()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    server.wait_for_termination()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Time Service gRPC Server")
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT,
        help=f"Port to listen on (default {_DEFAULT_PORT})",
    )
    parser.add_argument(
        "--workers", type=int, default=_DEFAULT_WORKERS,
        help=f"Thread pool size (default {_DEFAULT_WORKERS})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()
    serve(port=args.port, workers=args.workers)
