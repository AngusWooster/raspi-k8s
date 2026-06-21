# Step 6：Ansible 自動化部署

## 本章目標

用 Ansible 把 Step 5 的手動部署步驟自動化，讓你只需要執行一個指令，就能完成：

1. 建立 K8s namespace
2. 建立 GHCR imagePullSecret（用加密的 PAT）
3. 套用 Deployment 和 Service
4. 等待 Pod 就緒確認

---

## 背景知識：Ansible 是什麼？

Ansible 是一個**自動化工具**，讓你用 YAML 描述「要在哪台機器上做什麼」，然後一次執行完成。

### Ansible vs 手動 kubectl

| | 手動 kubectl | Ansible |
|--|--|--|
| 部署流程 | 依序手動輸入多個指令 | 一個指令自動執行全部 |
| 重複部署 | 每次都要重打指令 | 同一個 playbook 跑幾次都一樣 |
| PAT 安全 | 每次輸入 `read -s` | 用 Vault 加密存好，自動解密 |
| 多台機器 | 要一台一台做 | inventory 加一行就多一台 |

### 核心概念

```
Playbook（劇本）
└── Play（在哪些機器上做什麼）
    └── Tasks（一步一步做什麼）
        ├── Task 1：建立 namespace
        ├── Task 2：建立 imagePullSecret
        ├── Task 3：套用 Deployment
        ├── Task 4：套用 Service
        └── Task 5：等待 Pod Ready
```

- **Playbook**：一份 YAML 檔，描述完整的部署流程
- **Task**：Playbook 裡的每一個步驟
- **Module**：執行 Task 用的工具（本章用 `kubernetes.core.k8s` module）
- **Vault**：Ansible 內建的加密工具，用來保存 PAT 等機密

### 本章的架構

本章用 `kubernetes.core` Ansible collection，直接從**開發機**透過 kubeconfig 操作 Pi 5 的 k3s 叢集。不需要 SSH 到 Pi 5，Ansible 呼叫 K8s API 完成所有操作。

```
開發機
├── Ansible 執行 playbook
├── 讀取 ~/.kube/config（連到 Pi 5 k3s API）
└── 呼叫 K8s API → Pi 5 k3s
    ├── 建立 namespace aku-sw
    ├── 建立 secret ghcr-secret
    ├── 套用 Deployment + Service
    └── 確認 Pod Running
```

---

## 本章涉及的檔案

```
raspi-k8s/
├── host/
│   ├── sw/
│   │   └── time/                           ← time-daemon 程式碼
│   └── deploy/
│       └── ansible/
│           ├── group_vars/
│           │   └── all.yml                 ← 加密的 PAT（可以進 git）
│           └── playbooks/
│               └── deploy-time-daemon.yml  ← 部署 playbook
└── doc/
    └── step-6-ansible.md
```

---

## Section 1：安裝 Ansible

在**開發機**的 venv 虛擬環境中安裝：

```bash
source .venv/bin/activate
pip install ansible kubernetes
```

| 套件 | 說明 |
|------|------|
| `ansible` | Ansible 核心工具 |
| `kubernetes` | Python 的 K8s client library，`kubernetes.core` collection 需要它 |

安裝後更新 lock 檔（`pip-compile` 來自 `pip-tools`，已在前面步驟安裝）：

```bash
pip-compile requirements.txt -o requirements_lock.txt
```

安裝 `kubernetes.core` Ansible collection：

```bash
ansible-galaxy collection install kubernetes.core
```

| 參數 | 說明 |
|------|------|
| `ansible-galaxy` | Ansible 的套件管理工具，類似 pip |
| `collection install` | 安裝 collection（Ansible 的模組套件）。collection 有自己的安裝機制，不走 pip，不需要加進 `requirements.txt` |
| `kubernetes.core` | 提供 `k8s`、`k8s_info` 等操作 K8s 資源的 module |

確認安裝成功：

```bash
ansible --version
ansible-galaxy collection list | grep kubernetes
```

預期輸出：

```
ansible [core 2.17.x]
...
kubernetes.core    3.x.x
```

---

## Section 2：Ansible Vault — 加密存放 PAT

GitHub PAT 是機密，不能明文寫在 YAML 檔裡（會進 git history）。Ansible Vault 讓你把機密加密後存入檔案，執行時再解密使用。

```
PAT（GitHub 機密）
  → 用 Vault 密碼加密
  → 存進 group_vars/all.yml（加密後可以進 git）

執行 playbook 時
  → Ansible 讀 ~/.vault_pass（Vault 密碼）
  → 解密 PAT
  → 建立 K8s secret 進叢集
```

