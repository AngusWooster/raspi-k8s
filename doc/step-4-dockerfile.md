# Step 4：Dockerfile 與容器映像檔

## 本章目標

將 `daemon.py` 打包成 Docker 容器映像檔，讓你能夠：

- 在本機建置 ARM64 容器映像檔（適用於 Raspberry Pi 5）
- 理解 Dockerfile 每一行的用途
- 將映像檔推送到 GitHub Container Registry（GHCR）
- 為後續 Kubernetes 部署做好準備

---

## 背景知識：為什麼需要容器？

### 問題：「在我電腦跑得起來，在 Pi 上跑不起來」

直接把 `daemon.py` 複製到 Pi 上執行，會遇到：

- Python 版本不一樣
- 缺少 `grpcio`、`protobuf` 套件
- 路徑不一樣

**容器**把程式和它需要的環境（Python、套件、設定）打包成一個「映像檔（Image）」，在任何有 Docker/containerd 的機器上執行都一模一樣。

### Docker 基本概念

```
Dockerfile         →  docker build  →  Image（映像檔）  →  docker run  →  Container（容器）
（建置指令描述）                        （靜態的快照）                       （執行中的程式）
```

| 名詞 | 比喻 |
|------|------|
| Image | 光碟片（靜態） |
| Container | 播放中的光碟（執行中） |
| Dockerfile | 製作光碟片的說明書 |
| Registry | 雲端光碟倉庫（GHCR、DockerHub） |

### 為什麼特別需要 ARM64？

Raspberry Pi 5 的 CPU 架構是 **ARM64**（又叫 aarch64），而一般開發用的筆電是 **x86_64**（又叫 amd64）。  
這兩種架構的機器碼不相容，所以需要特別建置 ARM64 版本的映像檔。

```
開發機 (x86_64)                   Raspberry Pi 5 (ARM64)
┌──────────────────────┐           ┌──────────────────────┐
│  docker buildx build │ ──push──► │  containerd pull     │
│  --platform          │           │  image (ARM64)       │
│  linux/arm64         │           │  docker run ...      │
└──────────────────────┘           └──────────────────────┘
        GHCR (ghcr.io)
```

`docker buildx` 搭配 QEMU 模擬器，讓你在 x86 機器上交叉編譯出 ARM64 映像檔。

---

## 本章涉及的檔案

```
raspi-k8s/
├── host/sw/time/
│   └── Dockerfile              ← 本章新增
├── .dockerignore               ← 本章新增
└── doc/
    └── step-4-dockerfile.md   ← 本文件
```

---

## Section 1：容器需要哪些套件？

容器只是一個獨立的執行環境，它**不知道你開發機上裝了什麼**，所有依賴都必須在 Dockerfile 裡明確安裝。

### runtime 套件 vs 開發工具

本專案把套件分成兩個檔案：

| 檔案 | 用途 | 要進容器？ |
|------|------|----------|
| `requirements.txt` | daemon 執行時需要的套件 | ✅ 是 |
| `requirements-dev.txt` | 只有開發機才需要的工具 | ❌ 否 |

### requirements.txt 套件說明

```
grpcio==1.81.1        ← gRPC 核心函式庫，daemon.py 用它建立 server
grpcio-tools==1.81.1  ← protoc 編譯工具（含 gRPC plugin）
protobuf==6.33.6      ← Protocol Buffer 序列化函式庫，讀寫 message 用
setuptools            ← Python 打包工具，grpcio-tools 安裝時需要
```

**為什麼容器需要 `grpcio-tools`？**

`grpcio-tools` 包含 `protoc`，但容器裡**不需要重新編譯 proto**——`.proto` 早已在開發機上生成好並提交到 git。  
然而 `grpcio-tools` 同時帶入了 `grpcio` 的 C extension，有些版本的 `grpcio` 需要它。  
實務上可以只保留 `grpcio` + `protobuf`，但為簡化維護，此專案同版本一起安裝。

### requirements-dev.txt 套件說明（不進容器）

