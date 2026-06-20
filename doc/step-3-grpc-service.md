# Step 3：gRPC 服務實作

## 本章目標

完成 `host/sw/time/` 底下的核心程式碼，讓你能夠：

- 在開發機本機執行一個 gRPC server（`daemon.py`）
- 用 client（`client.py`）連上去查詢 Raspberry Pi 系統時間
- 透過 Bazel 建置與執行兩個程式

---

## 背景知識：gRPC 是什麼？

### RPC（Remote Procedure Call）

平常呼叫函式是在同一台電腦同一個程式裡：

```python
result = get_time()   # 本地呼叫
```

**RPC** 讓你對另一台電腦上的程式做同樣的事，看起來也像函式呼叫，但背後是網路通訊：

```python
result = stub.GetTime(request)   # 實際上是發一個網路請求到 Pi 上的 daemon
```

### gRPC 是 Google 開源的 RPC 框架

- 用 **Protocol Buffer（protobuf）** 定義介面（比 JSON 更小更快）
- 支援多種語言（Python、Go、C++...）
- 用 HTTP/2 傳輸，支援雙向串流

### 本專案的 gRPC 通訊

```
開發機或 K8s Pod                 Raspberry Pi 5
┌──────────────────┐             ┌──────────────────────┐
│  client.py       │             │  daemon.py           │
│                  │  ──gRPC──►  │                      │
│  stub.GetTime()  │  ◄──gRPC──  │  def GetTime():      │
│                  │             │      return 系統時間  │
└──────────────────┘             └──────────────────────┘
        port 50052 (本機) / 30052 (K8s NodePort)
```

---

## 本章涉及的檔案

```
host/sw/time/
├── daemon.py          gRPC server 主程式
├── client.py          gRPC client 測試工具
├── BUILD.bazel        Bazel 建置規則
└── proto/
    ├── time_service.proto        介面定義（手寫）
    ├── time_service_pb2.py       message 類別（script 產生）
    ├── time_service_pb2_grpc.py  service 類別（script 產生）
    ├── time_service_pb2.pyi      message 型別提示（script 產生）
    └── time_service_pb2_grpc.pyi service 型別提示（script 產生）
```

---

## 一、Proto 定義回顧

`time_service.proto` 是整個 gRPC 服務的合約，client 和 server 都遵守它：

```proto
syntax = "proto3";
package time_service;

service TimeService {
  rpc GetTime (GetTimeRequest) returns (GetTimeResponse);
}

message GetTimeRequest {}   // 不需要輸入參數

message GetTimeResponse {
  string timestamp   = 1;   // ISO 8601 時間，例如 "2026-06-20T10:30:00+00:00"
  int64 unix_seconds = 2;   // Unix 秒
  int32 unix_nanos   = 3;   // 奈秒部分
  string timezone    = 4;   // 時區，例如 "CST"
  string hostname    = 5;   // Pod / 主機名稱
}
```

**欄位編號（`= 1`, `= 2`...）** 是 protobuf 序列化時的識別碼，不是排列順序。
一旦部署後**絕對不能改**，改了就無法解析舊版的訊息。

---

## 二、Proto 程式碼產生

`time_service.proto` 不能直接被 Python 使用，需要先用工具轉換。

### 執行產生 script

```bash
./scripts/gen_time_proto.sh
```

### Script 做了什麼

```
time_service.proto
      │
      │  grpc_tools.protoc（grpcio-tools 提供）
      │
      ├──► time_service_pb2.py       message 類別（Python runtime 使用）
      ├──► time_service_pb2_grpc.py  service 類別（Python runtime 使用）
      │
      │  mypy-protobuf plugin
      │
      ├──► time_service_pb2.pyi      message 型別提示（IDE 使用）
      └──► time_service_pb2_grpc.pyi service 型別提示（IDE 使用）
```

### 為什麼需要 .pyi 型別提示檔

protobuf 的 `.py` 用動態方式建立類別，型別檢查工具（Pyright / Pylance）看不懂，
會報錯 `"GetTimeResponse" is not a known attribute`。

`.pyi` 是靜態的型別宣告檔，Pyright 讀它就能理解所有類別和屬性，IDE 的 autocomplete 和錯誤提示才會正確。

---

## 三、daemon.py 逐行解說

### 3-1 模組載入

```python
import time_service_pb2        # message 類別：GetTimeRequest, GetTimeResponse
import time_service_pb2_grpc   # service 類別：TimeServiceServicer, add_...to_server
```

