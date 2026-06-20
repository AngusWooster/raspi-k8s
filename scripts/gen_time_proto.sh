#!/bin/bash
# 產生 time_service 的 Python gRPC 程式碼到 source 目錄
# 用法：./scripts/gen_time_proto.sh
# 修改 .proto 後執行此 script 來更新 _pb2.py

set -e

WORKSPACE=$(git rev-parse --show-toplevel)
PROTO_DIR="$WORKSPACE/host/sw/time/proto"

echo "產生 proto 程式碼..."
bazel run //tools:gen_proto -- \
    "$PROTO_DIR/time_service.proto" \
    "$PROTO_DIR"

echo "完成："
ls "$PROTO_DIR"/*_pb2*.py
