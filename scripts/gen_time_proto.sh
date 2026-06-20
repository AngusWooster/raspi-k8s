#!/bin/bash
# Generate Python gRPC code from time_service.proto into the source tree.
#
# Output files (all committed to git for IDE support):
#   time_service_pb2.py       — message classes (runtime)
#   time_service_pb2_grpc.py  — service stub and servicer (runtime)
#   time_service_pb2.pyi      — message type stubs (IDE / Pyright)
#   time_service_pb2_grpc.pyi — service type stubs  (IDE / Pyright)
#
# Prerequisites:
#   pip install -r requirements-dev.txt   (provides mypy-protobuf)
#
# Usage:
#   ./scripts/gen_time_proto.sh
#
# Run this script after any change to time_service.proto.

set -e

WORKSPACE=$(git rev-parse --show-toplevel)
PROTO_DIR="$WORKSPACE/host/sw/time/proto"
PYTHON="$WORKSPACE/.venv/bin/python3"
VENV_BIN="$WORKSPACE/.venv/bin"

echo "Generating proto code..."
"$PYTHON" -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$PROTO_DIR" \
    --grpc_python_out="$PROTO_DIR" \
    --plugin="protoc-gen-mypy=$VENV_BIN/protoc-gen-mypy" \
    --plugin="protoc-gen-mypy_grpc=$VENV_BIN/protoc-gen-mypy_grpc" \
    --mypy_out="$PROTO_DIR" \
    --mypy_grpc_out="$PROTO_DIR" \
    "$PROTO_DIR/time_service.proto"

echo "Done. Generated files:"
ls "$PROTO_DIR"/*.py "$PROTO_DIR"/*.pyi