這兩個 import 能成功，是因為 `proto/BUILD.bazel` 裡的 `imports = ["."]`
把 `host/sw/time/proto/` 加到 Python 的搜尋路徑（PYTHONPATH）。

### 3-2 Servicer 類別

```python
class TimeServiceServicer(time_service_pb2_grpc.TimeServiceServicer):
```

**繼承**（inheritance）的用途：proto 產生的基底類別定義了介面（有哪些方法），
我們的類別**覆寫**（override）`GetTime` 填入真正的邏輯。

如果不覆寫，呼叫時 gRPC 會回傳 `UNIMPLEMENTED` 錯誤。

### 3-3 GetTime 方法

```python
def GetTime(self, _request, context):
```

| 參數 | 說明 |
|------|------|
| `_request` | `GetTimeRequest` 物件（這個服務不需要輸入，加 `_` 表示故意不用） |
| `context` | gRPC 連線資訊，可用 `context.peer()` 取得 client 的 IP 位址 |

**讀取系統時間：**

```python
ns = time.time_ns()              # 奈秒精度（Python 3.7+）
unix_seconds = ns // 1_000_000_000
unix_nanos   = ns %  1_000_000_000
```

`time.time_ns()` 比 `time.time()` 更精確：
- `time.time()` 回傳浮點數，浮點誤差約 ±1 微秒
- `time.time_ns()` 回傳整數奈秒，無浮點誤差

**建立 Response：**

```python
return time_service_pb2.GetTimeResponse(
    timestamp=now_utc.isoformat(),
    unix_seconds=unix_seconds,
    unix_nanos=unix_nanos,
    timezone=local_tz,
    hostname=socket.gethostname(),
)
```

欄位名稱必須和 `time_service.proto` 裡的 `message GetTimeResponse` 完全一致。

### 3-4 serve() 函式

```python
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
```

- `ThreadPoolExecutor(max_workers=10)` — 同時最多處理 10 個請求，每個用一個執行緒
- 適合 I/O 密集型（讀時間、讀感測器）；CPU 密集型應考慮 ProcessPoolExecutor

```python
server.add_insecure_port("[::]:{port}")
```

- `[::]` — 監聽所有網路介面（IPv4 + IPv6），在 K8s Pod 裡必須這樣設定
- `insecure` — 不加密，適合叢集內部。正式環境應改用 TLS

### 3-5 SIGTERM 優雅停止

```python
def _handle_sigterm(*_):
    server.stop(grace=5).wait()
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)
```

K8s 刪除 Pod 的流程：
1. 發送 `SIGTERM` → 我們的程式收到，開始優雅停止
2. 等 `terminationGracePeriodSeconds`（預設 30 秒）
3. 如果還沒停，強制發送 `SIGKILL`

`server.stop(grace=5)` — 停止接受新請求，等最多 5 秒讓進行中的請求完成。

---

## 四、client.py 逐行解說

### 4-1 Channel 與 Stub

```python
with grpc.insecure_channel(address) as channel:
    stub = time_service_pb2_grpc.TimeServiceStub(channel)
    response = stub.GetTime(time_service_pb2.GetTimeRequest())
```

**Channel（通道）：**
- TCP 連線到 server 的抽象
- `with` 語句確保使用完後自動關閉連線

**Stub（存根）：**
- 代替你「在遠端呼叫函式」的物件
- `stub.GetTime(...)` 看起來是本地呼叫，實際上：
  1. 序列化 `GetTimeRequest` 為 protobuf 二進位格式
  2. 透過 HTTP/2 傳送到 server
  3. 等待回應
  4. 反序列化為 `GetTimeResponse` 物件

### 4-2 Timeout

```python
stub.GetTime(request, timeout=5)
```

5 秒內沒有收到回應，拋出 `grpc.RpcError`（錯誤碼 `DEADLINE_EXCEEDED`）。
在 K8s 環境中一定要設 timeout，避免無限等待。

### 4-3 錯誤處理

```python
except grpc.RpcError as e:
    print(f"Reason: {e.code()} — {e.details()}")
```

常見錯誤碼：

| 錯誤碼 | 意義 | 常見原因 |
|--------|------|----------|
| `UNAVAILABLE` | 無法連到 server | daemon 沒有跑、IP/port 錯誤 |
| `DEADLINE_EXCEEDED` | 超時 | server 太慢、網路問題 |
| `UNIMPLEMENTED` | 方法不存在 | server 版本不一致 |
| `INTERNAL` | server 內部錯誤 | daemon 程式碼有例外 |

---

## 五、BUILD.bazel 解說

