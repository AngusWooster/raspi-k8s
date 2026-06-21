# Step 5a：Raspberry Pi 5 k3s 安裝設定

## 本章目標

在 Raspberry Pi 5 上安裝 k3s（輕量版 Kubernetes），並設定開發機的 `kubectl` 連到 Pi 5 叢集，讓你能夠：

- 從開發機用 `kubectl` 管理 Pi 5 上的 K8s 叢集
- 部署容器到 Pi 5
- 從開發機用 gRPC client 連到 Pi 5 上的服務

---

## 環境資訊

| 項目 | 值 |
|------|-----|
| Pi 5 IP | `192.168.1.185` |
| SSH 使用者 | `pi` |
| SSH 金鑰 | `~/.ssh/id_rsa.pub`（已設定） |

---

## 背景知識：k3s 是什麼？

**k3s** 是 Rancher（現為 SUSE）開發的輕量版 Kubernetes，設計給資源有限的邊緣裝置：

| | Kubernetes（標準） | k3s |
|--|--|--|
| 記憶體需求 | ~2GB+ | ~512MB |
| 安裝複雜度 | 需要多個元件手動設定 | 單一 binary，一行指令安裝 |
| 功能完整度 | 完整 | 95%（移除部分雲端整合） |
| 適用場景 | 生產雲端叢集 | 邊緣裝置、開發、IoT |

k3s 使用 **containerd**（不是 Docker）作為容器執行時期，但映像格式相容，GHCR 推上去的映像可以直接拉取。

---

## Section 1：前置確認

### 確認 SSH 可以連上

```bash
ssh pi@192.168.1.185
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `ssh` | 建立 SSH 加密連線的指令 |
| `pi` | 登入 Pi 5 的使用者名稱 |
| `192.168.1.185` | Pi 5 的區域網路 IP |

連上後提示符號會變成 `pi@raspberrypi:~$`，代表你現在在 Pi 5 上操作。

### 確認作業系統版本

```bash
uname -m && cat /etc/os-release | grep PRETTY_NAME
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `uname -m` | 顯示 CPU 架構，Pi 5 64-bit OS 應該顯示 `aarch64` |
| `cat /etc/os-release` | 顯示作業系統資訊 |
| `grep PRETTY_NAME` | 過濾出版本名稱那行 |

預期輸出：
```
aarch64
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
```

> k3s 需要 64-bit OS（`aarch64`）。若顯示 `armv7l` 代表裝了 32-bit OS，需要重裝。

---

## Section 2：確認 cgroup（k3s 必要前置）

### 什麼是 cgroup？

cgroup（Control Group）是 Linux 核心功能，讓系統可以限制和追蹤每個程式使用的 CPU、記憶體等資源。Kubernetes 用 cgroup 來管理每個 Pod 的資源限制，**沒有 cgroup，k3s 無法正常運作**。

Linux 有兩個版本的 cgroup：

| | cgroup v1 | cgroup v2 |
|--|--|--|
| 結構 | 每種資源各一個目錄（`/sys/fs/cgroup/memory/`、`/sys/fs/cgroup/cpu/` ...） | 單一統一目錄（`/sys/fs/cgroup/`） |
| 確認方式 | `cat /proc/cgroups \| grep memory` 第四欄為 `1` | `mount \| grep cgroup` 顯示 `cgroup2` |
| Debian 13 trixie | 不使用 | ✅ 預設使用 |

### 步驟 1：確認使用哪個版本

> 以下指令在 **Pi 5** 上執行（先 `ssh pi@192.168.1.185` 連上後操作）。