```
mypy-protobuf   ← 產生 .pyi 型別提示，給 IDE 使用（Pyright / mypy）
grpc-stubs      ← grpc 型別標記（如 grpc.Channel、grpc.RpcError），給 IDE 用
```

這兩個套件**只讓 IDE 更聰明**，daemon 執行時完全用不到，所以不打包進容器。

### 版本鎖定的重要性

`requirements_lock.txt` 是由 `pip-compile` 從 `requirements.txt` 產生的**完整鎖定檔**，包含所有間接依賴的精確版本。  
Dockerfile 裡安裝的是 `requirements.txt`（不鎖定間接依賴），若要讓容器環境和開發機**完全一致**，可改為：

```dockerfile
COPY requirements_lock.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements_lock.txt
```

本專案目前用 `requirements.txt` 即可；正式生產環境建議換成 `requirements_lock.txt`。

---

## Section 2：.dockerignore

`.dockerignore` 告訴 Docker 在 `COPY . .` 時**排除**哪些檔案，避免把不必要的大檔案（如 `.venv`、`bazel-*` 快取）複製進映像檔，縮短建置時間。

```
.venv/
bazel-*
*.pyc
__pycache__/
.git/
doc/
scripts/
```

類比：就像 `.gitignore` 告訴 Git 不要追蹤某些檔案，`.dockerignore` 告訴 Docker 不要打包某些檔案。

---

## Section 2：Dockerfile 結構——多階段建置

### 為什麼用多階段建置（Multi-stage Build）？

```
單階段（不推薦）          多階段（推薦）
┌─────────────────┐       ┌──────────────┐   ┌──────────────┐
│ python:3.11     │       │ builder 階段  │   │ runtime 階段  │
│ + pip install   │       │ python:3.11  │──►│ python:slim  │
│ + 編譯工具       │       │ pip install  │   │ 只複製需要的  │
│ = 大映像檔 ~1GB │       │ 編譯工具     │   │ = 小映像檔   │
└─────────────────┘       └──────────────┘   └──────────────┘
                                                    ~200MB
```

`builder` 階段負責安裝套件（包含編譯工具），`runtime` 階段只複製安裝好的 Python 套件，不含編譯工具，映像檔更小，部署更快。

---

## Section 3：完整 Dockerfile 解析

```dockerfile
# ── builder 階段：安裝 Python 套件 ──────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# 只複製 requirements 先安裝，利用 Docker layer cache：
# 只要 requirements.txt 沒變，這層不會重新安裝，build 更快
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── runtime 階段：最終映像檔 ─────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 從 builder 複製已安裝的套件到系統路徑
COPY --from=builder /install /usr/local

# 讓 Python 能找到 proto/ 子目錄裡的模組（不需要寫 from proto import ...）
# Bazel 透過 BUILD.bazel 的 imports=["."] 自動做這件事；
# Docker 沒有 Bazel，所以要手動設定 PYTHONPATH
ENV PYTHONPATH=/app/proto

# 複製程式碼（proto 生成的 .py 和 daemon.py）
COPY host/sw/time/proto/time_service_pb2.py      proto/
COPY host/sw/time/proto/time_service_pb2_grpc.py proto/
COPY host/sw/time/daemon.py                       .

# gRPC 服務監聽的 port（文件用，不影響實際行為）
EXPOSE 50052

# 容器啟動時執行的命令
# ENTRYPOINT 是固定指令；CMD 是預設參數（可被 docker run 覆蓋）
ENTRYPOINT ["python", "daemon.py"]
```

### 逐行重點說明

