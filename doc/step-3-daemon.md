# Step 3：gRPC Server（daemon.py）

## Server 的結構

一個 gRPC server 由三個部分組成：

```
1. Servicer 類別   — 實作業務邏輯（回傳什麼資料）
2. gRPC Server     — 負責網路通訊（監聽 port、序列化）
3. 進入點 serve()  — 啟動 server、等待請求
```

## 從 proto 到 Python 的對應

```proto
# time_service.proto
service TimeService {
  rpc GetTime (GetTimeRequest) returns (GetTimeResponse);
}
```

proto 產生的 `time_service_pb2_grpc.py` 裡有一個基底類別：

```python
class TimeServiceServicer:
    def GetTime(self, request, context):
        # 預設：回傳 UNIMPLEMENTED 錯誤
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        raise NotImplementedError()
```

我們繼承它，覆寫 `GetTime` 填入真正的邏輯：

```python
class TimeServiceServicer(time_service_pb2_grpc.TimeServiceServicer):
    def GetTime(self, request, context):
        now = datetime.now(timezone.utc)
        return time_service_pb2.GetTimeResponse(
            timestamp = now.isoformat(),
            unix_seconds = int(now.timestamp()),
            ...
        )
```

## request 和 context 是什麼？

| 參數 | 型別 | 說明 |
|------|------|------|
| `request` | `GetTimeRequest` | client 送來的資料（這個服務是空的） |
| `context`  | `grpc.ServicerContext` | 連線資訊，可設定狀態碼、取消請求等 |

## ThreadPoolExecutor 是什麼？

```python
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
```

gRPC server 是**多執行緒**的：同時可以處理最多 10 個請求。
`ThreadPoolExecutor` 是 Python 標準庫，管理執行緒池。

## 如何讀取 Raspberry Pi 系統時間？

```python
import time
import datetime

# 方法 1：datetime（推薦，有時區資訊）
now = datetime.datetime.now(datetime.timezone.utc)
now.isoformat()     # "2026-06-20T10:30:00.123456+00:00"
now.timestamp()     # 1750415400.123456（float）

# 方法 2：time.time_ns()（奈秒精度）
ns = time.time_ns()
seconds = ns // 1_000_000_000
nanos   = ns %  1_000_000_000

# 讀取本機時區
import datetime
local = datetime.datetime.now().astimezone()
local.tzname()      # "CST" 或 "Asia/Taipei"
```

## daemon.py 結構

```python
import grpc
from concurrent import futures
import datetime, socket, time

import time_service_pb2
import time_service_pb2_grpc

class TimeServiceServicer(...):       # 1. 業務邏輯
    def GetTime(self, request, context):
        ...

def serve(port):                      # 2. 啟動 server
    server = grpc.server(...)
    time_service_pb2_grpc.add_TimeServiceServicer_to_server(...)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":            # 3. 進入點
    serve(port=50052)
```