```bash
mount | grep cgroup
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `mount` | 列出目前所有已掛載的檔案系統 |
| `grep cgroup` | 過濾出包含 `cgroup` 的行 |

**cgroup v2 的輸出（Debian 13 trixie）：**

```
cgroup2 on /sys/fs/cgroup type cgroup2 (rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot)
```

`cgroup2` + `memory_recursiveprot` 代表 cgroup v2 已啟用，且記憶體管理正常，k3s 可直接安裝，**不需要修改任何設定**。

**cgroup v1 的輸出（舊版 OS）：**

```
tmpfs on /sys/fs/cgroup type tmpfs ...
cgroup on /sys/fs/cgroup/memory type cgroup ...
```

若是 cgroup v1 且 memory 沒有掛載，才需要執行下面的步驟。

---

### 若需要啟用 cgroup memory（cgroup v1 才需要）

> **Debian 13 trixie 不需要此步驟，直接跳到 Section 3。**

**步驟：編輯開機參數**

```bash
sudo nano /boot/firmware/cmdline.txt
```

> **注意**：`/boot/cmdline.txt` 只是一個提示檔，告訴你「真正的檔案已移到 `/boot/firmware/cmdline.txt`」，不要編輯它。

在這行**最後面**加上（注意：整個檔案只有**一行**，絕對不能換行，否則核心讀不到參數）：

```
 cgroup_memory=1 cgroup_enable=memory
```

加入後整行看起來像這樣：

```
console=serial0,115200 console=tty1 root=PARTUUID=5ae1c04a-02 rootfstype=ext4 fsck.repair=yes rootwait ... cgroup_memory=1 cgroup_enable=memory
```

**nano 操作：**
- 用方向鍵 `→` 移到行尾
- 輸入（注意前面有一個空格）` cgroup_memory=1 cgroup_enable=memory`
- `Ctrl+O` → `Enter` 存檔
- `Ctrl+X` 離開

**儲存後重新開機：**

```bash
sudo reboot
```

重開機後確認生效：

```bash
mount | grep cgroup
# 應看到 memory 相關的掛載點
```

---

## Section 3：安裝 k3s

> 以下指令在 **Pi 5** 上執行。

先 SSH 連上 Pi 5：

```bash
ssh pi@192.168.1.185
```

然後執行安裝：

```bash
curl -sfL https://get.k3s.io | sh -
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `curl` | 下載網路資源的指令 |
| `-s` | silent，不顯示進度條 |
| `-f` | fail，HTTP 錯誤時回傳失敗（避免把錯誤頁面當成安裝腳本執行） |
| `-L` | follow redirects，跟隨 HTTP 302 轉址 |
| `https://get.k3s.io` | k3s 官方安裝腳本 |
| `\| sh -` | 把下載的腳本傳給 `sh` 執行；`-` 代表從 stdin 讀取 |

安裝過程約 1-2 分鐘，完成後會自動啟動 k3s service。

### 確認 k3s 正常啟動

```bash
sudo kubectl get nodes
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `sudo` | k3s 的 kubeconfig 預設只有 root 可讀，需要 sudo |
| `kubectl` | K8s 指令列工具（k3s 安裝時自動附帶） |
| `get nodes` | 列出叢集中的所有節點（機器） |

預期輸出：

```
NAME     STATUS   ROLES           AGE   VERSION
raspi5   Ready    control-plane   30s   v1.35.x+k3s1
```

`STATUS: Ready` 代表 k3s 正常運作。

---

## Section 4：設定開發機 kubectl

目前 `kubectl` 只能在 Pi 5 上用 `sudo` 執行。接下來把 kubeconfig 複製到開發機，讓你可以在**開發機**上直接控制 Pi 5 的叢集。

### kubeconfig 是什麼？

kubeconfig 是一個 YAML 設定檔，記錄：
- 叢集的 API server 位址（`https://Pi_IP:6443`）
- 用來驗證身份的憑證（TLS certificate）
- 使用哪個叢集、哪個帳號

`kubectl` 預設讀取 `~/.kube/config`。

步驟 1–4 在**開發機**上執行，步驟 5 需要回到 **Pi 5** 上執行，步驟 6 兩台都要執行。

### 步驟 1：建立 .kube 目錄

