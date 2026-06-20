# Bazel 指令參考

## 指令結構說明

```
bazel  <動作>  <target>           [-- <程式參數>]
       build   //路徑:名稱
       run
       test
       query
       clean
```

- `//` 代表 workspace 根目錄
- `:` 後面是 target 名稱
- `//host/sw/time/...` 表示 `host/sw/time/` 底下所有 target

---

## 1. 查詢（Query）

了解專案結構，不會建置任何東西。

```bash
# 列出所有 target
bazel query //...

# 列出某個目錄的 target
bazel query //host/sw/time/...
bazel query //tools/...

# 查詢某個 target 依賴哪些東西
bazel query "deps(//host/sw/time:daemon)"

# 查詢誰依賴某個 target
bazel query "rdeps(//..., //host/sw/time/proto:time_service_proto)"
```

---

## 2. 建置（Build）

把原始碼編譯成可執行檔或函式庫，但**不執行**。

```bash
# 建置 proto 程式碼產生
bazel build //host/sw/time/proto:gen_time_proto

# 建置 proto py_library（包含相依解析）
bazel build //host/sw/time/proto:time_service_proto

# 建置 time daemon（server）
bazel build //host/sw/time:daemon

# 建置 time client
bazel build //host/sw/time:client

# 建置 sw/ 底下所有 target（未來新增 hello, sysmon 後一起建置）
bazel build //host/sw/...

# 建置整個專案所有 target
bazel build //...
```

輸出位置：`bazel-bin/host/sw/time/daemon`

---

## 3. 執行（Run）

建置後**直接執行**（只能用在 `py_binary`、`cc_binary` 等可執行 target）。

```bash
# 執行 time daemon（在本機跑 gRPC server，port 50052）
bazel run //host/sw/time:daemon

# 執行 time client（連到本機 daemon）
bazel run //host/sw/time:client

# 執行 client 並傳入參數（-- 之後是程式的 argv）
bazel run //host/sw/time:client -- --host localhost --port 50052

# 執行 client 連到 Pi（需 Pi 上已有 daemon 在跑）
bazel run //host/sw/time:client -- --host <Pi-IP> --port 30052

# 執行 proto 產生工具（測試用）
bazel run //tools:gen_proto -- host/sw/time/proto/time_service.proto /tmp/out
```

---

## 4. 測試（Test）

執行 `py_test` target（目前尚未新增，Phase 2 以後會用到）。

```bash
# 執行某個 target 的測試
bazel test //host/sw/time:daemon_test

# 執行所有測試
bazel test //...

# 顯示測試輸出（預設只顯示失敗的）
bazel test //... --test_output=all
```

---

## 5. 相依套件（Pip）

管理 Python pip 套件。

```bash
# 更新 requirements_lock.txt（修改 requirements.txt 後執行）
# 等同於 pip-compile，但透過 Bazel 確保版本一致
bazel run //:requirements.update

# 查詢某個 pip 套件的 target 名稱
bazel query "@pip//..."
bazel query "@pip//grpcio:pkg"
```

---

## 6. 清除快取（Clean）

```bash
# 清除建置輸出（bazel-bin 等 symlink）
bazel clean

# 完整清除，包含下載的工具鏈和外部套件（慢，但乾淨）
bazel clean --expunge
```

> 通常不需要手動 clean，Bazel 會自動追蹤哪些需要重建。
> 遇到奇怪的 cache 問題才用 `--expunge`。

---

## 7. 資訊與除錯

```bash
# 顯示 Bazel 版本
bazel version

# 顯示某個 target 的詳細資訊（型別、屬性）
bazel query --output=build //host/sw/time:daemon

# 顯示建置時的詳細 log
bazel build //host/sw/time:daemon --verbose_failures

# 顯示所有執行的 action（方便 debug genrule）
bazel build //host/sw/time/proto:gen_time_proto --subcommands
```

---

## 8. 本專案完整開發流程

```bash
# 第一次設定
pip-compile requirements.txt -o requirements_lock.txt --allow-unsafe

# 每次開發循環
bazel build //host/sw/time/...        # 建置
bazel run //host/sw/time:daemon &     # 背景執行 server
bazel run //host/sw/time:client       # 測試 client

# 新增或修改 proto 後
bazel build //host/sw/time/proto:gen_time_proto  # 重新產生

# push 前確認全部可建置
bazel build //...
```

---

## Target 命名對照表

| Target | 對應檔案 | 型別 |
|--------|----------|------|
| `//tools:gen_proto` | `tools/gen_proto.py` | `py_binary` |
| `//host/sw/time/proto:gen_time_proto` | `time_service_pb2.py` + `_grpc.py` | `genrule` |
| `//host/sw/time/proto:time_service_proto` | 上面兩個 + deps | `py_library` |
| `//host/sw/time:daemon` | `host/sw/time/daemon.py` | `py_binary` |
| `//host/sw/time:client` | `host/sw/time/client.py` | `py_binary` |
| `//host/sw/hello:daemon` | `host/sw/hello/daemon.py` | `py_binary`（待建立）|
| `//host/sw/sysmon:daemon` | `host/sw/sysmon/daemon.py` | `py_binary`（待建立）|
