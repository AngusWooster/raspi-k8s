# 學習手冊：從零掌握 Python / gRPC / Docker / K8s / Ansible

> 本手冊以 `raspi-k8s` 專案的真實程式碼為例。每個概念都對應你正在做的事。讀完這本手冊，你能獨立理解、修改、部署整個系統。

---

## 目錄

1. [Python 基礎](#chapter-1-python-基礎)
2. [網路基礎：IP、Port、TCP](#chapter-2-網路基礎)
3. [gRPC 與 Protobuf](#chapter-3-grpc-與-protobuf)
4. [Docker 與容器](#chapter-4-docker-與容器)
5. [Kubernetes 操作實戰](#chapter-5-kubernetes-操作實戰)
6. [Ansible 自動化](#chapter-6-ansible-自動化)
7. [整合：一次看懂整個系統](#chapter-7-整合)

---

# Chapter 1：Python 基礎

## 1.1 為什麼先學 Python？

你的整個服務——daemon（伺服器）和 client（客戶端）——都是 Python 寫的。看懂程式碼是理解系統的第一步。

## 1.2 變數與型別

Python 不需要宣告型別，直接賦值：

```python
# 整數
port = 50052

# 字串
host = "192.168.1.185"

# 浮點數
timeout = 5.0

# 布林
is_running = True
```

在你的 `client.py` 裡：

```python
_DEFAULT_HOST = "localhost"   # 字串，預設連 localhost
_DEFAULT_PORT = 50052         # 整數，預設 port
_TIMEOUT_SECONDS = 5          # 整數，連線逾時秒數
```

這三個都是**模組層級常數**（名字全大寫是 Python 的慣例，代表「不要修改我」）。

## 1.3 函式（Function）

```python
def 函式名稱(參數1, 參數2):
    """說明這個函式做什麼（docstring）"""
    # 執行內容
    return 結果
```

你的 `client.py` 裡的 `get_time`：

```python
def get_time(host: str, port: int) -> time_service_pb2.GetTimeResponse:
    """Connect to the daemon and call GetTime."""
    address = f"{host}:{port}"          # f-string：把變數嵌入字串
    with grpc.insecure_channel(address) as channel:
        stub = time_service_pb2_grpc.TimeServiceStub(channel)
        response = stub.GetTime(
            time_service_pb2.GetTimeRequest(),
            timeout=_TIMEOUT_SECONDS,
        )
    return response
```

**逐行解釋：**

| 程式碼 | 意思 |
|--------|------|
| `def get_time(host: str, port: int)` | 定義函式，`host` 是字串，`port` 是整數（`: str` 是型別提示，不強制） |
| `-> time_service_pb2.GetTimeResponse` | 這個函式回傳什麼型別（型別提示） |
| `f"{host}:{port}"` | f-string，把 `host` 和 `port` 的值插入字串，例如 `"192.168.1.185:50052"` |
| `with ... as channel` | with 語法確保用完後自動關閉 channel |
| `return response` | 把結果回傳給呼叫者 |

## 1.4 類別（Class）

類別是「有方法的資料容器」，讓相關的函式和資料放在一起：

```python
class 類別名稱(父類別):
    def 方法(self, 參數):
        pass
```

你的 `daemon.py` 裡的 `TimeServiceServicer`：

```python
class TimeServiceServicer(time_service_pb2_grpc.TimeServiceServicer):
    def GetTime(self, _request, context):
        ns = time.time_ns()
        # ...
        return time_service_pb2.GetTimeResponse(...)
```

**重點：**
- `TimeServiceServicer` 繼承（extends）自 `time_service_pb2_grpc.TimeServiceServicer`（protobuf 自動生成的基底類別）
- `GetTime` 是這個類別的方法（method）
- `self` 代表「這個物件本身」，每個方法第一個參數一定是 `self`
- `_request` 前面有底線，代表「這個參數我不會用到」（Python 慣例）

## 1.5 Import（引入模組）

Python 程式靠 import 引入其他檔案的功能：

```python
import argparse          # 標準函式庫：解析命令列參數
import datetime          # 標準函式庫：日期時間
import grpc              # 第三方套件：gRPC 通訊
import time_service_pb2  # 本專案生成的 protobuf 程式碼
```

**三種來源：**

| 來源 | 說明 | 例子 |
|------|------|------|
| Python 標準函式庫 | 安裝 Python 就有，不需要 pip | `import os`, `import datetime` |
| 第三方套件 | 需要 `pip install` 安裝 | `import grpc`, `import ansible` |
| 本地模組 | 你自己寫的檔案 | `import time_service_pb2` |

## 1.6 錯誤處理（try/except）

```python
try:
    response = get_time(args.host, args.port)
    print_response(response)
except grpc.RpcError as e:
    print(f"Error: cannot reach {args.host}:{args.port}", file=sys.stderr)
    sys.exit(1)
```

**解釋：**
- `try` 區塊：嘗試執行這段程式碼
- `except grpc.RpcError as e`：如果發生 `grpc.RpcError` 類型的錯誤，執行這個區塊，並把錯誤存到變數 `e`
- `sys.exit(1)`：結束程式，回傳錯誤碼 1（慣例：0 代表成功，非 0 代表失敗）

## 1.7 with 語法（Context Manager）

```python
with grpc.insecure_channel(address) as channel:
    # 在這個區塊裡使用 channel
    stub = ...
# 離開 with 區塊後，channel 自動關閉
```

`with` 確保資源（網路連線、檔案等）用完後一定被關閉，即使中途發生錯誤也一樣。

## 1.8 命令列參數（argparse）

你的 client 可以這樣執行：

```bash
python client.py --host 192.168.1.185 --port 30052
```

這是怎麼做到的？靠 `argparse`：

```python
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Time Service gRPC Client")
    parser.add_argument(
        "--host", default=_DEFAULT_HOST,
        help=f"Server hostname or IP (default: {_DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT,
        help=f"Server port (default: {_DEFAULT_PORT})",
    )
    return parser.parse_args()
```

| 程式碼 | 意思 |
|--------|------|
| `ArgumentParser` | 建立一個參數解析器 |
| `add_argument("--host")` | 註冊 `--host` 這個參數 |
| `default=_DEFAULT_HOST` | 若使用者沒有提供 `--host`，預設值是 `_DEFAULT_HOST` |
| `type=int` | 把使用者輸入的字串轉成整數 |
| `parse_args()` | 解析使用者實際輸入的參數，回傳結果 |

使用時：

```python
args = _parse_args()
# args.host 就是使用者輸入的 --host 值（或預設值）
# args.port 就是使用者輸入的 --port 值（或預設值）
response = get_time(args.host, args.port)
```

## 1.9 f-string 格式化

```python
host = "192.168.1.185"
port = 30052
address = f"{host}:{port}"
# address = "192.168.1.185:30052"

unix_nanos = 123456789
print(f"Unix time: {unix_seconds}.{unix_nanos:09d}")
# :09d 代表用 0 補齊到 9 位數
```

## 1.10 信號處理（Signal）

```python
def _handle_sigterm(*_):
    logging.info("Received SIGTERM, shutting down gracefully...")
    server.stop(grace=5).wait()
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)
```

**這在做什麼？**

當 Kubernetes 要停止 Pod 時，會先發送 `SIGTERM` 信號給程序（「你可以收拾了」），5 秒後再強制殺死（`SIGKILL`）。

這段程式碼讓 daemon 在收到 `SIGTERM` 時：
1. 印出日誌
2. 優雅地停止 gRPC server（最多等 5 秒讓進行中的請求完成）
3. 正常退出

沒有這段，Kubernetes 強制殺死時可能中斷正在處理的請求。

---

# Chapter 2：網路基礎

## 2.1 什麼是 IP 位址？

IP 位址是網路上每台機器的「地址」：

```
192.168.1.185   ← Pi 5 在區域網路的位址
127.0.0.1       ← localhost，代表「這台機器自己」
[::]            ← 所有網路介面（IPv4 + IPv6），daemon.py 用這個監聽
```

## 2.2 什麼是 Port？

一台機器可以同時跑很多服務，**port** 是用來區分「這個連線要找哪個服務」的號碼：

```
Pi 5（192.168.1.185）
├── Port 22   → SSH 服務（讓你遠端登入）
├── Port 6443 → k3s API server（kubectl 連這裡）
└── Port 30052 → time-daemon NodePort（你的 gRPC 服務）
```

port 是 0-65535 的數字：
- 0-1023：系統保留（HTTP=80, HTTPS=443, SSH=22）
- 30000-32767：Kubernetes NodePort 範圍

## 2.3 TCP 連線流程

gRPC 跑在 TCP 上。TCP 連線的過程：

```
Client（開發機）              Server（Pi 5 daemon）
     │                              │
     │──── 我想連 192.168.1.185:30052 ──►│  SYN
     │◄─── 好，連線建立 ───────────────│  SYN-ACK
     │──── 確認 ──────────────────────►│  ACK
     │                              │
     │──── GetTime 請求 ────────────►│
     │◄─── GetTimeResponse ──────────│
     │                              │
     │──── 關閉連線 ────────────────►│
```

你的程式碼中：
- `grpc.insecure_channel("192.168.1.185:30052")` → 建立 TCP 連線
- `stub.GetTime(...)` → 透過這個連線發送請求
- `with ... as channel` → 結束時關閉連線

## 2.4 Port 流向（完整圖）

```
開發機                    Pi 5（k3s node）            Pod（容器）
                          
client
  │
  └─► 192.168.1.185:30052  ──►  NodePort Service  ──►  daemon:50052
        （外部入口）               （K8s 轉發）           （實際程式）
```

為什麼有兩個不同的 port（30052 和 50052）？

- `30052`：NodePort，**Pi 5 對外**開放的 port，讓區域網路的其他機器能連進來
- `50052`：daemon 在容器**內部**監聽的 port
- K8s Service 負責把 30052 的流量轉到 50052

---

# Chapter 3：gRPC 與 Protobuf

## 3.1 為什麼用 gRPC？

**傳統 REST API：**
```
Client 發送：POST /api/time  (JSON 格式)
Server 回應：{"timestamp": "2026-06-21T...", "unix_seconds": 1750484200}
```

**gRPC：**
```
Client 呼叫：stub.GetTime(GetTimeRequest())
Server 回傳：GetTimeResponse(timestamp=..., unix_seconds=...)
```

gRPC 的優點：
- 像呼叫本地函式一樣呼叫遠端服務（RPC = Remote Procedure Call）
- 用 protobuf 序列化，比 JSON 快且省空間
- 自動生成 client 和 server 的程式碼
- 強型別，改了 API 定義就知道哪裡需要更新

## 3.2 Protobuf：定義資料格式

`time_service.proto` 定義了這個服務的「合約」：

```protobuf
syntax = "proto3";
package time_service;

// 定義服務有哪些 RPC 方法
service TimeService {
  rpc GetTime (GetTimeRequest) returns (GetTimeResponse);
}

// 請求的資料結構（這個服務不需要輸入，所以是空的）
message GetTimeRequest {}

// 回應的資料結構
message GetTimeResponse {
  string timestamp   = 1;   // 欄位名稱 = 編號
  int64 unix_seconds = 2;
  int32 unix_nanos   = 3;
  string timezone    = 4;
  string hostname    = 5;
}
```

**欄位編號（= 1, = 2...）的作用：**
編號是用來序列化和反序列化的，不是順序。一旦定義就不能改（改了會讓舊版 client 無法讀新版 server 的資料）。

## 3.3 從 .proto 生成程式碼

```
time_service.proto
       │
       │  protoc（protobuf 編譯器）
       ▼
time_service_pb2.py       ← 資料結構（GetTimeRequest, GetTimeResponse）
time_service_pb2_grpc.py  ← gRPC stub 和 servicer 基底類別
```

你不需要手動寫這兩個檔案，它們是自動生成的。

## 3.4 Server 端：Servicer

```python
class TimeServiceServicer(time_service_pb2_grpc.TimeServiceServicer):
    def GetTime(self, _request, context):
        return time_service_pb2.GetTimeResponse(
            timestamp=now_utc.isoformat(),
            unix_seconds=unix_seconds,
            unix_nanos=unix_nanos,
            timezone=local_tz,
            hostname=socket.gethostname(),
        )
```

**你需要做的事：**
1. 繼承 protobuf 生成的 `TimeServiceServicer` 基底類別
2. 實作 `.proto` 裡定義的每個 RPC 方法（這裡是 `GetTime`）
3. 回傳對應的 Response 物件

## 3.5 Client 端：Stub

```python
with grpc.insecure_channel(address) as channel:
    stub = time_service_pb2_grpc.TimeServiceStub(channel)
    response = stub.GetTime(
        time_service_pb2.GetTimeRequest(),
        timeout=_TIMEOUT_SECONDS,
    )
```

**`stub` 是什麼？**

Stub 是 protobuf 自動生成的「代理人」，讓你可以呼叫遠端的 `GetTime` 就像呼叫本地函式一樣。你呼叫 `stub.GetTime(...)`，stub 負責：
1. 把 `GetTimeRequest` 序列化成二進位格式
2. 透過 TCP 傳給 server
3. 收到回應後反序列化成 `GetTimeResponse` 物件
4. 回傳給你

## 3.6 完整 gRPC 呼叫流程

```
client.py                              daemon.py
  │                                       │
  │  stub.GetTime(GetTimeRequest())       │
  │──序列化──► 二進位資料 ──TCP──►        │
  │                                       │  def GetTime(self, request, context):
  │                                       │      return GetTimeResponse(...)
  │◄──TCP──── 二進位資料 ◄──序列化────   │
  │  response = GetTimeResponse(...)      │
  │  print(response.timestamp)            │
```

---

# Chapter 4：Docker 與容器

## 4.1 為什麼用容器？

問題：你的程式在自己電腦上跑得好，但在 Pi 5 上跑不起來，因為 Python 版本不同、套件沒裝。

容器解決這個問題：把程式和它所需的所有環境（Python 版本、套件、設定）打包成一個「箱子」，在任何有 container runtime 的機器上都能跑。

```
沒有容器：
開發機（Python 3.11, grpcio 1.71）──► Pi 5（Python 3.9, 沒有 grpcio）= 執行失敗

有容器：
開發機 ──打包──► 映像（含 Python 3.11 + grpcio 1.71）──► Pi 5 = 執行成功
```

## 4.2 Dockerfile 解析

`host/sw/time/Dockerfile`：

```dockerfile
# ── Stage 1: builder（安裝套件）──────────────────
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime（只複製必要的）──────────────
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
ENV PYTHONPATH=/app/proto
COPY host/sw/time/proto/time_service_pb2.py      proto/
COPY host/sw/time/proto/time_service_pb2_grpc.py proto/
COPY host/sw/time/daemon.py                       .
EXPOSE 50052
ENTRYPOINT ["python", "daemon.py"]
```

**逐行說明：**

| 指令 | 說明 |
|------|------|
| `FROM python:3.11-slim AS builder` | 以 Python 3.11 精簡版映像為基底，命名這個 stage 為 `builder` |
| `WORKDIR /build` | 設定工作目錄（之後的指令都在這個目錄執行） |
| `COPY requirements.txt .` | 把開發機的 `requirements.txt` 複製進容器 |
| `RUN pip install --prefix=/install` | 安裝套件到 `/install` 目錄（不安裝到系統目錄，方便複製） |
| `FROM python:3.11-slim`（第二個） | 開始新的 stage，這是最終的 runtime 映像 |
| `COPY --from=builder /install /usr/local` | 從 builder stage 複製安裝好的套件 |
| `ENV PYTHONPATH=/app/proto` | 設定環境變數，讓 Python 知道在 `/app/proto` 找模組 |
| `COPY ... proto/` | 複製 protobuf 生成的 Python 檔案 |
| `EXPOSE 50052` | 宣告容器監聽 50052 port（文件用途） |
| `ENTRYPOINT ["python", "daemon.py"]` | 容器啟動時執行這個命令 |

**為什麼要兩個 stage（multi-stage build）？**

```
只用一個 stage：映像大小 = Python base + 編譯工具 + 套件 + 程式碼 ≈ 500MB
兩個 stage：  映像大小 = Python base + 套件 + 程式碼 ≈ 150MB
```

builder stage 有 gcc 等編譯工具（安裝某些 Python 套件需要），runtime stage 不需要，所以第二個 stage 更小。

**為什麼需要 `ENV PYTHONPATH=/app/proto`？**

daemon.py 用 `import time_service_pb2` 引入 proto 生成的程式碼。但那個檔案在 `/app/proto/time_service_pb2.py`，Python 預設不會在 `/app/proto/` 找模組，所以要告訴它。

## 4.3 建置和跑容器

```bash
# 在本機建置（x86_64，開發用）
docker build -t time-daemon-local -f host/sw/time/Dockerfile .

# 啟動容器測試
docker run --rm -p 50052:50052 time-daemon-local
```

| 參數 | 說明 |
|------|------|
| `build` | 建置映像 |
| `-t time-daemon-local` | 給映像取名字 |
| `-f host/sw/time/Dockerfile` | 指定 Dockerfile 路徑 |
| `.` | Build context：把這個目錄的檔案送給 Docker daemon |
| `run` | 啟動容器 |
| `--rm` | 容器停止後自動刪除 |
| `-p 50052:50052` | 把開發機的 50052 port 對應到容器的 50052 port |

## 4.4 為什麼要 ARM64？

你的開發機是 x86_64（Intel/AMD CPU），Pi 5 是 ARM64（ARM CPU）。

程式在 x86_64 上編譯的，無法在 ARM64 上執行，反之亦然。

解決方式：cross-compilation（交叉編譯）

```bash
# 在開發機上建置 ARM64 映像
docker buildx build \
  --platform linux/arm64 \    # 目標平台：ARM64
  -t ghcr.io/.../time-daemon:latest \
  -f host/sw/time/Dockerfile \
  --push .                    # 直接推到 GHCR
```

`docker buildx` + QEMU（模擬 ARM64 指令集）讓 x86_64 機器能建置 ARM64 映像。

## 4.5 GHCR（GitHub Container Registry）

映像建置好後需要存放在 registry（映像倉庫），Pi 5 才能拉取。

```
開發機                    GHCR（雲端）                Pi 5
   │                          │                         │
   │── docker buildx --push ─►│                         │
   │                          │◄── k3s 拉取映像 ────────│
```

映像名稱格式：`ghcr.io/<使用者>/<倉庫>/<映像名>:<tag>`
你的：`ghcr.io/anguswooster/raspi-k8s/time-daemon:latest`

---

# Chapter 5：Kubernetes 操作實戰

## 5.1 Kubernetes 是什麼？

Kubernetes（K8s）是一個「容器管理平台」，你告訴它「我要跑什麼、跑幾個」，它負責：
- 在適合的機器上啟動容器
- 容器掛掉自動重啟
- 管理容器之間的網路
- 滾動更新（不停機升級）

## 5.2 核心概念（用你的專案說明）

```
k3s 叢集（Pi 5）
└── Namespace: aku-sw          ← 你的「命名空間」，隔離你的資源
    ├── Pod: time-daemon-xxxxx  ← 實際跑 daemon 的容器
    ├── Deployment: time-daemon ← 管理 Pod（確保 1 個 Pod 一直活著）
    └── Service: time-daemon    ← 開放 NodePort 30052，讓外部能連進來
```

**Pod**：K8s 最小執行單位，包含一個或多個容器。你的 time-daemon 容器跑在一個 Pod 裡。

**Deployment**：管理 Pod 的「老闆」，負責：
- 確保指定數量（replicas）的 Pod 一直存活
- Pod 掛掉時自動重建
- 滾動更新映像版本

**Service**：網路入口，讓流量能找到 Pod。Pod 重啟後 IP 會變，Service 提供穩定的入口點。

**Namespace**：邏輯隔離單位，你的所有資源都在 `aku-sw` namespace。

## 5.3 Manifest 檔案解析

### namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: aku-sw
```

告訴 K8s：「建立一個叫 `aku-sw` 的 namespace」。

### deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: time-daemon
  namespace: aku-sw
spec:
  replicas: 1                  # 維持 1 個 Pod
  selector:
    matchLabels:
      app: time-daemon         # 管理有這個 label 的 Pod
  template:
    metadata:
      labels:
        app: time-daemon       # Pod 的 label
    spec:
      imagePullSecrets:
        - name: ghcr-secret    # 拉取私有映像用的憑證
      containers:
        - name: time-daemon
          image: ghcr.io/anguswooster/raspi-k8s/time-daemon:latest
          ports:
            - containerPort: 50052
```

**Label 機制：**

```
Deployment.selector.matchLabels.app = "time-daemon"
         │
         └──► 找到 Pod.labels.app = "time-daemon"（這些 Pod 我來管）
                    │
                    └──► Service.selector.app = "time-daemon"（流量送到這些 Pod）
```

Deployment 和 Service 不直接引用 Pod 的 IP，而是透過 label 找到對應的 Pod。好處：Pod 重啟 IP 變了也沒關係，只要 label 不變，Service 就能找到它。

### service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: time-daemon
  namespace: aku-sw
spec:
  type: NodePort
  selector:
    app: time-daemon           # 把流量送到有這個 label 的 Pod
  ports:
    - protocol: TCP
      port: 50052              # 叢集內部用的 port
      targetPort: 50052        # 轉到 Pod 的哪個 port
      nodePort: 30052          # 外部連入的 port
```

## 5.4 kubectl 常用指令

**查看資源：**

```bash
# 查看所有 Pod（-n 指定 namespace）
kubectl get pods -n aku-sw

# 查看所有 Service
kubectl get service -n aku-sw

# 查看所有 namespace
kubectl get namespaces

# 查看所有節點（機器）
kubectl get nodes
```

**診斷問題：**

```bash
# 看 Pod 詳細狀態和事件（出問題第一個跑這個）
kubectl describe pod -n aku-sw <pod名稱>

# 看 Pod 的 log（daemon.py 的輸出）
kubectl logs -n aku-sw <pod名稱>

# 持續追蹤 log
kubectl logs -n aku-sw <pod名稱> -f
```

**如何取得 `<pod名稱>`？**

```bash
kubectl get pods -n aku-sw
# NAME                          READY   STATUS    RESTARTS   AGE
# time-daemon-7d9f8b-xk2p4      1/1     Running   0          5m
#                ^^^^^^^^^^^^
#                複製這個名稱
```

**套用/更新：**

```bash
# 套用 manifest 檔案
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/time/

# 強制重新部署（讓 K8s 拉取最新的 :latest 映像）
kubectl rollout restart deployment/time-daemon -n aku-sw

# 等待更新完成
kubectl rollout status deployment/time-daemon -n aku-sw
```

**刪除資源：**

```bash
# 刪除整個 namespace（裡面所有資源一起刪）
kubectl delete namespace aku-sw
```

## 5.5 Pod 狀態看懂它

```
NAME                     READY   STATUS             RESTARTS   AGE
time-daemon-7d9f8b-xk2p4 1/1     Running            0          5m
time-daemon-7d9f8b-abc12  0/1     Pending            0          30s
time-daemon-7d9f8b-def34  0/1     ImagePullBackOff   0          1m
time-daemon-7d9f8b-ghi56  0/1     CrashLoopBackOff   3          2m
```

| STATUS | 意思 | 怎麼排查 |
|--------|------|---------|
| `Running` | 正常運作 | 沒問題 |
| `Pending` | 等待被排程（映像拉取中，或資源不足） | `kubectl describe pod ...` 看 Events |
| `ImagePullBackOff` | 拉不到映像（映像不存在、私有映像沒設 secret） | 確認映像名稱、ghcr-secret 是否存在 |
| `CrashLoopBackOff` | 容器啟動後馬上崩潰，K8s 一直重試 | `kubectl logs ...` 看錯誤訊息 |

## 5.6 常見問題排查流程

```
kubectl get pods -n aku-sw 看到問題
         │
         ▼
kubectl describe pod -n aku-sw <名稱>
  看 Events 區塊（在輸出最下面）：
  - "Failed to pull image" → ImagePullBackOff，檢查 ghcr-secret
  - "Back-off restarting failed container" → CrashLoopBackOff
         │
         ▼
kubectl logs -n aku-sw <名稱>
  看 daemon.py 的輸出，找 Python 錯誤訊息
```

---

# Chapter 6：Ansible 自動化

## 6.1 Ansible 是什麼？

Ansible 是「自動化執行一連串指令」的工具。

沒有 Ansible：
```bash
kubectl apply -f k8s/namespace.yaml
read -s TOKEN && kubectl create secret docker-registry ghcr-secret ...
kubectl apply -f k8s/time/
kubectl get pods -n aku-sw
```
每次部署都要手動一個一個跑，容易忘記或跑錯順序。

有 Ansible：
```bash
ansible-playbook host/deploy/ansible/playbooks/deploy-time-daemon.yml \
  --vault-password-file ~/.vault_pass
```
一個指令，自動完成所有步驟。

## 6.2 Playbook 結構

```
Playbook
└── Play（在哪台機器上跑）
    ├── vars（變數定義）
    └── Tasks（步驟）
        ├── Task 1: 建立 namespace
        ├── Task 2: 建立 ghcr-secret
        ├── Task 3: 套用 Deployment
        ├── Task 4: 套用 Service
        └── Task 5: 等待 Pod Ready
```

## 6.3 你的 Playbook 解析

```yaml
- name: Deploy time-daemon to Pi 5 k3s
  hosts: localhost          # 在開發機本機執行（透過 kubeconfig 連到 k3s）
  connection: local         # 不需要 SSH，本機直接執行
  gather_facts: false       # 跳過收集機器資訊（加快執行）

  vars_files:
    - "{{ playbook_dir }}/../group_vars/all.yml"  # 載入加密的 PAT

  vars:
    kubeconfig: "{{ lookup('env', 'HOME') }}/.kube/config"
    k8s_namespace: aku-sw
    ghcr_username: AngusWooster
    manifest_dir: "{{ playbook_dir }}/../../../../k8s"
```

**`{{ }}` 是什麼？**

Ansible 用 `{{ 變數名 }}` 引用變數，執行時會替換成實際值：
- `{{ k8s_namespace }}` → `aku-sw`
- `{{ playbook_dir }}` → `/home/aku/aku/raspi-k8s/host/deploy/ansible/playbooks`

## 6.4 Ansible Vault：加密機密

GitHub PAT 是機密，不能明文存在檔案裡（否則 git history 裡永遠看得到）。

```
PAT（明文）
  → ansible-vault encrypt_string（用 vault 密碼加密）
  → $ANSIBLE_VAULT;1.1;AES256...（加密後的字串）
  → 存進 all.yml（可以進 git）

執行 playbook 時
  → Ansible 讀 ~/.vault_pass（vault 密碼）
  → 解密得到 PAT
  → 用 PAT 建立 K8s secret
```

**加密流程：**

```bash
# 1. 建立 vault 密碼（只做一次）
read -s VAULT_PASS && echo "$VAULT_PASS" > ~/.vault_pass
chmod 600 ~/.vault_pass

# 2. 加密 PAT
read -s GHCR_TOKEN
ansible-vault encrypt_string "$GHCR_TOKEN" \
  --vault-password-file ~/.vault_pass \
  --name ghcr_pat \
  > host/deploy/ansible/group_vars/all.yml
```

**`--name ghcr_pat`** 代表加密結果的變數名，playbook 裡用 `{{ ghcr_pat }}` 引用。

## 6.5 冪等性

Ansible 最重要的特性：**同一個 playbook 跑幾次，結果都一樣**。

```
第 1 次跑：namespace 不存在 → 建立 → changed
第 2 次跑：namespace 已存在 → 不動 → ok
第 3 次跑：namespace 已存在 → 不動 → ok
```

這讓你可以放心重複執行，不用擔心「是不是已經跑過了」。

---

# Chapter 7：整合——一次看懂整個系統

## 7.1 整體架構

```
raspi-k8s 專案
│
├── host/sw/time/           ← 服務程式碼
│   ├── daemon.py           ← gRPC server（跑在 Pi 5 的容器裡）
│   ├── client.py           ← gRPC client（從開發機呼叫）
│   ├── proto/              ← protobuf 生成的 Python 程式碼
│   │   ├── time_service.proto          ← API 合約定義
│   │   ├── time_service_pb2.py         ← 資料結構
│   │   └── time_service_pb2_grpc.py    ← gRPC stub/servicer
│   └── Dockerfile          ← 打包 daemon 成容器
│
├── k8s/                    ← Kubernetes manifest
│   ├── namespace.yaml      ← 建立 aku-sw namespace
│   └── time/
│       ├── deployment.yaml ← 讓 Pi 5 跑 time-daemon Pod
│       └── service.yaml    ← 開放 NodePort 30052
│
└── host/deploy/ansible/    ← 自動化部署
    ├── group_vars/all.yml  ← 加密的 GHCR PAT
    └── playbooks/deploy-time-daemon.yml  ← 部署 playbook
```

## 7.2 開發到部署的完整流程

```
Step 1: 寫程式
  修改 daemon.py 或 client.py

Step 2: 本機測試
  docker build -t time-daemon-local -f host/sw/time/Dockerfile .
  docker run --rm -p 50052:50052 time-daemon-local
  python host/sw/time/client.py  # 測試連線

Step 3: 建置 ARM64 映像並推到 GHCR
  docker buildx build --platform linux/arm64 \
    -t ghcr.io/anguswooster/raspi-k8s/time-daemon:latest \
    -f host/sw/time/Dockerfile --push .

Step 4: 部署到 Pi 5
  ansible-playbook host/deploy/ansible/playbooks/deploy-time-daemon.yml \
    --vault-password-file ~/.vault_pass

Step 5: 驗證
  kubectl get pods -n aku-sw          # 確認 Running
  kubectl logs -n aku-sw <pod名稱>    # 看 daemon 輸出
  bazel run //host/sw/time:client -- --host 192.168.1.185 --port 30052
```

## 7.3 一個請求的完整旅程

```
你在開發機執行：
  bazel run //host/sw/time:client -- --host 192.168.1.185 --port 30052

client.py 執行：
  1. get_time("192.168.1.185", 30052)
  2. grpc.insecure_channel("192.168.1.185:30052")  ← TCP 連線

網路傳輸：
  開發機:????  ──TCP──►  Pi 5:30052（NodePort）

K8s 轉發：
  Pi 5:30052  ──►  Service（aku-sw/time-daemon）  ──►  Pod:50052

daemon.py 執行（容器裡）：
  3. TimeServiceServicer.GetTime() 被呼叫
  4. time.time_ns() 取得當前時間
  5. 回傳 GetTimeResponse(timestamp=..., unix_seconds=..., ...)

回傳旅程（反向）：
  Pod:50052  ──►  Service  ──►  Pi 5:30052  ──TCP──►  開發機

client.py 收到回應：
  6. print_response(response)
  7. 印出 Timestamp, Unix time, Timezone, Hostname
```

## 7.4 出問題時的思考框架

**連不到服務？**

```
client 報 "Error: cannot reach 192.168.1.185:30052"
  │
  ├── 1. Pi 5 開著嗎？  →  ping 192.168.1.185
  │
  ├── 2. k3s 還在跑嗎？  →  ssh pi@192.168.1.185 "sudo kubectl get nodes"
  │
  ├── 3. Pod 在跑嗎？  →  kubectl get pods -n aku-sw
  │       ├── Pending → kubectl describe pod ... 看 Events
  │       ├── ImagePullBackOff → 確認 ghcr-secret 存在
  │       └── CrashLoopBackOff → kubectl logs ... 找錯誤
  │
  └── 4. Service 和 NodePort 對嗎？  →  kubectl get service -n aku-sw
```

**映像沒更新？**

```
改了 daemon.py 但 Pod 跑的還是舊版
  →  kubectl rollout restart deployment/time-daemon -n aku-sw
     （強制拉取最新 :latest 映像）
```

**Ansible 失敗？**

```
playbook 失敗
  →  ansible-playbook ... -vvv  （加 -vvv 看詳細錯誤）
  →  檢查 ~/.kube/config 是否指向 Pi 5
  →  確認 all.yml 裡的 ghcr_pat 是否只有一個（沒有重複 key）
```

---

## 快速參考卡

### 常用 kubectl 指令

```bash
kubectl get pods -n aku-sw                          # 看 Pod 狀態
kubectl get service -n aku-sw                       # 看 Service
kubectl get nodes                                   # 看節點
kubectl describe pod -n aku-sw <名稱>               # 詳細診斷
kubectl logs -n aku-sw <名稱>                       # 看 log
kubectl logs -n aku-sw <名稱> -f                    # 追蹤 log
kubectl apply -f k8s/                               # 套用所有 manifest
kubectl rollout restart deployment/time-daemon -n aku-sw  # 強制重新部署
kubectl delete namespace aku-sw                     # 刪除所有資源
```

### 常用 Docker 指令

```bash
docker build -t time-daemon-local -f host/sw/time/Dockerfile .   # 本機建置
docker run --rm -p 50052:50052 time-daemon-local                  # 本機執行
docker buildx build --platform linux/arm64 ... --push .           # ARM64 建置並推送
```

### 常用 Ansible 指令

```bash
# 部署
ansible-playbook host/deploy/ansible/playbooks/deploy-time-daemon.yml \
  --vault-password-file ~/.vault_pass

# 更換 PAT
read -s GHCR_TOKEN
ansible-vault encrypt_string "$GHCR_TOKEN" \
  --vault-password-file ~/.vault_pass \
  --name ghcr_pat \
  > host/deploy/ansible/group_vars/all.yml
```

### 連接服務

```bash
# 從開發機用 bazel 連
bazel run //host/sw/time:client -- --host 192.168.1.185 --port 30052

# 直接用 Python 連（venv 啟動後）
python host/sw/time/client.py --host 192.168.1.185 --port 30052
```
