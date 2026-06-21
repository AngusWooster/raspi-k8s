# Step 4b：用 Bazel rules_oci 建置容器映像

> **狀態**：概念說明完整；實作細節待補（標記 `[TODO]` 的章節）。

## 本章目標

了解如何用 Bazel 的 `rules_oci` 取代手動的 `docker build`，讓容器映像的建置也納入 Bazel 的依賴管理與快取系統。

---

## 背景：為什麼要用 rules_oci？

Step 4 用的 `docker build` 是最直接的做法，但它在 Bazel 專案中有個根本缺點：**Bazel 不知道 Docker 做了什麼**。

```
Bazel 世界                         Docker 世界
┌────────────────────────┐         ┌──────────────────────────┐
│  bazel build //...     │         │  docker build ...        │
│                        │         │                          │
│  - 知道所有依賴         │         │  - Bazel 不知道它的存在   │
│  - 精確快取             │         │  - 每次需要手動執行       │
│  - 可重現建置           │         │  - 需要 Docker daemon    │
└────────────────────────┘         └──────────────────────────┘
           ↑ 斷開
```

`rules_oci` 把容器映像的建置帶進 Bazel，讓你可以：

```bash
# 取代 docker build + docker push
bazel run //host/sw/time:push
```

### docker build vs rules_oci 完整比較

| 面向 | `docker build` | `rules_oci` |
|------|---------------|-------------|
| **建置指令** | `docker build -f ... .` | `bazel build //host/sw/time:image` |
| **推送指令** | `docker push ...` | `bazel run //host/sw/time:push` |
| **需要 Docker daemon** | ✅ 是 | ❌ 否（直接操作 OCI layer） |
| **Bazel 快取** | ❌ Bazel 看不到 Docker cache | ✅ 每個 layer 都是 Bazel artifact |
| **ARM64 交叉編譯** | `docker buildx --platform` | 設定 base image 用 ARM64 variant |
| **可重現性** | 取決於 Docker 環境 | 完全由 Bazel 掌控，hermetic build |
| **CI/CD 整合** | 需要 CI 機器裝 Docker | 只需 Bazel，不需要 Docker |
| **學習曲線** | 低（業界標準） | 中（需要了解 OCI 格式與 Bazel rule） |

### 什麼是 OCI？

OCI（Open Container Initiative）是容器映像的開放標準格式。Docker image 本身也是 OCI 格式，`rules_oci` 直接操作這個格式，不需要透過 Docker daemon 作為中介。

---

## rules_oci 的核心概念

### 映像的組成結構

一個容器映像由多個 **layer（層）** 疊加而成，每個 layer 是一個 tar 檔：

```
最終映像
├── layer 1：base image（python:3.11-slim）  ← 從 Registry 拉取
├── layer 2：pip install 的套件              ← pkg_tar 打包
└── layer 3：daemon.py + proto/*.py          ← pkg_tar 打包
```

`rules_oci` 用 `oci_image` 把這些 layer 組合成映像，用 `pkg_tar` 打包每個 layer。

### rules_oci 涉及的 Bazel rule

| Rule | 來源 | 用途 |
|------|------|------|
| `oci_pull` | `rules_oci` | 從 Registry 拉取 base image |
| `oci_image` | `rules_oci` | 把多個 layer 組合成映像 |
| `oci_push` | `rules_oci` | 把映像推送到 Registry |
| `pkg_tar` | `rules_pkg` | 把一組檔案打包成 tar layer |

---

## 專案結構（實作後）

```
raspi-k8s/
├── MODULE.bazel          ← 加入 rules_oci、rules_pkg 依賴 [TODO]
├── host/sw/time/
│   ├── BUILD.bazel       ← 加入 oci_image、oci_push target [TODO]
│   └── Dockerfile        ← 保留，供本機快速測試用
└── doc/
    └── step-4b-rules-oci.md
```

---

## [TODO] Section 1：MODULE.bazel 修改

> **待實作**：在 `MODULE.bazel` 加入 `rules_oci` 和 `rules_pkg` 的依賴宣告，並設定 ARM64 base image 的 `oci_pull`。

將會加入的內容：

```python
# [TODO] 版本待確認
bazel_dep(name = "rules_oci", version = "x.x.x")
bazel_dep(name = "rules_pkg", version = "x.x.x")

# [TODO] 拉取 ARM64 Python base image
oci = use_extension("@rules_oci//oci:extensions.bzl", "oci")
oci.pull(
    name = "python311_slim",
    image = "docker.io/library/python",
    tag = "3.11-slim",
    platforms = ["linux/arm64"],
)
use_repo(oci, "python311_slim")
```

---

## [TODO] Section 2：host/sw/time/BUILD.bazel 修改

> **待實作**：在現有 `BUILD.bazel` 加入 `pkg_tar`、`oci_image`、`oci_push` target。

將會加入的內容：

```python
# [TODO]
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_push")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

# 把程式碼打包成 tar layer
pkg_tar(
    name = "app_tar",
    srcs = [
        ":daemon",
        "//host/sw/time/proto:time_service_proto",
    ],
    # [TODO] 確認路徑設定
)

# 組合映像
oci_image(
    name = "image",
    base = "@python311_slim",
    tars = [":app_tar"],
    entrypoint = ["python", "daemon.py"],
    env = {"PYTHONPATH": "/app/proto"},
)

# 推送到 GHCR
oci_push(
    name = "push",
    image = ":image",
    repository = "ghcr.io/anguswooster/raspi-k8s/time-daemon",
)
```

---

## [TODO] Section 3：建置與推送指令

> **待實作**：驗證以下指令在完成 MODULE.bazel 和 BUILD.bazel 設定後可正確執行。

```bash
# 建置映像（不推送）
bazel build //host/sw/time:image

# 建置並推送到 GHCR
bazel run //host/sw/time:push

# 推送指定 tag（[TODO] 確認 rules_oci 的 tag 設定方式）
bazel run //host/sw/time:push -- --tag v1.0.0
```

---

## [TODO] Section 4：本機測試

> **待實作**：確認如何用 rules_oci 產生的映像在本機執行（不需要 `docker buildx`）。

```bash
# [TODO] rules_oci 可以產生 tarball，再用 docker load 載入本機
bazel build //host/sw/time:image.tar
docker load -i bazel-bin/host/sw/time/image.tar
docker run --rm -p 50052:50052 time-daemon:latest
```

---

## 實作順序建議

當三個 daemon（time、hello、sysmon）都完成後，統一改用 `rules_oci` 效益更大：

1. 確認 `rules_oci` 和 `rules_pkg` 的最新穩定版本
2. 修改 `MODULE.bazel`，加入 `oci_pull` 拉取 ARM64 base image
3. 修改 `host/sw/time/BUILD.bazel`，加入 `oci_image` 和 `oci_push`
4. 驗證 `bazel run //host/sw/time:push` 能成功推送
5. 同樣套用到 hello、sysmon
6. 更新 `commands-bazel.md` 加入容器相關 Bazel 指令

---

## 下一步

目前繼續用 `docker build`（Step 4）完成 K8s 部署流程，`rules_oci` 的實作留待所有 daemon 完成後再統一整合。

Step 5：Kubernetes Manifests — 定義 `Deployment`、`Service`。