| 指令 | 說明 |
|------|------|
| `FROM python:3.11-slim AS builder` | 以官方 Python slim 映像為基礎，命名此階段為 `builder` |
| `WORKDIR /build` | 設定工作目錄，之後的 `COPY`、`RUN` 都在此目錄執行 |
| `COPY requirements.txt .` | 先只複製 requirements，不複製全部程式碼 |
| `pip install --prefix=/install` | 安裝套件到 `/install`，之後可整包複製到 runtime 階段 |
| `--no-cache-dir` | 不存 pip 快取，避免浪費空間 |
| `COPY --from=builder /install /usr/local` | 從 builder 階段複製套件到 runtime 階段 |
| `ENV PYTHONPATH=/app/proto` | 把 proto 目錄加進 Python 模組搜尋路徑（Bazel 用 `imports=["."]` 做同樣的事） |
| `EXPOSE 50052` | 宣告容器使用此 port（只是文件標記，K8s 的 Service 才真正決定開放） |
| `ENTRYPOINT ["python", "daemon.py"]` | 容器啟動時執行 `python daemon.py` |

### EXPOSE 和 NodePort 的關係

`EXPOSE 50052` 只是文件標記，不會真正開放任何 port。實際的 port 流向分三層：

```
外部（你的開發機）    Node（Raspberry Pi）    Pod（容器）

client:任意 port ──► Pi IP : 30052 ──► Service : 50052 ──► daemon : 50052
                     （NodePort）       （ClusterIP）        （EXPOSE）
```

| Port | 設定位置 | 說明 |
|------|----------|------|
| `EXPOSE 50052` | Dockerfile | daemon 在容器內監聽的 port，純文件標記 |
| `targetPort: 50052` | K8s Service | Service 要把流量轉到容器的哪個 port（必須和 EXPOSE 一致） |
| `port: 50052` | K8s Service | 叢集內部其他 Pod 連此 Service 用的 port |
| `nodePort: 30052` | K8s Service | 從 Pi 外部連進來的 port（K8s 規定只能 30000–32767） |

**NodePort 為什麼不直接用 50052？**  
K8s 規定 NodePort 範圍是 30000–32767，避免和 Linux 系統常用 port（22 SSH、80 HTTP、443 HTTPS）衝突。  
所以從外部連時用 30052，進入 K8s 叢集後再轉成 50052 到達容器。

這個 Service 設定會在 Step 5（Kubernetes Manifests）實際寫出來。

### PYTHONPATH 是什麼？

Python 載入模組時，會依序搜尋 `sys.path` 裡的目錄：

```
daemon.py 執行 import time_service_pb2
  → Python 搜尋 sys.path = ['/app', '/usr/local/lib/...', ...]
  → 找不到！因為 time_service_pb2.py 在 /app/proto/，不在 /app/

設了 ENV PYTHONPATH=/app/proto 之後：
  → Python 搜尋 sys.path = ['/app/proto', '/app', '/usr/local/lib/...', ...]
  → 找到了！/app/proto/time_service_pb2.py
```

### ENTRYPOINT vs CMD 的區別

```bash
# ENTRYPOINT 固定，CMD 是預設參數
ENTRYPOINT ["python", "daemon.py"]
CMD []

# docker run 時傳入額外參數，會附加到 ENTRYPOINT 後面：
docker run time-daemon --port 50099
# 等於執行：python daemon.py --port 50099

# 若用 CMD 而非 ENTRYPOINT，docker run 傳的參數會取代整個 CMD
```

---

## Section 4：本機測試完整步驟（x86）

在這個階段，我們在開發機上建置 x86 版本的映像檔，先驗證容器能正常運作，再進行 ARM64 的交叉編譯。

### 步驟 1：確認目前位置

**所有 docker 指令都要在專案根目錄執行**，因為 Dockerfile 裡 `COPY host/sw/time/...` 是相對根目錄的路徑。如果在錯誤的目錄下執行，`COPY` 會找不到檔案。

```bash
cd ~/aku/raspi-k8s
pwd
# 應該顯示：/home/aku/aku/raspi-k8s
```

### 步驟 2：建置映像檔