### 步驟 1：建立 Vault 密碼檔

Vault 本身需要一個密碼來加密/解密 PAT，把這個密碼存在**家目錄**（不進 git）：

```bash
read -s VAULT_PASS && echo "$VAULT_PASS" > ~/.vault_pass
chmod 600 ~/.vault_pass
```

| 參數 | 說明 |
|------|------|
| `read -s VAULT_PASS` | 安全輸入 Vault 密碼，不顯示在螢幕，也不進 shell history |
| `echo "$VAULT_PASS"` | 把輸入的密碼寫入檔案 |
| `> ~/.vault_pass` | 寫入家目錄（`~`），不在專案目錄裡，確保不會被 git 追蹤 |
| `chmod 600` | 擁有者可讀寫，其他人無權限。Vault 密碼只有自己能看 |

> **注意**：不要用 `echo "你的密碼" > ~/.vault_pass`，這樣密碼會出現在 shell history（`~/.zsh_history`），任何人看 history 都能看到。`read -s` 不會記錄輸入內容。

> **重要**：`~/.vault_pass` 只存在你的電腦上，不進 git。沒有這個密碼，就算拿到 `all.yml` 也無法解密 PAT。

### 步驟 2：建立目錄並加密 PAT

先建立目錄（若已存在不報錯）：

```bash
mkdir -p host/deploy/ansible/group_vars
```

安全輸入 GitHub PAT（不會顯示在螢幕上）：

```bash
read -s GHCR_TOKEN
```

| 參數 | 說明 |
|------|------|
| `read` | 讀取使用者輸入，存到變數 |
| `-s` | silent，輸入時不顯示字元，避免 PAT 出現在螢幕或 shell history |
| `GHCR_TOKEN` | 變數名稱，之後用 `$GHCR_TOKEN` 引用 |

輸完 PAT 按 Enter，然後加密並寫入 `all.yml`：

```bash
ansible-vault encrypt_string "$GHCR_TOKEN" \
  --vault-password-file ~/.vault_pass \
  --name ghcr_pat \
  > host/deploy/ansible/group_vars/all.yml
```

| 參數 | 說明 |
|------|------|
| `ansible-vault encrypt_string` | 加密單一字串（不是整個檔案） |
| `"$GHCR_TOKEN"` | 要加密的 PAT 值（從變數取得，不直接貼 PAT） |
| `--vault-password-file ~/.vault_pass` | 指定用哪個密碼來加密 |
| `--name ghcr_pat` | 加密後的變數名稱，playbook 裡用 `{{ ghcr_pat }}` 引用 |
| `>` | 把輸出**寫入**檔案（覆蓋，確保不會有重複的 key） |
| `host/deploy/ansible/group_vars/all.yml` | 輸出路徑，Ansible 執行時自動讀取這個檔案的變數 |

> **重要**：這裡用 `>`（覆蓋）而不是 `>>`（附加）。若用 `>>` 重複執行，`all.yml` 會出現兩個 `ghcr_pat` key，Ansible 只讀最後一個，造成混亂。

執行後 `host/deploy/ansible/group_vars/all.yml` 內容看起來像這樣：

```yaml
ghcr_pat: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          35306132663839316565336636656138...（加密內容）
```

這個檔案可以安全地進 git，沒有 `~/.vault_pass` 無法解密。

### 查看 / 驗證加密內容

確認 all.yml 裡的 PAT 是否正確（解密後印到螢幕，不修改檔案）：

```bash
ansible-vault view \
  --vault-password-file ~/.vault_pass \
  host/deploy/ansible/group_vars/all.yml
```

| 參數 | 說明 |
|------|------|
| `ansible-vault view` | 解密並顯示檔案內容，不修改原檔案 |
| `--vault-password-file ~/.vault_pass` | 指定解密用的密碼檔 |

預期輸出：
```
ghcr_pat: ghp_xxxxxxxxxxxxxxxxxxxx
```

### 若需要更換 PAT（重新加密）

PAT 洩露或過期時，重新加密：

```bash
# 清空舊的加密內容
echo "" > host/deploy/ansible/group_vars/all.yml

# 輸入新 PAT
read -s GHCR_TOKEN

# 重新加密
ansible-vault encrypt_string "$GHCR_TOKEN" \
  --vault-password-file ~/.vault_pass \
  --name ghcr_pat \
  > host/deploy/ansible/group_vars/all.yml
```

---

## Section 3：Playbook 解析

完整 playbook 位於 `host/deploy/ansible/playbooks/deploy-time-daemon.yml`：

