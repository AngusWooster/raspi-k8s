# Step 5：Kubernetes Manifests

## 本章目標

撰寫 Kubernetes manifest 檔案，將 `time-daemon` 容器部署到 Raspberry Pi 5 上的 k3s 叢集，讓你能夠：

- 理解 Kubernetes 三個核心資源：Namespace、Deployment、Service
- 從外部（開發機）用 gRPC client 查詢跑在 Pi 5 上的時間服務
- 學會 `kubectl` 的基本操作指令

---

## 背景知識：Kubernetes 是什麼？

Kubernetes（簡稱 K8s）是一個**容器編排系統**，負責：

- 在指定的機器上**啟動容器**（你只描述「我要跑什麼」，K8s 決定在哪跑）
- **監控**容器狀態，掛掉就自動重啟
- **管理網路**，讓容器之間、外部和容器之間可以通訊
- **滾動更新**，升級版本時不中斷服務

**k3s** 是 Kubernetes 的輕量版，設計給邊緣裝置（如 Raspberry Pi），功能與 K8s 相同但資源佔用更少。

### 你只需要寫「想要的狀態」

K8s 的核心概念是**宣告式（Declarative）**：你寫 YAML 描述「我希望系統是什麼狀態」，K8s 負責讓現實符合你的描述。

```
你寫 YAML：「我要 1 個 time-daemon Pod 一直跑著」
     ↓
K8s：好，我來啟動它
     Pod 掛掉了
K8s：你說要 1 個，現在是 0 個，我來重啟
```

相較之下，**命令式（Imperative）**是你下每一個指令：「幫我啟動這個容器、如果掛掉幫我重啟...」，K8s 幫你把這些自動化了。

---

## 本章涉及的檔案

```
raspi-k8s/
├── k8s/
│   ├── namespace.yaml          ← 建立 aku-sw namespace
│   └── time/
│       ├── deployment.yaml     ← 定義 Pod 規格
│       └── service.yaml        ← 開放 NodePort 30052
└── doc/
    └── step-5-k8s-manifests.md
```

---

## Section 1：Namespace

### 什麼是 Namespace？

Namespace 是 K8s 裡的**邏輯隔離單位**，像是在同一個叢集裡劃分不同的「房間」。

```
k3s 叢集（Raspberry Pi 5）
├── namespace: default          ← K8s 預設 namespace
├── namespace: kube-system      ← K8s 系統元件（不要動它）
└── namespace: aku-sw           ← 我們的 namespace
    ├── Pod: time-daemon
    ├── Pod: hello-daemon       （未來）
    └── Pod: sysmon-daemon      （未來）
```

為什麼要用自己的 namespace？
- 避免和 K8s 系統元件混在一起
- 可以對整個 namespace 設定權限、資源限制
- `kubectl get pods -n aku-sw` 只看自己的東西，不會和其他服務混淆

### namespace.yaml 解析

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: aku-sw
```

| 欄位 | 說明 |
|------|------|
| `apiVersion: v1` | 使用 K8s API 的版本。`v1` 是核心 API 群組，包含 Namespace、Pod、Service 等基本資源 |
| `kind: Namespace` | 資源類型。告訴 K8s 這個 YAML 要建立什麼 |
| `metadata.name: aku-sw` | 這個 Namespace 的名稱，之後所有資源都用 `-n aku-sw` 指定 |

---

## Section 2：Deployment

### 什麼是 Deployment？

Deployment 定義「要跑什麼、跑幾個、怎麼更新」。它管理的是 **Pod**，Pod 是 K8s 裡最小的執行單位，一個 Pod 裡可以有一個或多個容器。

```
Deployment: time-daemon
└── 管理 ReplicaSet（副本集）
    └── 維持 1 個 Pod 存活
        └── Pod
            └── Container: time-daemon（ghcr.io/.../time-daemon:latest）
                └── 監聽 port 50052