```bash
docker build \
  -t time-daemon-local \
  -f host/sw/time/Dockerfile \
  .
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker build` | 根據 Dockerfile 建置映像檔的指令 |
| `-t time-daemon-local` | `-t` 是 `--tag` 的縮寫，給映像檔取名。格式為 `名稱:版本`，省略版本預設為 `latest`，所以這等於 `time-daemon-local:latest` |
| `-f host/sw/time/Dockerfile` | `-f` 是 `--file` 的縮寫，指定 Dockerfile 的路徑。若不加，Docker 預設找當前目錄的 `./Dockerfile` |
| `.`（最後的點） | **Build context（建置上下文）**：告訴 Docker 哪個目錄是根目錄。Dockerfile 裡所有 `COPY` 指令的來源路徑都相對於這個目錄。`.` 代表目前所在目錄（專案根目錄），所以 `COPY host/sw/time/daemon.py .` 就是從 `專案根目錄/host/sw/time/daemon.py` 複製 |

**第一次 build 輸出範例（慢，約 1-2 分鐘）：**

```
[+] Building 90.3s (10/10) FINISHED
 => [builder 1/3] FROM docker.io/library/python:3.11-slim   ← 從 DockerHub 下載基礎映像
 => [builder 2/3] COPY requirements.txt .                   ← 複製 requirements
 => [builder 3/3] RUN pip install ...                        ← 最慢的步驟，安裝套件
 => [stage-2 1/4] COPY --from=builder /install /usr/local   ← 從 builder 複製套件
 => [stage-2 2/4] COPY host/sw/time/proto/...               ← 複製 proto 檔
 => [stage-2 3/4] COPY host/sw/time/daemon.py .             ← 複製主程式
```

**第二次 build（只改了 daemon.py，快很多）：**

```
[+] Building 1.2s (10/10) FINISHED
 => CACHED [builder 3/3] RUN pip install ...   ← [CACHED] 代表這層已快取，直接跳過
 => [stage-2 3/4] COPY host/sw/time/daemon.py  ← 只有這層重新執行
```

這就是為什麼要先 `COPY requirements.txt`，再 `COPY daemon.py`：把**很少變動**的套件安裝放前面，讓它被快取；**常改動**的程式碼放後面。只要 `requirements.txt` 沒改，套件安裝那層永遠是 `[CACHED]`，rebuild 只需幾秒。

### 步驟 3：啟動容器

```bash
docker run --rm -p 50052:50052 time-daemon-local
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker run` | 從映像檔啟動一個容器（執行實例）的指令 |
| `--rm` | 容器停止後自動刪除。不加的話，停掉的容器會留在磁碟佔空間，需要手動執行 `docker rm <id>` 清除 |
| `-p 50052:50052` | `-p` 是 `--publish` 的縮寫，Port mapping（連接埠對應）。格式為 `本機port:容器port`。容器有自己的獨立網路，預設外面無法連進去。這個參數把本機的 50052 連到容器內的 50052 |
| `time-daemon-local` | 要啟動的映像檔名稱（就是剛才 `-t` 指定的名稱） |

**Port mapping 示意圖：**

```
你的開發機                    容器（獨立網路空間）
┌──────────────────────┐      ┌──────────────────────┐
│  bazel run client    │      │  daemon.py           │
│  → localhost:50052   │─────►│  監聽 [::]:{50052}   │
│                      │◄─────│  回傳時間資料         │
└──────────────────────┘      └──────────────────────┘
      -p 50052:50052
（本機 50052 → 容器 50052）
```

沒有 `-p` 的話，容器內的 port 從外面完全看不到，連線會被拒絕。

### 步驟 4：另開終端測試連線

容器跑起來後，**不要關閉它**，另開一個終端視窗執行 client：

```bash
cd ~/aku/raspi-k8s
bazel run //host/sw/time:client -- --host localhost --port 50052
```

預期輸出：

```
Timestamp  : 2026-06-20T10:41:58.891022+00:00
Unix time  : 1781952118.891017650
Timezone   : UTC           ← 容器內預設 UTC（和開發機的 CST 不同）
Hostname   : a3f2c1b8d9e0  ← 容器 ID（不是你的電腦名稱）
```

### 步驟 5：停止容器

