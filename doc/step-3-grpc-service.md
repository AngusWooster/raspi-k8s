# Step 3：gRPC 服務實作（daemon + client）

## 這一步做了什麼

實作 `time daemon`：

```
client.py  ──gRPC──►  daemon.py  ──讀取──►  Raspberry Pi 系統時間
```

涉及的檔案：

```
host/sw/time/
├── daemon.py      gRPC server，讀取系統時間並回傳
├── client.py      gRPC client，連到 server 查詢時間並印出
└── BUILD.bazel    告訴 Bazel 如何建置這兩個程式
```

---

## 一、daemon.py 解說

### 整體結構

```
daemon.py
├── import                     載入 grpc、datetime、socket 等
├── class TimeServiceServicer  實作業務邏輯（繼承 proto 產生的基底類別）
│   └── def GetTime()          讀取系統時間，組成 Response 回傳
├── def serve()                建立並啟動 gRPC server
├── def _parse_args()          解析命令列參數（--port、--workers）
└── if __name__ == "__main__"  程式進入點
```

### Servicer 類別

```python
class TimeServiceServicer(time_service_pb2_grpc.TimeServiceServicer):
```

- **繼承**自 proto 產生的 `TimeServiceServicer`（在 `_grpc.py` 裡）
- 必須**覆寫** `GetTime` 方法，否則呼叫時回傳 `UNIMPLEMENTED` 錯誤

### GetTime 方法的參數

```python
def GetTime(self, _request, context):
```

| 參數 | 說明 |
|------|------|
| `_request` | client 送來的 `GetTimeRequest`（此服務不需要輸入，加 `_` 表示故意不用） |
| `context` | gRPC 連線資訊，可用 `context.peer()` 取得 client IP |

### 讀取系統時間

```python
ns = time.time_ns()              # 取得奈秒精度的 Unix timestamp
unix_seconds = ns // 1_000_000_000
unix_nanos   = ns %  1_000_000_000

now_utc = datetime.datetime.now(datetime.timezone.utc)
now_utc.isoformat()              # "2026-06-20T10:30:00.123456+00:00"
```

- `time.time_ns()` — Python 3.7+，比 `time.time()` 精度更高（奈秒 vs 浮點秒）
- `datetime.timezone.utc` — 明確指定 UTC，避免時區混淆

### SIGTERM 處理

```python
def _handle_sigterm(*_):
    server.stop(grace=5).wait()
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)
```

K8s 關閉 Pod 時會先送 `SIGTERM`，給服務 5 秒「優雅停止」（處理完手頭的請求再關）。
不處理 SIGTERM 的話，K8s 等 30 秒後強制 SIGKILL，可能中斷正在處理的請求。

### ThreadPoolExecutor

```python
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
```

gRPC server 同時可以處理最多 10 個平行請求，每個用一個執行緒處理。

### 監聽地址

```python
server.add_insecure_port("[::]:{port}")
```

- `[::]` — 監聽所有網路介面（IPv4 + IPv6），K8s 需要這樣才能接受來自其他 Pod 的連線
- `insecure` — 不加密，適合叢集內部通訊。正式環境需換成 TLS

---

## 二、client.py 解說

### 整體結構

```
client.py
├── import
├── def get_time(host, port)    連到 server 並呼叫 GetTime()
├── def print_response(resp)    格式化印出結果
├── def _parse_args()           解析 --host、--port
└── if __name__ == "__main__"   執行 get_time，處理錯誤
```

### Stub 是什麼？

```python
with grpc.insecure_channel(address) as channel:
    stub = time_service_pb2_grpc.TimeServiceStub(channel)
    response = stub.GetTime(time_service_pb2.GetTimeRequest())
```

- `channel` — 連線到 server 的通道（像是電話線）
- `stub` — 讓你「假裝」在呼叫本地函式，背後實際是網路呼叫
- `stub.GetTime(...)` — 看起來像普通的 Python 函式呼叫，實際是發送 gRPC 請求

### with 語句的作用

```python
with grpc.insecure_channel(address) as channel:
    ...
```

離開 `with` 區塊時自動關閉連線，確保不會漏掉資源釋放。

### 錯誤處理

```python
except grpc.RpcError as e:
    print(f"錯誤：{e.code()} — {e.details()}")
```

常見錯誤碼：

