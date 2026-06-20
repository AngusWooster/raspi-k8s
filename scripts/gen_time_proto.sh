#!/bin/bash
# 產生 time_service 的 Python gRPC 程式碼到 source 目錄
#
# 產生的檔案：
#   time_service_pb2.py      — message 類別（runtime 使用）
#   time_service_pb2_grpc.py — service 類別（runtime 使用）
#   time_service_pb2.pyi     — message 型別提示（IDE / Pyright 使用）
#   time_service_pb2_grpc.pyi— service 型別提示（IDE / Pyright 使用）
#
# 前置條件：
#   pip install -r requirements-dev.txt  （需要 mypy-protobuf）
#
# 用法：./scripts/gen_time_proto.sh
# 修改 .proto 後執行此 script 更新所有產生的檔案

set -e

WORKSPACE=$(git rev-parse --show-toplevel)
PROTO_DIR="$WORKSPACE/host/sw/time/proto"
PYTHON="$WORKSPACE/.venv/bin/python3"
VENV_BIN="$WORKSPACE/.venv/bin"

echo "產生 proto 程式碼..."
# --plugin 告訴 protoc 去哪裡找 mypy 插件（在 venv 裡）
"$PYTHON" -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$PROTO_DIR" \
    --grpc_python_out="$PROTO_DIR" \
    --plugin="protoc-gen-mypy=$VENV_BIN/protoc-gen-mypy" \
    --plugin="protoc-gen-mypy_grpc=$VENV_BIN/protoc-gen-mypy_grpc" \
    --mypy_out="$PROTO_DIR" \
    --mypy_grpc_out="$PROTO_DIR" \
    "$PROTO_DIR/time_service.proto"

echo "完成，產生的檔案："
ls "$PROTO_DIR"/*.py "$PROTO_DIR"/*.pyi