回到執行 `docker run` 的終端，按 `Ctrl+C`。因為加了 `--rm`，容器停止後會自動刪除。

---

## Section 5：ARM64 建置與推送到 GHCR

本機 x86 測試通過後，才進行這個步驟。Raspberry Pi 5 是 ARM64 架構，需要特別的交叉編譯工具。

### 步驟 1：確認 builder 是否支援 ARM64

先查看目前有哪些 builder 及其支援的平台：

```bash
docker buildx ls
```

查看特定 builder 的詳細平台列表：

```bash
docker buildx inspect <builder名稱>
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker buildx ls` | 列出所有 builder 實例，顯示名稱、driver、狀態與支援平台 |
| `docker buildx inspect` | 顯示指定 builder 的完整資訊，包含每個節點支援的所有平台 |
| `<builder名稱>` | 要查看的 builder 名稱，從 `docker buildx ls` 取得 |

**正常的輸出應包含 `linux/arm64`：**

```
Platforms: linux/amd64, linux/arm64, linux/arm/v7, ...
```

**如果 `Platforms` 只有 `linux/amd64` 系列，沒有 `linux/arm64`**，代表 QEMU 未正確安裝，需要執行下面的步驟重新設定。

---

### 步驟 2：安裝 QEMU ARM64 支援（若 builder 缺少 arm64 才需要）

`docker build` 預設只能建置和你電腦相同架構（x86）的映像。要建 ARM64，需要 `docker buildx` 搭配 QEMU 模擬器。

**什麼是 QEMU？**  
QEMU 是一個 CPU 模擬器。透過 Linux 核心的 `binfmt_misc` 機制，系統看到 ARM64 執行檔時，會自動呼叫 QEMU 去模擬執行，讓 x86 機器能「假裝」是 ARM64。`docker buildx` 就是利用這個機制在 x86 上執行 ARM64 的建置步驟。

**安裝 QEMU binfmt handler：**

```bash
docker run --privileged --rm tonistiigi/binfmt --install all
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker run` | 啟動容器 |
| `--privileged` | 給容器最高權限，讓它能修改 Linux 核心設定（安裝 binfmt handler 需要寫入 `/proc/sys/fs/binfmt_misc`，普通容器沒有這個權限） |
| `--rm` | 執行完自動刪除這個一次性的安裝容器 |
| `tonistiigi/binfmt` | 官方維護的 QEMU binfmt 安裝工具映像 |
| `--install all` | 安裝所有支援架構的 handler（ARM64、ARM32、RISC-V、s390x 等） |

**刪除舊 builder，重新建立（讓它讀取到新安裝的 QEMU）：**

```bash
docker buildx rm multiarch-builder
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker buildx rm` | 刪除指定的 builder 實例 |
| `multiarch-builder` | 要刪除的 builder 名稱（用你的 builder 實際名稱替換） |

```bash
docker buildx create --name multiarch-builder --use --driver docker-container
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker buildx create` | 建立一個新的 builder 實例 |
| `--name multiarch-builder` | 給 builder 取名，方便管理與切換 |
| `--use` | 建立後立即切換為目前使用的 builder |
| `--driver docker-container` | 使用 `docker-container` driver，在獨立容器中執行 BuildKit，才能支援多平台建置（預設的 `docker` driver 不支援多平台） |

**啟動 builder 並確認平台支援：**

```bash
docker buildx inspect --bootstrap
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker buildx inspect` | 顯示目前使用中的 builder 詳細資訊 |
| `--bootstrap` | 確保 builder 已啟動並就緒（第一次使用時會下載 BuildKit daemon 元件） |

執行後確認 `linux/arm64` 出現在平台列表：

```
Platforms: linux/amd64, linux/arm64, linux/arm/v7, ...
```

### 步驟 2：取得 GitHub PAT

推送映像到 GHCR 需要先登入，登入需要 GitHub PAT（Personal Access Token，個人存取金鑰）。

