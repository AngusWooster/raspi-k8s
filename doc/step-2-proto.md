# Step 2：Proto 定義

## gRPC 是什麼？

gRPC 讓兩個程式（在不同 Pod、不同機器）可以互相呼叫函式，就像呼叫本地函式一樣。

```
client.py                         daemon.py
─────────                         ─────────
stub.GetTime(request)  ─gRPC──►  class TimeServiceServicer:
                                      def GetTime(request):
response            ◄──gRPC──        return response
```

## Proto 是什麼？

`.proto` 檔是 **介面合約**，client 和 server 都遵守這份合約：
- 定義有哪些函式（`service`）
- 定義傳遞的資料格式（`message`）

類比：
- `service` ≈ Python 的 `class`
- `rpc`     ≈ Python 的 `def`（方法）
- `message` ≈ Python 的 `dataclass`（資料結構）

## 我們的 time_service.proto

```proto
syntax = "proto3";               // 使用第 3 版語法
package time_service;            // 命名空間，避免名稱衝突

// 定義服務（相當於一個 class）
service TimeService {
  // 定義一個 RPC 方法：
  // client 傳入 GetTimeRequest，server 回傳 GetTimeResponse
  rpc GetTime (GetTimeRequest) returns (GetTimeResponse);
}

// client 送出的資料（這個服務不需要任何輸入）
message GetTimeRequest {}

// server 回傳的資料
message GetTimeResponse {
  string timestamp   = 1;  // ISO 8601 時間字串，例如 "2026-06-20T10:30:00+00:00"
  int64 unix_seconds = 2;  // Unix timestamp（秒）
  int32 unix_nanos   = 3;  // 奈秒部分
  string timezone    = 4;  // 時區，例如 "Asia/Taipei"
  string hostname    = 5;  // Pod 名稱，例如 "time-daemon-7d9f8b-xk2p"
}
```

## 欄位編號是什麼？（`= 1`, `= 2`...）

每個欄位後面的數字是**二進位序列化的識別碼**，不是順序。
規則：
- 一旦定型**不能改**（改了就無法解析舊資料）
- 從 1 開始，不需要連續
- 1–15 佔 1 byte（常用欄位放這裡），16–2047 佔 2 bytes

## 從 .proto 到 Python

Bazel 會執行 `grpcio-tools` 的 `protoc` 把 proto 轉成兩個 Python 檔：

```
time_service.proto
      │
      │  [bazel genrule → grpc_tools.protoc]
      ▼
time_service_pb2.py       ← message 類別（GetTimeRequest, GetTimeResponse）
time_service_pb2_grpc.py  ← service 類別（TimeServiceStub, TimeServiceServicer）
```

`_pb2.py` = Protocol Buffer 第 2 代（pb2）的慣例命名

## 檔案位置

```
host/sw/time/
└── proto/
    ├── BUILD.bazel          ← 告訴 Bazel 如何處理這個 proto
    └── time_service.proto   ← 介面定義（你手寫的）
```
