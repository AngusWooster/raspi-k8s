# raspi-k8s 系統設計文件

## 學習目標

本專案的目的是透過實作，完整學習以下技術鏈：

| 目標 | 說明 |
|------|------|
| **Bazel + Python** | 使用 Bazel 建置 Python 專案，包含 proto 程式碼產生 |
| **gRPC 服務開發** | 撰寫 Python gRPC server (daemon) 與 client |
| **K8s Deployment / Job** | 了解不同 K8s 資源類型的使用場景 |
| **Ansible 自動部署** | 將映像建置、推送、kubectl apply 整合成一條指令 |
| **叢集內 Client 存取** | 學習如何在 K8s 叢集內部，或從外部透過 Service 存取 Pod 上的 gRPC 服務 |

---

## 環境規格

| 項目 | 值 |
|------|----|
| 硬體 | Raspberry Pi 5（單節點，全新） |
| K8s 發行版 | k3s（輕量，適合 Pi） |
| K8s namespace | `aku-sw` |
| Container Registry | GitHub GHCR — `ghcr.io/anguswooster` |
| GitHub | [github.com/AngusWooster/raspi-k8s](https://github.com/AngusWooster/raspi-k8s) |
| 開發機 | x86 Linux（cross-compile ARM64 映像） |

---

## 整體架構

```
開發機 (x86 Linux)
├── Bazel build      → Python binary + proto 程式碼
├── docker buildx    → ARM64 映像 (ghcr.io/anguswooster/aku-sw/<name>:<tag>)
├── docker push      → GitHub GHCR
└── ansible-playbook → Raspberry Pi 5
                            │
                            ▼
              Raspberry Pi 5 — k3s (單節點叢集)
              ┌──────────────────────────────────────┐
              │  namespace: aku-sw                   │
              │                                      │
              │  hello-daemon  Pod  NodePort: 30051  │
              │  time-daemon   Pod  NodePort: 30052  │
              │  sysmon-daemon Pod  NodePort: 30053  │
              └──────────────────────────────────────┘
                            ▲
                  gRPC client（開發機或叢集內）
                  grpc://<Pi-IP>:30052
```

---

## 規劃中的服務（sw/ 底下的 daemon）

| Daemon | 目錄 | 說明 | gRPC Port | NodePort | K8s 資源 | 開發狀態 |
|--------|------|------|-----------|----------|----------|----------|
| **hello-world** | `host/sw/hello/` | 最簡單的 echo 服務，驗證整套建置流程 | 50051 | 30051 | Deployment | 待開始 |
| **time** | `host/sw/time/` | 讀取 raspi 系統時間，client 透過 gRPC 查詢 | 50052 | 30052 | Deployment | **進行中** |
| **sysmon** | `host/sw/sysmon/` | 回傳 CPU / 記憶體 / 溫度 | 50053 | 30053 | Deployment | 待規劃 |

> 每個 daemon 都有對應的 **client** 工具，以及獨立的 K8s Service（NodePort）與 Ansible role。

---

## 專案目錄結構

```
raspi-k8s/
├── MODULE.bazel                         # Bazel bzlmod 入口
├── BUILD.bazel                          # 根 BUILD (pip requirements)
├── .bazelrc                             # Bazel 建置參數
├── .bazelversion                        # 固定 Bazel 版本
├── .gitignore
├── requirements.txt                     # pip 直接依賴（所有服務共用）
├── requirements_lock.txt                # pip 鎖定版本（pip-compile 產生）
├── system_design.md                     # 本文件
│
├── tools/
│   ├── BUILD.bazel
│   └── gen_proto.py                     # Bazel genrule 用的 protoc 包裝工具
│
├── host/
│   └── sw/                              # 所有軟體服務放這裡
│       │
│       ├── hello/                       # [服務 1] Hello World daemon
│       │   ├── BUILD.bazel
│       │   ├── daemon.py
│       │   ├── client.py
│       │   ├── Dockerfile
│       │   └── proto/
│       │       ├── BUILD.bazel
│       │       └── hello_service.proto
│       │
│       ├── time/                        # [服務 2] Time daemon（目前進行中）
│       │   ├── BUILD.bazel
│       │   ├── daemon.py                # gRPC server — 回傳系統時間
│       │   ├── client.py                # gRPC client — CLI 查詢工具
│       │   ├── Dockerfile               # ARM64 容器映像
│       │   └── proto/
│       │       ├── BUILD.bazel
│       │       └── time_service.proto
│       │
│       └── sysmon/                      # [服務 3] System Monitor daemon
│           ├── BUILD.bazel
│           ├── daemon.py
│           ├── client.py
│           ├── Dockerfile
│           └── proto/
│               ├── BUILD.bazel
│               └── sysmon_service.proto
│
├── k8s/
│   ├── namespace.yaml                   # namespace: aku-sw
│   ├── hello/
│   │   ├── deployment.yaml
│   │   └── service.yaml                 # NodePort 30051
│   ├── time/
│   │   ├── deployment.yaml
│   │   └── service.yaml                 # NodePort 30052
│   └── sysmon/
│       ├── deployment.yaml
│       └── service.yaml                 # NodePort 30053
│
└── ansible/
    ├── inventory/
    │   └── hosts.yml                    # Pi 5 的 IP / hostname
    ├── group_vars/
    │   └── all.yml                      # registry, namespace, image tag 等
    ├── roles/
    │   ├── build_image/                 # docker buildx build（ARM64）
    │   ├── push_image/                  # docker push to GHCR
    │   └── k8s_deploy/                  # kubectl apply
    └── playbooks/
        ├── deploy_time.yml              # 部署 time daemon
        ├── deploy_hello.yml             # 部署 hello daemon
        ├── deploy_sysmon.yml            # 部署 sysmon daemon
        └── deploy_all.yml               # 一次部署全部
```

---

## gRPC API 設計

### time_service.proto（目前進行中）

```proto
syntax = "proto3";
package time_service;

service TimeService {
  rpc GetTime (GetTimeRequest) returns (GetTimeResponse);
}

message GetTimeRequest {}

message GetTimeResponse {
  string timestamp   = 1;  // ISO 8601 (UTC)
  int64 unix_seconds = 2;
  int32 unix_nanos   = 3;
  string timezone    = 4;  // 主機本機時區
  string hostname    = 5;  // Pod 名稱
}
```

### Bazel 建置流程（以 time 為例）

```
host/sw/time/proto/time_service.proto
        │
        │  [Bazel genrule] tools/gen_proto.py
        ▼
time_service_pb2.py + time_service_pb2_grpc.py
        │
        │  [py_library :time_service_proto]
        ├──► [py_binary :daemon]  → daemon.py
        └──► [py_binary :client]  → client.py
                    │
                    │  [docker buildx --platform linux/arm64]
                    ▼
         ghcr.io/anguswooster/aku-sw/time-daemon:latest
                    │
                    │  [ansible-playbook deploy_time.yml]
                    ▼
         Pi 5 k3s — namespace aku-sw — time-daemon Deployment
```

---

## K8s 資源類型說明

| 資源 | 使用場景 | 本專案用途 |
|------|----------|-----------|
| `Namespace` | 隔離資源群組 | `aku-sw` — 所有服務放在此 namespace |
| `Deployment` | 長期運行的服務，支援滾動更新 | 三個 daemon 都使用 Deployment |
| `Service` (NodePort) | 讓叢集外部能存取 Pod | 每個 daemon 一個，Port 範圍 30051–30053 |
| `Job` | 一次性任務，執行完即結束 | Phase 4：定時備份、資料匯出 |
| `CronJob` | 定時執行的 Job | Phase 4：學習 Job 與 CronJob 差異 |
| `ConfigMap` | 注入設定（port、timezone 等） | daemon 設定參數 |

### 叢集內 DNS 存取方式

```
# 叢集內 client 存取 time daemon：
time-service.aku-sw.svc.cluster.local:50052

# 格式：<service-name>.<namespace>.svc.cluster.local:<port>
```

### 叢集外（開發機）存取方式

```
# 透過 NodePort 直接存取（Pi 5 IP + NodePort）
grpc://<Pi-5-IP>:30052

# 或用 kubectl port-forward（不需 NodePort）
kubectl port-forward -n aku-sw svc/time-service 50052:50052
```

---

## 開發環境需求

| 工具 | 最低版本 | 用途 |
|------|----------|------|
| Bazel (Bazelisk) | 7.x | 建置系統 |
| Python | 3.11 | 程式語言 |
| pip-tools | 7.x | 產生 requirements_lock.txt |
| Docker + Buildx | 24.x | 建置 ARM64 映像 |
| kubectl | 1.28+ | 套用 K8s 清單 |
| Ansible | 2.15+ | 自動化部署 |
| git | 2.x | 版本控制 |

---

## 安裝步驟

### 1. 安裝 Bazel（使用 Bazelisk）

```bash
# Bazelisk 會自動根據 .bazelversion 下載正確的 Bazel 版本
curl -Lo /usr/local/bin/bazel \
  https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64
chmod +x /usr/local/bin/bazel

bazel version
```

### 2. 安裝 Python 3.11 與 pip-tools

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip
pip install pip-tools
```

### 3. 產生 requirements_lock.txt

```bash
# 每次修改 requirements.txt 後需重新執行
pip-compile requirements.txt -o requirements_lock.txt
```

### 4. 安裝 Docker Buildx（ARM64 cross-compile）

```bash
# 啟用 QEMU（讓 x86 機器可以 build ARM64 映像）
docker run --privileged --rm tonistiigi/binfmt --install arm64

# 建立 buildx builder
docker buildx create --name raspi-builder --use
docker buildx inspect --bootstrap
```

### 5. 安裝 kubectl

```bash
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/
```

### 6. 安裝 Ansible

```bash
pip install ansible
ansible --version
```

### 7. 設定 GitHub GHCR 登入

```bash
# 用 GitHub Personal Access Token 登入 GHCR
# Token 需要 write:packages 權限
# 前往 https://github.com/settings/tokens 建立 PAT
echo <YOUR_GITHUB_PAT> | docker login ghcr.io -u AngusWooster --password-stdin
```

---

## Raspberry Pi 5 設定

### 7-1. 安裝 Raspberry Pi OS（64-bit）

使用 Raspberry Pi Imager 燒錄：
- OS：**Raspberry Pi OS Lite (64-bit)**（無 GUI，適合 server）
- 進階設定（齒輪圖示）：啟用 SSH、設定 hostname（例如 `raspi5`）、設定 WiFi 或使用有線

### 7-2. 首次連線

```bash
ssh pi@raspi5.local
# 或用 IP：ssh pi@<Pi-5-IP>
```

### 7-3. 在 Pi 5 上安裝 k3s

```bash
# 在 Pi 5 上執行
curl -sfL https://get.k3s.io | sh -

# 確認 k3s 狀態
sudo systemctl status k3s
sudo k3s kubectl get nodes
```

### 7-4. 把 kubeconfig 複製到開發機

```bash
# 在 Pi 5 上取得 kubeconfig
sudo cat /etc/rancher/k3s/k3s.yaml

# 在開發機上
mkdir -p ~/.kube
ssh pi@raspi5.local "sudo cat /etc/rancher/k3s/k3s.yaml" \
  | sed 's/127.0.0.1/<Pi-5-IP>/g' \
  > ~/.kube/config-raspi5

# 設定 KUBECONFIG
export KUBECONFIG=~/.kube/config-raspi5
kubectl get nodes
```

### 7-5. 建立 namespace

```bash
kubectl create namespace aku-sw
# 或用 k8s/namespace.yaml：
kubectl apply -f k8s/namespace.yaml
```

### 7-6. 設定 GHCR imagePullSecret（讓 k3s 能 pull 私有映像）

```bash
kubectl create secret docker-registry ghcr-secret \
  --namespace aku-sw \
  --docker-server=ghcr.io \
  --docker-username=AngusWooster \
  --docker-password=<YOUR_GITHUB_PAT>
```

---

## Bazel 常用指令

```bash
# 建置 time daemon
bazel build //host/sw/time:daemon

# 建置 time client
bazel build //host/sw/time:client

# 本機執行 daemon（測試用）
bazel run //host/sw/time:daemon

# 本機執行 client
bazel run //host/sw/time:client -- --host localhost --port 50052

# 建置所有服務
bazel build //host/sw/...

# 更新 pip lock file
bazel run //:pip_requirements.update
```

---

## Docker 映像建置

```bash
# 建置並 push time daemon 的 ARM64 映像
docker buildx build \
  --platform linux/arm64 \
  --tag ghcr.io/anguswooster/aku-sw/time-daemon:latest \
  --push \
  host/sw/time/
```

---

## Ansible 部署

```bash
# 部署 time daemon
ansible-playbook \
  -i ansible/inventory/hosts.yml \
  ansible/playbooks/deploy_time.yml \
  --extra-vars "image_tag=latest"

# 部署全部服務
ansible-playbook \
  -i ansible/inventory/hosts.yml \
  ansible/playbooks/deploy_all.yml
```

---

## GitHub 上傳流程

### 1. 在 GitHub 建立 Repository

前往 [https://github.com/new](https://github.com/new)，建立 `raspi-k8s`，**不要**勾選 Initialize with README。

### 2. 初始化本地 git 並推送

```bash
cd /home/aku/aku/raspi-k8s

git init
git branch -M main
git remote add origin https://github.com/AngusWooster/raspi-k8s.git

git add .
git commit -m "feat: initial project scaffold"
git push -u origin main
```

### 3. 日常開發流程

```bash
git add <修改的檔案>
git commit -m "feat/fix/chore: 簡述改動"
git push
```

---

## .gitignore 重點

| 路徑 | 原因 |
|------|------|
| `bazel-*` | Bazel 產生的 symlink / cache，不需版控 |
| `*_pb2.py`, `*_pb2_grpc.py` | Proto 產生的程式碼，由 genrule 自動產生 |
| `__pycache__/`, `*.pyc` | Python 編譯快取 |
| `.venv/` | 本機虛擬環境 |

---

## 實作順序（Todo）

### Phase 1 — time daemon（目前進行中）

- [ ] Bazel workspace（MODULE.bazel、.bazelrc、.bazelversion、requirements.txt）
- [ ] `tools/gen_proto.py`（proto 程式碼產生工具）
- [ ] `host/sw/time/proto/time_service.proto` + BUILD.bazel
- [ ] `host/sw/time/daemon.py` + `client.py` + BUILD.bazel
- [ ] `host/sw/time/Dockerfile`（ARM64）
- [ ] `k8s/namespace.yaml`
- [ ] `k8s/time/deployment.yaml` + `k8s/time/service.yaml`（NodePort 30052）
- [ ] `ansible/inventory/hosts.yml`（填入 Pi 5 IP）
- [ ] `ansible/group_vars/all.yml`
- [ ] `ansible/roles/` 結構
- [ ] `ansible/playbooks/deploy_time.yml`
- [ ] GitHub 初始化並推送

### Phase 2 — hello-world daemon

- [ ] 複製 time 的結構，建立最簡單的 echo 服務
- [ ] 驗證整套 Bazel → Docker → Ansible → K8s 流程

### Phase 3 — sysmon daemon

- [ ] 讀取 CPU / 記憶體 / 溫度（`/sys/class/thermal/thermal_zone0/temp`）
- [ ] 設計 `sysmon_service.proto`

### Phase 4 — K8s Job / CronJob 範例

- [ ] 建立一個 one-shot Job（例如：讀取時間並寫入 ConfigMap）
- [ ] 建立 CronJob（定時執行）
- [ ] 學習 Job 與 CronJob 與 Deployment 的差異

---

## 決策記錄

| 項目 | 決策 | 理由 |
|------|------|------|
| Container Registry | **GHCR** (`ghcr.io/anguswooster`) | 和 GitHub repo 整合最方便，有免費私有 package |
| K8s 發行版 | **k3s** | 輕量，官方支援 Pi，安裝一行指令 |
| Service 類型 | **NodePort** | 單節點無 LoadBalancer，NodePort 讓開發機直接存取 |
| Bazel 映像建置 | **純 Dockerfile + docker buildx** | 比 rules_oci 簡單，先學核心流程 |
| K8s namespace | **aku-sw** | 統一隔離所有自製服務 |
| Python 版本 | **3.11** | 穩定，Pi 5 64-bit OS 支援良好 |