```python
py_binary(
    name = "daemon",
    srcs = ["daemon.py"],
    deps = [
        "//host/sw/time/proto:time_service_proto",
        requirement("grpcio"),
    ],
)
```

**`py_binary`** — 產生可執行的 Python 程式（對應 `py_library` 是函式庫）

**`deps` 的兩種來源：**

| 寫法 | 來源 | 範例 |
|------|------|------|
| `//host/sw/time/proto:name` | 專案內其他 Bazel target | proto 函式庫 |
| `requirement("grpcio")` | pip 套件（來自 requirements_lock.txt）| grpcio 套件 |

Bazel 會自動解析相依關係：
```
:daemon
  └── //host/sw/time/proto:time_service_proto
        ├── time_service_pb2.py
        ├── time_service_pb2_grpc.py
        ├── requirement("grpcio")
        └── requirement("protobuf")
```

---

## 六、型別提示架構

```
開發工具（只有開發機需要）
requirements-dev.txt
├── mypy-protobuf   → 產生 .pyi 型別提示檔
└── grpc-stubs      → grpc 模組的型別定義

pyrightconfig.json（IDE 設定）
├── venvPath + venv → 告訴 IDE 用 .venv 裡的 Python
│                     （所以能找到 grpcio）
└── extraPaths      → 加入 host/sw/time/proto/
                      （所以能找到 time_service_pb2）
```

---

## 七、開發環境設定步驟（從零開始）

```bash
# 1. 建立 venv（只做一次）
python3 -m venv .venv

# 2. 安裝 runtime 套件（Bazel 也會用這份）
.venv/bin/pip install -r requirements.txt

# 3. 安裝開發工具（不進 Docker container）
.venv/bin/pip install -r requirements-dev.txt

# 4. 產生 proto 程式碼（修改 .proto 後重新執行）
./scripts/gen_time_proto.sh

# 5. VSCode：選擇 .venv/bin/python3 作為 interpreter
#    Ctrl+Shift+P → Python: Select Interpreter → .venv/bin/python3
```

---

## 八、本機測試

```bash
# 終端機 1：啟動 server
bazel run //host/sw/time:daemon

# 輸出：
# 2026-06-20 10:30:00,000 INFO Time service listening on [::]:50052

# 終端機 2：執行 client
bazel run //host/sw/time:client

# 輸出：
# Timestamp  : 2026-06-20T10:30:05.123456+00:00
# Unix time  : 1750415405.123456789
# Timezone   : CST
# Hostname   : your-machine-name
```

**帶參數執行：**

```bash
# 指定不同 port
bazel run //host/sw/time:daemon -- --port 9090

# 連到 Raspberry Pi（K8s NodePort）
bazel run //host/sw/time:client -- --host 192.168.1.100 --port 30052
```

---

## 九、修改 proto 後的完整工作流程

```bash
# 1. 編輯 proto 定義
vim host/sw/time/proto/time_service.proto

# 2. 重新產生所有程式碼
./scripts/gen_time_proto.sh

# 3. 確認差異
git diff host/sw/time/proto/

# 4. 更新 daemon.py / client.py（如有新欄位）

# 5. 驗證 build 正常
bazel build //host/sw/time/...

# 6. 本機測試
bazel run //host/sw/time:daemon &
bazel run //host/sw/time:client

# 7. commit 所有 proto 相關檔案
git add host/sw/time/proto/
git commit -m "feat(proto): add xxx field to GetTimeResponse"
```

---

## 十、常見問題

**Q：`Address already in use` 錯誤**

Port 50052 已被佔用：
```bash
lsof -i :50052     # 查看是哪個程式
kill <PID>         # 關掉它
# 或改用其他 port
bazel run //host/sw/time:daemon -- --port 9090
```

**Q：client 顯示 `UNAVAILABLE`**

daemon 沒有在跑，或 host/port 設定錯誤：
```bash
# 確認 daemon 有在執行
bazel run //host/sw/time:daemon
# 然後再開另一個終端機執行 client
```

**Q：IDE 仍然顯示 import 錯誤**

依序確認：
1. 已執行 `./scripts/gen_time_proto.sh`（`.pyi` 檔是否存在？）
2. VSCode 已選擇 `.venv/bin/python3` 作為 interpreter
3. `pyrightconfig.json` 存在於專案根目錄
4. 重新啟動 VSCode 或執行 `Developer: Reload Window`

**Q：`protoc-gen-mypy: program not found`**

`requirements-dev.txt` 還沒安裝：
```bash
.venv/bin/pip install -r requirements-dev.txt
```
