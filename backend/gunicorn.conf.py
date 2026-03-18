"""
Gunicorn configuration for Safebot production server.

Uses UvicornWorker to support FastAPI async handlers.
"""

import multiprocessing

# ── Worker ────────────────────────────────────────────────────────────────────
worker_class = "uvicorn.workers.UvicornWorker"
# 2 * CPU + 1 is the standard Gunicorn recommendation for I/O-bound workers
workers = multiprocessing.cpu_count() * 2 + 1
threads = 1  # UvicornWorker is single-threaded inside; concurrency via async

# ── Binding ───────────────────────────────────────────────────────────────────
bind = "0.0.0.0:8000"

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout = 30        # Kill worker if no response in 30s
keepalive = 2       # Seconds to wait for requests on a keep-alive connection
graceful_timeout = 30

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = "-"     # stdout
errorlog = "-"      # stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sms'

# ── Process Naming ────────────────────────────────────────────────────────────
proc_name = "safebot"
