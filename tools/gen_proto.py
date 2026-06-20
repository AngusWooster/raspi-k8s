"""Bazel genrule 用的 protoc 包裝工具。

用法（由 Bazel genrule 呼叫）：
    python gen_proto.py <proto_file> <output_dir>

說明：
    呼叫 grpcio-tools 的 protoc，把 .proto 轉成：
    - <name>_pb2.py      (message 類別)
    - <name>_pb2_grpc.py (service 類別)
"""

import sys
import os
from grpc_tools import protoc


def main():
    if len(sys.argv) != 3:
        print("用法: gen_proto.py <proto_file> <output_dir>")
        sys.exit(1)

    proto_file = sys.argv[1]   # 例如 host/sw/time/proto/time_service.proto
    output_dir = sys.argv[2]   # Bazel 的 $(RULEDIR)

    proto_dir = os.path.dirname(proto_file)

    ret = protoc.main([
        "grpc_tools.protoc",
        f"-I{proto_dir}",           # 在哪裡找 .proto 檔
        f"--python_out={output_dir}",      # message 輸出目錄
        f"--grpc_python_out={output_dir}", # service 輸出目錄
        proto_file,
    ])

    if ret != 0:
        print(f"protoc 失敗，錯誤碼：{ret}")
        sys.exit(ret)


if __name__ == "__main__":
    main()
