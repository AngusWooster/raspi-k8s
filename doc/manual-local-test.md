# 本機測試手冊：time daemon

這份文件讓你從零開始，在開發機上跑起 daemon 和 client 並驗證它們可以溝通。

---

## 前置條件檢查

在開始之前，先確認每一項都 OK：

```bash
# 1. Bazel 版本
bazel version
# 預期輸出包含：Build label: 7.4.1

# 2. venv 是否建立
ls .venv/bin/python3
# 預期：.venv/bin/python3

# 3. proto 檔是否已產生
ls host/sw/time/proto/*.py host/sw/time/proto/*.pyi
# 預期看到四個檔案：
#   time_service_pb2.py
#   time_service_pb2_grpc.py
#   time_service_pb2.pyi
#   time_service_pb2_grpc.pyi
```

如果 venv 不存在，先執行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
./scripts/gen_time_proto.sh
```

---

## 步驟 1：建置

確認程式碼可以被 Bazel 建置：

```bash
bazel build //host/sw/time/...
```

成功的輸出：

```
INFO: Build completed successfully, N total actions
```

如果出錯，看錯誤訊息並對照本文件最後的「常見問題」。

---

## 步驟 2：啟動 daemon（Terminal 1）

**開一個新的終端機**，在專案根目錄執行：

```bash
bazel run //host/sw/time:daemon
```

成功啟動後你會看到：

```
2026-06-20 10:30:00,000 INFO Time service listening on [::]:50052
```

> daemon 會持續執行並等待請求，**不要關掉這個終端機**。

---

## 步驟 3：執行 client（Terminal 2）

**開另一個終端機**，在同樣的專案根目錄執行：

```bash
bazel run //host/sw/time:client
```

成功的輸出：

```
Timestamp  : 2026-06-20T10:30:05.123456+00:00
Unix time  : 1750415405.123456789
Timezone   : CST
Hostname   : your-machine-name
```

---

## 步驟 4：驗證幾個場景

### 場景 A：多次查詢，時間應該遞增

```bash
bazel run //host/sw/time:client
# 等幾秒
bazel run //host/sw/time:client
# Unix time 應該比上一次大
```

### 場景 B：連到不存在的 server（預期出錯）

```bash
bazel run //host/sw/time:client -- --host localhost --port 9999
```

預期輸出（錯誤訊息）：

```
Error: cannot reach localhost:9999
Reason: StatusCode.UNAVAILABLE — ...
```

這代表錯誤處理正常工作。

### 場景 C：自訂 port

**Terminal 1：**
```bash
bazel run //host/sw/time:daemon -- --port 9090
```

**Terminal 2：**
```bash
bazel run //host/sw/time:client -- --port 9090
```

---

## 步驟 5：停止 daemon

在 Terminal 1 按 `Ctrl+C`，daemon 會停止。

---

## 常見問題

### `Address already in use`

```
OSError: [Errno 98] Address already in use
```

Port 50052 被佔用了：

```bash
# 找出是哪個程式在用 50052
lsof -i :50052

# 如果是之前忘記關掉的 daemon，找到 PID 並關掉
kill <PID>

# 或者改用其他 port
bazel run //host/sw/time:daemon -- --port 9090
bazel run //host/sw/time:client -- --port 9090
```

### `Build did NOT complete successfully`

先確認 requirements_lock.txt 是最新的：

```bash
pip-compile requirements.txt -o requirements_lock.txt --allow-unsafe
bazel build //host/sw/time/...
```

### `No module named 'time_service_pb2'`

proto 檔還沒產生：

```bash
./scripts/gen_time_proto.sh
bazel build //host/sw/time/...
```

### client 輸出的 `Hostname` 是開發機名稱而不是 Pi

這是正常的。現在是**本機測試**，daemon 跑在你的開發機上，
所以 `hostname` 回傳的是你的機器名稱。

部署到 Pi 的 K8s 之後，`hostname` 會是 Pod 的名稱（例如 `time-daemon-7d9f8b-xk2p`）。
