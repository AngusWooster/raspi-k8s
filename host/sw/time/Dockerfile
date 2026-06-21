# ── Stage 1: builder ─────────────────────────────────────────────
# Install Python packages here; compile tools stay in this stage only.
FROM python:3.11-slim AS builder

WORKDIR /build

# Copy requirements first to leverage Docker layer cache:
# as long as requirements.txt is unchanged, pip install is skipped on rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────
# Final image: only the installed packages + application code.
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder stage into system Python path.
COPY --from=builder /install /usr/local

# Add proto directory to Python module search path so daemon.py can find
# time_service_pb2 without a package prefix (mirrors Bazel's imports=["."])
ENV PYTHONPATH=/app/proto

# Copy generated proto bindings and the daemon.
COPY host/sw/time/proto/time_service_pb2.py      proto/
COPY host/sw/time/proto/time_service_pb2_grpc.py proto/
COPY host/sw/time/daemon.py                       .

# Document the port this service listens on (informational only).
EXPOSE 50052

# ENTRYPOINT is the fixed command; arguments passed via `docker run` are appended.
ENTRYPOINT ["python", "daemon.py"]