```bash
mkdir -p ~/.kube
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `mkdir` | 建立目錄 |
| `-p` | 若目錄已存在不報錯，父目錄不存在時一併建立 |
| `~/.kube` | `~` 代表家目錄（`/home/aku`），`kubectl` 預設在這裡找設定 |

### 步驟 2：從 Pi 5 取得 kubeconfig

`k3s.yaml` 只有 root 可讀，`pi` 使用者沒有直接讀取的權限，所以用 `ssh ... "sudo cat ..."` 讓 Pi 5 用 root 讀取後傳回開發機：

```bash
ssh pi@192.168.1.185 "sudo cat /etc/rancher/k3s/k3s.yaml" > ~/.kube/config
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `ssh pi@192.168.1.185` | 連到 Pi 5（指令執行完後自動斷線，不是互動式 shell） |
| `"sudo cat /etc/rancher/k3s/k3s.yaml"` | 在 Pi 5 上執行的指令，用 root 權限讀取 k3s kubeconfig |
| `>` | 把 ssh 的輸出（kubeconfig 內容）寫入右邊的檔案 |
| `~/.kube/config` | 寫入開發機上 `kubectl` 預設讀取的路徑 |

> **重要**：`>` 是在**開發機**上執行的，把 Pi 5 傳回的內容存到開發機的 `~/.kube/config`，不是在 Pi 5 上建檔。

### 步驟 3：修改 kubeconfig 的 server 位址

k3s 產生的 kubeconfig 裡，server 位址預設是 `127.0.0.1`（localhost），在 Pi 5 本機上用沒問題，但從開發機連要改成 Pi 5 的實際 IP。

```bash
sed -i 's/127.0.0.1/192.168.1.185/g' ~/.kube/config
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `sed` | Stream Editor，對文字做搜尋取代 |
| `-i` | in-place，直接修改原檔案（不加的話只印出結果，不修改） |
| `'s/127.0.0.1/192.168.1.185/g'` | 替換規則：`s/舊字串/新字串/g`，`g` 代表替換所有出現的地方 |
| `~/.kube/config` | 要修改的檔案 |

### 步驟 4：設定 config 檔案權限

```bash
chmod 600 ~/.kube/config
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `chmod` | 修改檔案權限 |
| `600` | 擁有者可讀寫（`6`），群組和其他人無權限（`00`）。kubeconfig 含有憑證，不應該讓其他使用者讀取 |

### 步驟 5：讓 pi 使用者可以直接使用 kubectl（在 Pi 5 上執行）

> 這步要切回 **Pi 5**，先 SSH 連上：
> ```bash
> ssh pi@192.168.1.185
> ```

k3s 的 kubectl 會同時嘗試讀取 `~/.kube/config` 和 `/etc/rancher/k3s/k3s.yaml` 並合併，但後者預設只有 root 可讀，導致權限錯誤。

```bash
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
```

**參數說明：**

| 參數 | 說明 |
|------|------|
| `chmod 644` | 擁有者可讀寫（`6`），群組和其他人可讀（`4`）。讓 `pi` 使用者能直接讀取 k3s kubeconfig |

### 步驟 6：確認連線成功（在開發機和 Pi 5 上都執行）

**在 Pi 5 上：**

```bash
kubectl get nodes
```

**在開發機上：**

```bash
kubectl get nodes
```

預期輸出：

```
NAME     STATUS   ROLES           AGE   VERSION
raspi5   Ready    control-plane   14m   v1.35.5+k3s1
```

兩者都應該正常，且不需要 `sudo`。

---

## 本章重點回顧

| 步驟 | 在哪台機器 | 指令 |
|------|-----------|------|
| 安裝 k3s | Pi 5 | `curl -sfL https://get.k3s.io \| sh -` |
| 確認 k3s 狀態 | Pi 5 | `sudo kubectl get nodes` |
| 複製 kubeconfig | 開發機 | `ssh pi@192.168.1.185 "sudo cat /etc/rancher/k3s/k3s.yaml" > ~/.kube/config` |
| 修改 server IP | 開發機 | `sed -i 's/127.0.0.1/192.168.1.185/g' ~/.kube/config` |
| 讓 pi 可用 kubectl | Pi 5 | `sudo chmod 644 /etc/rancher/k3s/k3s.yaml` |
| 確認開發機連線 | 開發機 | `kubectl get nodes` |

---

## 下一步

前往 **[Step 5：Kubernetes Manifests](step-5-k8s-manifests.md)**，部署 time-daemon 到 Pi 5。

> **注意**：我們的 GHCR 映像是**私有**的，Step 5 Section 4 會說明如何建立 imagePullSecret 讓 Pi 5 能夠拉取映像，請按照文件步驟順序執行，不要跳過 Step 2（建立 secret）。