```

**Deployment vs 直接跑容器的差別：**

| | `docker run` | K8s Deployment |
|--|--|--|
| 容器掛掉 | 就掛了 | 自動重啟 |
| 更新映像 | 手動停止、重啟 | 滾動更新，零停機 |
| 多副本 | 要手動跑多個 | 改 `replicas: 3` 即可 |
| 重開機後 | 需要手動啟動 | 自動恢復 |

### deployment.yaml 解析

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: time-daemon
  namespace: aku-sw
spec:
  replicas: 1
  selector:
    matchLabels:
      app: time-daemon
  template:
    metadata:
      labels:
        app: time-daemon
    spec:
      imagePullSecrets:
        - name: ghcr-secret
      containers:
        - name: time-daemon
          image: ghcr.io/anguswooster/raspi-k8s/time-daemon:latest
          ports:
            - containerPort: 50052
```

**逐欄說明：**

| 欄位 | 說明 |
|------|------|
| `apiVersion: apps/v1` | Deployment 屬於 `apps` API 群組，版本 `v1` |
| `kind: Deployment` | 資源類型 |
| `metadata.name` | Deployment 的名稱，`kubectl get deployment -n aku-sw` 會看到這個名字 |
| `metadata.namespace` | 部署到哪個 namespace |
| `spec.replicas: 1` | 維持 1 個 Pod 存活。改成 `3` K8s 就會啟動 3 個 Pod |
| `spec.selector.matchLabels` | Deployment 用這個 label 找到它管理的 Pod（必須和 `template.metadata.labels` 一致） |
| `spec.template` | Pod 的模板，每個副本都用這個模板建立 |
| `template.metadata.labels` | 貼在 Pod 上的標籤，Service 也靠這個 label 找到 Pod |
| `imagePullSecrets[].name` | 拉取私有映像時要用哪個 secret 驗證身份。`ghcr-secret` 是 Section 4 步驟 2 建立的 secret 名稱 |
| `containers[].name` | 容器在 Pod 內的名稱（一個 Pod 有多個容器時用來區分） |
| `containers[].image` | 要跑的映像檔，就是 Step 4 推到 GHCR 的那個 |
| `containers[].ports[].containerPort` | 容器內監聽的 port（文件用途，不影響實際行為，但 Service 設定時要一致） |

### Label 的作用

Label（標籤）是 K8s 裡連結不同資源的核心機制：

```
Deployment
  selector:
    matchLabels:
      app: time-daemon     ← 「我管理有這個 label 的 Pod」
          │
          └──────────────────────────────────┐
                                             ▼
Pod                              Service
  labels:                          selector:
    app: time-daemon  ◄──────────    app: time-daemon
                                   「把流量送到有這個 label 的 Pod」
```

Deployment 和 Service 都透過 label `app: time-daemon` 找到同一批 Pod，彼此不需要知道 Pod 的 IP（Pod 重啟後 IP 會變）。

---

## Section 3：Service

### 什麼是 Service？

Pod 有幾個問題：
1. Pod 重啟後 IP 會改變，client 不知道新 IP 是多少
2. Pod 預設只在叢集內部可以連，外部連不進來

**Service** 解決這兩個問題：
1. 提供一個**固定不變的入口**（ClusterIP 或 NodePort）
2. 自動找到符合 label 的 Pod 並把流量轉過去

### Service 類型

| 類型 | 用途 | 可被誰連接 |
|------|------|-----------|
| `ClusterIP` | 叢集內部通訊（預設） | 只有叢集內部 |
| `NodePort` | 開放給外部存取 | 叢集外部，透過 Pi 的 IP + NodePort |
| `LoadBalancer` | 雲端環境，自動建立 Load Balancer | 需要雲端支援 |

本專案用 **NodePort**，讓開發機可以直接連到 Pi 5 上的服務。

### service.yaml 解析

```yaml
apiVersion: v1
kind: Service
metadata:
  name: time-daemon
  namespace: aku-sw
spec:
  type: NodePort
  selector:
    app: time-daemon
  ports:
    - protocol: TCP
      port: 50052
      targetPort: 50052
      nodePort: 30052
```

**逐欄說明：**