| 錯誤碼 | 原因 |
|--------|------|
| `UNAVAILABLE` | server 沒有在跑，或 IP/port 錯誤 |
| `DEADLINE_EXCEEDED` | 超過 `timeout=5` 秒沒有回應 |
| `UNIMPLEMENTED` | server 沒有實作這個方法 |

---

## 三、BUILD.bazel 解說

```python
py_binary(
    name = "daemon",
    srcs = ["daemon.py"],
    deps = [
        "//host/sw/time/proto:time_service_proto",  # proto 產生的 py_library
        requirement("grpcio"),                       # pip 套件
    ],
)
```

- `py_binary` — 產生一個可執行的 Python 程式
- `deps` — 列出所有相依：proto 函式庫 + grpcio 套件
- Bazel 自動追蹤相依，確保 `daemon` 建置前 `time_service_proto` 已建置

---

## 四、型別提示（.pyi 檔）

### 問題

protobuf 用動態方式建立類別，Pyright / Pylance（IDE 的型別檢查工具）看不懂：

```
錯誤：Import "time_service_pb2" could not be resolved
錯誤："GetTimeResponse" is not a known attribute of module "time_service_pb2"
```

### 解法：mypy-protobuf

`mypy-protobuf` 讀取 `.proto`，額外產生 `.pyi` 型別提示檔：

```
time_service.proto
      │
      └──► mypy-protobuf ──► time_service_pb2.pyi      ← IDE 讀這個
                         ──► time_service_pb2_grpc.pyi
```

`.pyi` 包含明確的類別定義讓 Pyright 讀懂：

```python
# time_service_pb2.pyi（mypy-protobuf 產生）
class GetTimeResponse(_message.Message):
    timestamp: str
    unix_seconds: int
    ...
```

### requirements-dev.txt vs requirements.txt

| 檔案 | 用途 | 會進 Docker 嗎？ |
|------|------|-----------------|
| `requirements.txt` | runtime 套件（grpcio、protobuf）| 會 |
| `requirements-dev.txt` | 開發工具（mypy-protobuf、grpc-stubs）| 不會 |

---

## 五、開發 venv 設定

```bash
# 建立 venv（只需做一次）
python3 -m venv .venv

# 安裝 runtime 套件
.venv/bin/pip install -r requirements.txt

# 安裝開發工具
.venv/bin/pip install -r requirements-dev.txt
```

`pyrightconfig.json` 告訴 IDE：
- 用 `.venv` 裡的 Python（找得到 grpcio）
- `host/sw/time/proto/` 加到搜尋路徑（找得到 `time_service_pb2`）

---

## 六、執行與測試

### 本機測試（兩個終端機）

```bash
# 終端機 1：啟動 daemon
bazel run //host/sw/time:daemon

# 終端機 2：執行 client
bazel run //host/sw/time:client
# 輸出：
# Timestamp  : 2026-06-20T10:30:00.123456+00:00
# Unix time  : 1750415400.123456000
# Timezone   : CST
# Hostname   : your-machine-name
```

### 連到 Raspberry Pi 上的 daemon

```bash
bazel run //host/sw/time:client -- --host <Pi-IP> --port 30052
```

### 修改 proto 後的流程

```bash
# 1. 修改 host/sw/time/proto/time_service.proto
# 2. 重新產生所有 proto 相關檔案
./scripts/gen_time_proto.sh
# 3. 確認 diff
git diff host/sw/time/proto/
# 4. 重新 build 確認沒有錯誤
bazel build //host/sw/time/...
# 5. commit
git add host/sw/time/proto/
git commit -m "feat(proto): ..."
```

---

## 七、常見問題

**Q：執行 daemon 時顯示 `Address already in use`**

Port 50052 已被佔用：
```bash
# 找出是哪個程式
lsof -i :50052
# 或換一個 port
bazel run //host/sw/time:daemon -- --port 50099
```

**Q：client 顯示 `UNAVAILABLE — failed to connect`**

daemon 沒有在跑，或 host/port 設定錯誤。先確認：
```bash
bazel run //host/sw/time:daemon &
bazel run //host/sw/time:client
```

**Q：import 在 IDE 仍然顯示錯誤**

1. 確認 VSCode 已選擇 `.venv` 的 Python：`Ctrl+Shift+P` → `Python: Select Interpreter` → 選 `.venv/bin/python3`
2. 確認 `pyrightconfig.json` 存在於專案根目錄
3. 重新執行 `./scripts/gen_time_proto.sh` 確保 `.pyi` 檔存在