1. 前往 [GitHub](https://github.com) → 右上角頭像 → **Settings**
2. 左側選單最底部 → **Developer settings**
3. **Personal access tokens** → **Classic tokens** → **Generate new token**
4. 勾選 **`write:packages`**（會自動帶 `read:packages`）
5. 點 **Generate token**，複製產生的 token（只會顯示一次）

> **Classic vs Fine-grained**：推薦用 Classic，只需勾一個權限即可。Fine-grained token 的 package 權限需要綁定特定 repository，設定較繁瑣。

### 步驟 3：登入 GHCR

**⚠️ 安全注意**：不要直接把 token 寫在指令裡，例如 `echo ghp_xxxx | docker login ...`，這樣 token 會被記錄在 shell history（`~/.zsh_history` 或 `~/.bash_history`），別人可以查到。

改用 `read -s` 安全輸入：

```bash
read -s TOKEN && echo $TOKEN | docker login ghcr.io -u AngusWooster --password-stdin
```

**參數說明：**

| 指令／參數 | 說明 |
|-----------|------|
| `read` | shell 內建指令，從鍵盤讀取一行輸入，存入變數 |
| `-s` | silent 模式，輸入時**不顯示任何字元**（包含 `*`），token 不會出現在螢幕上，也不會進 history |
| `TOKEN` | 變數名稱，輸入的內容存在這裡 |
| `&&` | 前一個指令成功才執行下一個（`read` 讀到內容後，才執行 `docker login`） |
| `echo $TOKEN` | 把變數 `TOKEN` 的內容輸出到 stdout |
| `\|`（pipe） | 把前一個指令的 stdout 接到下一個指令的 stdin |
| `docker login ghcr.io` | 登入指定的 Container Registry（`ghcr.io` 是 GitHub Container Registry 的網域） |
| `-u AngusWooster` | `-u` 是 `--username`，指定 GitHub 登入帳號 |
| `--password-stdin` | 從 stdin 讀取密碼，不從指令參數讀取（避免 token 出現在 process list 和 history） |

執行後游標會停住等你輸入，把 token 貼上按 Enter，看到 `Login Succeeded` 代表成功。

### 步驟 4：建置 ARM64 並推送

```bash
docker buildx build \
  --platform linux/arm64 \
  -t ghcr.io/anguswooster/raspi-k8s/time-daemon:latest \
  -f host/sw/time/Dockerfile \
  --push \
  .
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker buildx build` | 使用 buildx 建置，支援多平台（`docker build` 只能建本機架構） |
| `--platform linux/arm64` | 指定目標架構，`linux/arm64` 就是 Raspberry Pi 5 的架構 |
| `-t ghcr.io/anguswooster/raspi-k8s/time-daemon:latest` | 完整的映像名稱。格式：`Registry網域/帳號/專案/映像名:版本`。GHCR 的格式固定是 `ghcr.io/GitHub帳號/...` |
| `-f host/sw/time/Dockerfile` | 指定 Dockerfile 路徑 |
| `--push` | build 完成後自動推送到 Registry（一般的 `docker build` 不支援這個選項） |
| `.` | Build context，同 Section 4 步驟 2 的說明 |

**注意**：`--push` 的映像不會留在本機（ARM64 映像無法在 x86 上直接執行）。

### 步驟 5：確認推送成功

前往 `https://github.com/AngusWooster?tab=packages` 確認 `raspi-k8s/time-daemon` 出現，點進去可以看到 `linux/arm64` 的 tag。

---

## Section 6：映像版本策略

每次 `docker buildx build` 都要給映像打 tag，tag 是識別一個映像的標籤。

| Tag | 範例 | 用途 |
|-----|------|------|
| `latest` | `time-daemon:latest` | 最新版，每次推送都覆蓋，適合開發測試 |
| 語意化版本 | `time-daemon:v1.0.0` | 固定版本號，不會被覆蓋，適合生產環境部署 |
| git commit | `time-daemon:sha-abc1234` | 對應 git commit，可精確追蹤是哪次程式碼產生的映像 |

同一個 build 可以同時打多個 tag（加多個 `-t`）：

```bash
docker buildx build \
  --platform linux/arm64 \
  -t ghcr.io/anguswooster/raspi-k8s/time-daemon:latest \
  -t ghcr.io/anguswooster/raspi-k8s/time-daemon:v1.0.0 \
  -f host/sw/time/Dockerfile \
  --push \
  .
```

---

## Section 7：常用 docker 指令速查

### 查看映像與容器狀態

```bash
# 列出本機所有映像檔（名稱、tag、大小、建立時間）
docker images

# 列出執行中的容器
docker ps

# 列出所有容器，包含已停止的
docker ps -a
```

**`docker ps` 欄位說明：**

| 欄位 | 說明 |
|------|------|
| `CONTAINER ID` | 容器的唯一 ID（daemon.py 裡 `socket.gethostname()` 回傳的就是這個） |
| `IMAGE` | 從哪個映像啟動的 |
| `STATUS` | `Up 5 minutes`（執行中）/ `Exited (0)`（正常結束）/ `Exited (1)`（錯誤結束） |
| `PORTS` | Port mapping，如 `0.0.0.0:50052->50052/tcp` |

### 查看容器 log

```bash
docker logs <container_id>

# 持續追蹤 log（類似 tail -f）
docker logs -f <container_id>
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker logs` | 顯示容器的標準輸出（stdout）和標準錯誤（stderr）的歷史記錄 |
| `<container_id>` | 容器 ID，從 `docker ps` 取得，可以只輸入前幾碼（如 `a3f2`） |
| `-f` | `--follow`，持續追蹤新 log，按 `Ctrl+C` 停止 |

### 進入執行中的容器（除錯用）

```bash
docker exec -it <container_id> bash
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `docker exec` | 在**已執行中**的容器裡執行一個額外的指令 |
| `-i` | `--interactive`，保持 stdin 開啟，讓你可以輸入 |
| `-t` | `--tty`，分配一個虛擬終端（沒有這個的話，終端顯示會不正常） |
| `<container_id>` | 目標容器 ID |
| `bash` | 要在容器裡執行的指令（開啟一個 bash shell，讓你可以在容器內部操作） |

進入容器後可以執行：

```bash
# 確認 Python 和套件版本
python --version
pip list | grep grpcio

# 確認 PYTHONPATH 設定
echo $PYTHONPATH

# 確認程式碼和 proto 檔在正確位置
ls /app/
ls /app/proto/

# 離開容器
exit
```

### 清理指令

```bash
# 刪除指定映像檔（映像有容器在使用中時無法刪除）
docker rmi time-daemon-local

# 強制刪除（即使有容器在使用）
docker rmi -f time-daemon-local

# 刪除所有已停止的容器、沒有 tag 的映像、未使用的網路（釋放磁碟空間）
docker system prune
```

---

## 本章重點回顧

| 概念 | 說明 |
|------|------|
| **多階段建置** | 分 builder / runtime 兩階段，最終映像不含編譯工具，體積更小 |
| **Layer Cache** | 不常變的指令（pip install）放前面，常改的（COPY daemon.py）放後面，加速 rebuild |
| **PYTHONPATH** | 告訴 Python 去哪裡找模組；Bazel 用 `imports=["."]` 自動做，Docker 需手動設定 |
| **EXPOSE** | 純文件標記，不會真正開放 port；`docker run -p` 才真正做 port mapping |
| **-p（port mapping）** | 把本機 port 連到容器內部 port，容器預設是隔離網路 |
| **docker buildx** | 支援交叉編譯（在 x86 建 ARM64 映像），搭配 QEMU 模擬器運作 |
| **--push** | buildx 獨有選項，build 完直接推送到 Registry |
| **GHCR** | GitHub 提供的免費 Container Registry，映像名稱格式 `ghcr.io/帳號/...` |

---

## 下一步

Step 5：Kubernetes Manifests — 定義 `Deployment`、`Service`，把映像部署到 k3s 叢集。
