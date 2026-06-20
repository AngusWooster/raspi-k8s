"""Proto code generation tool for use in shell scripts.

Usage (called by scripts/gen_time_proto.sh):
    python gen_proto.py <proto_file> <output_dir>

Invokes grpcio-tools protoc to generate:
    <name>_pb2.py      — message classes
    <name>_pb2_grpc.py — service stub and servicer classes
"""

import sys
import os
from grpc_tools import protoc


def main():
    if len(sys.argv) != 3:
        print("Usage: gen_proto.py <proto_file> <output_dir>")
        sys.exit(1)

    proto_file = sys.argv[1]   # e.g. host/sw/time/proto/time_service.proto
    output_dir = sys.argv[2]   # destination directory for generated files

    proto_dir = os.path.dirname(proto_file)

    ret = protoc.main([
        "grpc_tools.protoc",
        f"-I{proto_dir}",                  # directory to search for .proto files
        f"--python_out={output_dir}",      # output directory for _pb2.py
        f"--grpc_python_out={output_dir}", # output directory for _pb2_grpc.py
        proto_file,
    ])

    if ret != 0:
        print(f"protoc failed with exit code {ret}")
        sys.exit(ret)


if __name__ == "__main__":
    main()