```yaml
---
- name: Deploy time-daemon to Pi 5 k3s
  hosts: localhost
  connection: local
  gather_facts: false

  vars_files:
    - "{{ playbook_dir }}/../group_vars/all.yml"

  vars:
    kubeconfig: "{{ lookup('env', 'HOME') }}/.kube/config"
    k8s_namespace: aku-sw
    image: ghcr.io/anguswooster/raspi-k8s/time-daemon:latest
    ghcr_username: AngusWooster
    manifest_dir: "{{ playbook_dir }}/../../../../k8s"

  tasks:
    - name: Create namespace aku-sw
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig }}"
        state: present
        definition:
          apiVersion: v1
          kind: Namespace
          metadata:
            name: "{{ k8s_namespace }}"

    - name: Create GHCR imagePullSecret
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig }}"
        state: present
        force: true
        definition:
          apiVersion: v1
          kind: Secret
          metadata:
            name: ghcr-secret
            namespace: "{{ k8s_namespace }}"
          type: kubernetes.io/dockerconfigjson
          data:
            .dockerconfigjson: "{{ {'auths': {'ghcr.io': {'username': ghcr_username, 'password': ghcr_pat}}} | to_json | b64encode }}"

    - name: Apply time-daemon Deployment
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig }}"
        state: present
        src: "{{ manifest_dir }}/time/deployment.yaml"

    - name: Apply time-daemon Service
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig }}"
        state: present
        src: "{{ manifest_dir }}/time/service.yaml"

    - name: Wait for time-daemon Pod to be Running
      kubernetes.core.k8s_info:
        kubeconfig: "{{ kubeconfig }}"
        kind: Pod
        namespace: "{{ k8s_namespace }}"
        label_selectors:
          - app=time-daemon
        wait: true
        wait_condition:
          type: Ready
          status: "True"
        wait_timeout: 120
```

### Play 層級說明

| 欄位 | 說明 |
|------|------|
| `hosts: localhost` | 在哪台機器上執行。用 kubeconfig 操作 K8s API，在開發機本機跑就好 |
| `connection: local` | 不透過 SSH，直接在本機執行 |
| `gather_facts: false` | 跳過收集目標機器資訊（本機執行不需要，跳過節省時間） |

### vars_files 說明

```yaml
vars_files:
  - "{{ playbook_dir }}/../group_vars/all.yml"
```

| 欄位 | 說明 |
|------|------|
| `vars_files` | 明確指定要載入哪些變數檔案 |
| `{{ playbook_dir }}` | Ansible 內建變數，代表 playbook 所在的目錄（`host/deploy/ansible/playbooks/`） |
| `/../group_vars/all.yml` | 往上一層到 `ansible/`，再進 `group_vars/all.yml`（存加密 PAT 的檔案） |

### vars 說明

| 變數 | 值 | 說明 |
|------|-----|------|
| `kubeconfig` | `~/.kube/config` | kubeconfig 路徑。`lookup('env', 'HOME')` 取得家目錄路徑 |
| `k8s_namespace` | `aku-sw` | K8s namespace。**注意**：不能用 `namespace`，那是 Ansible 保留字 |
| `ghcr_username` | `AngusWooster` | GHCR 使用者名稱 |
| `manifest_dir` | `playbook_dir/../../../../k8s` | K8s manifest 目錄。從 `playbooks/` 往上 4 層到專案根目錄，再進 `k8s/` |

> **注意**：`image` 變數在 vars 區塊定義，但 Task 3、4 直接用 `src:` 套用 manifest 檔案（image 已寫在 `deployment.yaml` 裡），所以 `image` 變數目前未被任何 task 引用。它只做記錄用途，讓你一眼知道這個 playbook 部署的是哪個映像。

**`manifest_dir` 路徑計算：**

```
host/deploy/ansible/playbooks/   ← playbook_dir
                        ../      → host/deploy/ansible/
                      ../../     → host/deploy/
                    ../../../    → host/
                  ../../../../   → raspi-k8s/（專案根目錄）
               ../../../../k8s   → raspi-k8s/k8s/（manifest 目錄）
```

### Task 說明

**Task 1：建立 namespace**

| 欄位 | 說明 |
|------|------|
| `kubernetes.core.k8s` | 操作 K8s 資源的 module，等同 `kubectl apply` |
| `state: present` | 若不存在就建立，已存在就不動（冪等） |
| `definition` | 直接在 playbook 裡寫 K8s YAML 定義 |

**Task 2：建立 GHCR imagePullSecret**

