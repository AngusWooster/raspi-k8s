# Step 1：Bazel 基礎

## Bazel 是什麼？

Bazel 是 Google 開源的**建置系統**（Build System）。

你平常寫 Python 可能直接 `python daemon.py` 就跑了，那為什麼需要 Bazel？

| 情境 | 沒有 Bazel | 有 Bazel |
|------|-----------|---------|
| 管理相依套件 | 手動 `pip install`，每台機器不同 | 宣告在 BUILD 檔，所有人一致 |
| 從 `.proto` 產生程式碼 | 手動跑指令，容易忘記 | `bazel build` 自動處理 |
| 跨平台建置（ARM64） | 要自己設環境 | Bazel 處理工具鏈 |
| 大型專案多個服務 | Makefile 越來越難維護 | 每個目錄獨立 BUILD，清楚分離 |

簡單說：**Bazel 讓「從原始碼到可執行檔」這個過程可重現、可自動化。**

---

## 核心概念：Target

Bazel 的基本單位叫做 **Target**，用 `//路徑:名稱` 表示：

```
//host/sw/time:daemon    ← host/sw/time/ 目錄下，名為 daemon 的 target
//host/sw/time:client    ← 同一目錄，名為 client 的 target
//tools:gen_proto        ← tools/ 目錄下，名為 gen_proto 的 target
```

每個 target 在 `BUILD.bazel` 裡定義，例如：

```python
py_binary(
    name = "daemon",        # target 名稱
    srcs = ["daemon.py"],   # 原始碼
    deps = [...],           # 相依的函式庫
)
```

---

## 這個專案的 Bazel 檔案

```
raspi-k8s/
├── MODULE.bazel          ← 專案身份 + 外部套件（rules_python 等）
├── BUILD.bazel           ← 根目錄的 target（pip requirements）
├── .bazelrc              ← Bazel 預設參數
├── .bazelversion         ← 固定 Bazel 版本號
├── requirements.txt      ← pip 套件清單（你手寫）
└── requirements_lock.txt ← pip 鎖定版本（工具產生，確保可重現）
```

每個有程式碼的子目錄也會有自己的 `BUILD.bazel`：

```
host/sw/time/
├── BUILD.bazel           ← 定義 daemon 和 client 這兩個 py_binary
└── proto/
    └── BUILD.bazel       ← 定義 proto 程式碼產生 + py_library
```

---

## 五個檔案的內容與說明

### 1. `.bazelversion`

告訴 Bazelisk（Bazel 的版本管理工具）要用哪個版本。
這樣所有人 `bazel build` 都用同一版本，不會因為版本不同行為不一樣。

```
7.4.1
```

### 2. `.bazelrc`

Bazel 每次執行時自動套用的參數。
放在這裡就不用每次手動輸入。

```
# 使用 bzlmod（MODULE.bazel）管理外部相依
common --enable_bzlmod

# 建置時使用 Python 3
build --python_version=PY3
```

### 3. `MODULE.bazel`

整個專案的「身份證」＋「外部套件宣告」。

類似 `package.json`（Node.js）或 `go.mod`（Go），但這是 Bazel 的格式。

```python
# 這個模組叫 raspi_k8s，版本 0.1.0
module(
    name = "raspi_k8s",
    version = "0.1.0",
)

# 引入 rules_python — 讓 Bazel 支援 Python
bazel_dep(name = "rules_python", version = "0.36.0")

# 設定 Python 工具鏈（用哪個版本的 Python）
python = use_extension("@rules_python//python/extensions:python.bzl", "python")
python.toolchain(
    python_version = "3.11",
    is_default = True,
)

# 設定 pip 套件來源
pip = use_extension("@rules_python//python/extensions:pip.bzl", "pip")
pip.parse(
    hub_name = "pip",
    python_version = "3.11",
    requirements_lock = "//:requirements_lock.txt",  # 鎖定版本檔
)
use_repo(pip, "pip")
```

**為什麼用 `requirements_lock.txt` 而不是 `requirements.txt`？**
`requirements.txt` 只寫 `grpcio>=1.60`（範圍），每次安裝版本可能不同。
`requirements_lock.txt` 鎖定確切版本（如 `grpcio==1.62.1`），確保**任何人任何時候建置結果都一樣**。

### 4. `requirements.txt`

你手寫的直接相依套件：

```
grpcio==1.68.1
grpcio-tools==1.68.1
protobuf==5.29.3
```

| 套件 | 用途 |
|------|------|
| `grpcio` | gRPC runtime（server 和 client 都需要） |
| `grpcio-tools` | 把 `.proto` 檔轉成 Python 程式碼 |
| `protobuf` | Protocol Buffer runtime（序列化/反序列化） |

### 5. `requirements_lock.txt`

由 `pip-compile` 工具從 `requirements.txt` 產生，包含所有**直接＋間接**相依的確切版本。

**你不用手寫，執行以下指令產生：**

```bash
pip-compile requirements.txt -o requirements_lock.txt
```

### 6. `BUILD.bazel`（根目錄）

根目錄的 BUILD 只做一件事：讓 Bazel 可以更新 pip lock file。

```python
load("@pip//:requirements.bzl", "all_requirements")

# 讓你可以執行 bazel run //:pip_requirements.update 來更新 lock file
filegroup(
    name = "pip_requirements",
    srcs = ["requirements.txt"],
)
```

---

## 動手實作

現在我們建立這些檔案，然後驗證 Bazel 能正確初始化。

> 執行順序：建檔 → 安裝 pip-tools → 產生 lock file → 執行 `bazel build` 看看有沒有錯誤

---

## 常見問題

**Q：Bazel 和 Makefile 有什麼不同？**
Makefile 是「告訴電腦每一步怎麼做」（命令式）。
Bazel 是「告訴電腦我要什麼、相依關係是什麼」（宣告式），Bazel 自己決定執行順序和快取。

**Q：MODULE.bazel 和 WORKSPACE 有什麼不同？**
WORKSPACE 是舊格式，MODULE.bazel（bzlmod）是新格式。
本專案用新的 MODULE.bazel，更簡潔，也是 Bazel 7.x 的預設。

**Q：`bazel build` 第一次很慢？**
正常，Bazel 第一次要下載工具鏈（Python 3.11、protoc 等）並快取。
之後只有改動的部分才會重新建置，速度很快。