| 欄位 | 說明 |
|------|------|
| `kind: Service` | 資源類型 |
| `spec.type: NodePort` | Service 類型，開放叢集外部存取 |
| `spec.selector.app: time-daemon` | 把流量送到有這個 label 的 Pod（對應 Deployment template 的 labels） |
| `ports[].protocol: TCP` | gRPC 跑在 TCP 上 |
| `ports[].port: 50052` | 叢集**內部**其他 Pod 連這個 Service 用的 port |
| `ports[].targetPort: 50052` | Service 把流量轉到 Pod 的哪個 port（對應 `containerPort`） |
| `ports[].nodePort: 30052` | 從叢集**外部**（開發機）連入的 port。K8s 規定 NodePort 必須在 30000–32767 範圍內 |

### 完整 port 流向

```
開發機                  Raspberry Pi 5              Pod（容器）
                        （k3s node）
                        
client ──► Pi_IP:30052 ──► Service:50052 ──► daemon:50052
           （NodePort）     （ClusterIP）     （containerPort）
           
bazel run //host/sw/time:client -- --host <Pi_IP> --port 30052
```

---

## Section 4：套用 manifest

### 前置需求

- kubeconfig 已設定（`kubectl get nodes` 可以看到 `raspi5 Ready`）
- GHCR 映像是**私有**的，需要建立 imagePullSecret 讓 Pi 5 有權限拉取

### 步驟 1：建立 namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

| 參數 | 說明 |
|------|------|
| `kubectl apply` | 套用 manifest。若資源不存在就建立，已存在就更新 |
| `-f k8s/namespace.yaml` | `-f` 是 `--filename`，指定要套用的 YAML 檔案 |

### 步驟 2：建立 GHCR imagePullSecret

k3s 在 Pi 5 上拉取 GHCR 私有映像時需要驗證身份。這個 secret 存在叢集裡，k3s 拉取映像時自動使用。

先安全輸入 GitHub PAT（不會顯示在螢幕上）：

```bash
read -s GHCR_TOKEN
```

| 參數 | 說明 |
|------|------|
| `read` | 讀取使用者輸入，存到變數 |
| `-s` | silent，輸入時不顯示字元（避免 PAT 出現在螢幕或 shell history） |
| `GHCR_TOKEN` | 變數名稱，之後用 `$GHCR_TOKEN` 引用 |

輸完 PAT 按 Enter，然後建立 secret：

```bash
kubectl create secret docker-registry ghcr-secret \
  --namespace aku-sw \
  --docker-server=ghcr.io \
  --docker-username=AngusWooster \
  --docker-password=$GHCR_TOKEN
```

| 參數 | 說明 |
|------|------|
| `kubectl create secret` | 建立 K8s secret 資源 |
| `docker-registry` | secret 的類型，專門用於容器 registry 的登入憑證 |
| `ghcr-secret` | secret 的名稱，在 `deployment.yaml` 裡用 `imagePullSecrets.name` 引用 |
| `--namespace aku-sw` | 建立在哪個 namespace，必須和 Deployment 同一個 namespace |
| `--docker-server=ghcr.io` | registry 的網址 |
| `--docker-username=AngusWooster` | GHCR 的使用者名稱 |
| `--docker-password=$GHCR_TOKEN` | 用 `$GHCR_TOKEN` 變數傳入 PAT，不直接寫在指令裡 |

確認 secret 建立成功：

```bash
kubectl get secret ghcr-secret -n aku-sw
```

預期輸出：

```
NAME          TYPE                             DATA   AGE
ghcr-secret   kubernetes.io/dockerconfigjson   1      5s
```

### 步驟 3：部署 Deployment 和 Service

```bash
kubectl apply -f k8s/time/
```

| 參數 | 說明 |
|------|------|
| `-f k8s/time/` | 套用目錄下所有 `.yaml` 檔案（`deployment.yaml` 和 `service.yaml`） |

**`kubectl apply` vs `kubectl create` 的差別：**

| | `kubectl create` | `kubectl apply` |
|--|--|--|
| 資源已存在 | 報錯 | 更新（diff 後只改不同的欄位） |
| 資源不存在 | 建立 | 建立 |
| 使用場景 | 一次性建立 | 日常維護（推薦） |

---

## Section 5：驗證部署