| 欄位 | 說明 |
|------|------|
| `force: true` | 若 secret 已存在，先刪除再重建。用於確保 PAT 更新後 secret 一定是最新的 |
| `type: kubernetes.io/dockerconfigjson` | K8s 專門用於容器 registry 登入憑證的 secret 類型 |
| `data` | K8s Secret 的 `data` 欄位，值必須是 base64 編碼 |
| `to_json` | Ansible filter，把 Python dict 轉成 JSON 字串 |
| `b64encode` | Ansible filter，把字串 base64 編碼（`data` 欄位的要求） |

為什麼用 `data` + `b64encode` 而不是 `stringData`？  
Ansible 的 `kubernetes.core.k8s` module 在處理 `stringData` 時，會把 JSON 字串誤解析成物件，導致 K8s API 回傳格式錯誤。改用 `data` 並自行 base64 編碼可以繞過這個問題。

**Task 3 & 4：套用 Deployment 和 Service**

| 欄位 | 說明 |
|------|------|
| `src` | 指定 manifest 檔案路徑，直接套用檔案（等同 `kubectl apply -f`） |

**Task 5：等待 Pod Ready**

| 欄位 | 說明 |
|------|------|
| `kubernetes.core.k8s_info` | 查詢 K8s 資源狀態的 module |
| `label_selectors` | 用 label 篩選 Pod，`app=time-daemon` |
| `wait: true` | 等待條件成立才繼續 |
| `wait_condition.type: Ready` | 等待 Pod 的 `Ready` condition 變成 `True` |
| `wait_timeout: 120` | 最多等 120 秒，超過就報錯 |

---

## Section 4：執行 Playbook

從**專案根目錄**執行（`raspi-k8s/`）：

```bash
ansible-playbook host/deploy/ansible/playbooks/deploy-time-daemon.yml \
  --vault-password-file ~/.vault_pass
```

| 參數 | 說明 |
|------|------|
| `ansible-playbook` | 執行 playbook 的指令 |
| `host/deploy/ansible/playbooks/deploy-time-daemon.yml` | playbook 路徑（相對於專案根目錄） |
| `--vault-password-file ~/.vault_pass` | 指定 Vault 密碼檔，Ansible 自動解密 `ghcr_pat` 變數 |

### 成功輸出範例

```
PLAY [Deploy time-daemon to Pi 5 k3s] *****

TASK [Create namespace aku-sw] ************
ok: [localhost]

TASK [Create GHCR imagePullSecret] ********
changed: [localhost]

TASK [Apply time-daemon Deployment] *******
ok: [localhost]

TASK [Apply time-daemon Service] **********
ok: [localhost]

TASK [Wait for time-daemon Pod to be Running]
ok: [localhost]

PLAY RECAP ********************************
localhost : ok=5  changed=1  unreachable=0  failed=0
```

| 狀態 | 說明 |
|------|------|
| `ok` | Task 執行成功，資源已存在且無變化 |
| `changed` | Task 執行成功，資源有被建立或修改 |
| `failed` | Task 失敗，看錯誤訊息排查 |

---

## Section 5：驗證部署

```bash
# 確認 Pod 正在跑
kubectl get pods -n aku-sw

# 確認 Service 和 NodePort
kubectl get service -n aku-sw
```

從開發機測試 gRPC：

```bash
bazel run //host/sw/time:client -- --host 192.168.1.185 --port 30052
```

---

## Section 6：冪等性（Idempotency）

同一個 playbook 跑幾次，結果都一樣，不會重複建立或報錯：

```
第一次跑：namespace 不存在 → 建立 → changed=1
第二次跑：namespace 已存在 → 不動 → ok=1
兩次都不會 failed
```

這叫做**冪等性（Idempotent）**。當 manifest 有修改時，Ansible 只更新有差異的部分。

---

## 本章重點回顧

| 步驟 | 指令 |
|------|------|
| 安裝套件 | `pip install ansible kubernetes` |
| 安裝 collection | `ansible-galaxy collection install kubernetes.core` |
| 建立 Vault 密碼 | `echo "your-password" > ~/.vault_pass && chmod 600 ~/.vault_pass` |
| 加密 PAT | `read -s GHCR_TOKEN && ansible-vault encrypt_string "$GHCR_TOKEN" --vault-password-file ~/.vault_pass --name ghcr_pat > host/deploy/ansible/group_vars/all.yml` |
| 執行部署 | `ansible-playbook host/deploy/ansible/playbooks/deploy-time-daemon.yml --vault-password-file ~/.vault_pass` |

---

## 下一步

Step 7：新增 hello-daemon，學習如何在同一個 k3s 叢集上部署第二個 gRPC 服務。