```bash
# 確認 Pod 正在跑（STATUS 應該是 Running）
kubectl get pods -n aku-sw

# 確認 Service 和 NodePort 設定正確
kubectl get service -n aku-sw

# 查看 Pod 的詳細狀態（出問題時用）
kubectl describe pod -n aku-sw <pod_name>

# 查看 Pod 的 log（daemon 的輸出）
kubectl logs -n aku-sw <pod_name>

# 持續追蹤 log
kubectl logs -n aku-sw <pod_name> -f
```

**`kubectl get pods` 欄位說明：**

| 欄位 | 說明 |
|------|------|
| `NAME` | Pod 名稱，格式為 `deployment名稱-隨機碼`，例如 `time-daemon-7d9f8b-xk2p4` |
| `READY` | `1/1` 代表 1 個容器中 1 個就緒；`0/1` 代表容器還沒啟動 |
| `STATUS` | `Running`（正常）、`Pending`（等待排程）、`CrashLoopBackOff`（一直崩潰重啟） |
| `RESTARTS` | 容器重啟次數，正常應該是 `0` |
| `AGE` | Pod 存在多久了 |

### 常見問題排查

| 症狀 | 可能原因 | 排查方式 |
|------|---------|---------|
| `STATUS: Pending` | 映像拉取中，或 Pi 資源不足 | `kubectl describe pod ...` 看 Events |
| `STATUS: ImagePullBackOff` | GHCR 映像拉不到（私有映像未設 imagePullSecret，或名稱錯誤） | 確認 image 名稱、GHCR 是否公開 |
| `STATUS: CrashLoopBackOff` | 容器啟動後馬上崩潰 | `kubectl logs ...` 看錯誤訊息 |
| `READY: 0/1` | 容器啟動中或 liveness probe 失敗 | `kubectl describe pod ...` |

### 從開發機測試連線

Pod 正常跑起來後，用 bazel client 連到 Pi 5：

```bash
bazel run //host/sw/time:client -- --host <Pi_IP> --port 30052
```

預期輸出：

```
Timestamp  : 2026-06-21T05:30:00.123456+00:00
Unix time  : 1750484200.123456789
Timezone   : CST              ← Pi 5 的時區
Hostname   : time-daemon-xxx  ← Pod 名稱（不是你的電腦）
```

---

## Section 6：更新映像

當 `daemon.py` 有修改，更新流程：

```bash
# 1. 重新 build 並推送新映像
docker buildx build \
  --platform linux/arm64 \
  -t ghcr.io/anguswooster/raspi-k8s/time-daemon:latest \
  -f host/sw/time/Dockerfile \
  --push .

# 2. 讓 K8s 重新拉取映像（強制 rollout）
kubectl rollout restart deployment/time-daemon -n aku-sw

# 3. 確認更新完成
kubectl rollout status deployment/time-daemon -n aku-sw
```

**為什麼要用 `rollout restart`？**  
`image: ...:latest` 這個 tag 不變，K8s 不知道映像內容有更新，不會自動重拉。`rollout restart` 強制讓 Deployment 建立新的 Pod（會拉最新的 `latest` 映像），舊 Pod 等新 Pod 就緒後再刪除，做到**零停機更新**。

---

## 本章重點回顧

| 概念 | 說明 |
|------|------|
| **Namespace** | 叢集內的邏輯隔離空間，本專案用 `aku-sw` |
| **Deployment** | 管理 Pod 數量和更新策略，Pod 掛掉自動重啟 |
| **Pod** | K8s 最小執行單位，包含一個或多個容器 |
| **Service** | 穩定的網路入口，透過 label selector 找到 Pod |
| **NodePort** | 開放叢集外部存取，port 範圍 30000–32767 |
| **Label** | 連結 Deployment 和 Service 到同一批 Pod 的機制 |
| **kubectl apply** | 宣告式套用 manifest，自動建立或更新資源 |
| **rollout restart** | 強制重新部署，讓 K8s 拉取最新的 `latest` 映像 |

---

## 下一步

Step 6：Ansible — 自動化部署流程，用 playbook 取代手動執行 `kubectl apply`。
