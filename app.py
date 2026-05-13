import os
import time
from functools import wraps

from flask import Flask, Response

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    multiprocess,
    REGISTRY,
)

app = Flask(__name__)

# =========================================================
# PROMETHEUS METRICS
# =========================================================

REQUEST_COUNTER = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["endpoint"],
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
        10,
    ),
)

IN_PROGRESS_REQUESTS = Gauge(
    "http_requests_in_progress",
    "In-progress HTTP requests",
    ["endpoint"],
)

# =========================================================
# DECORATOR
# =========================================================

def monitor_requests(endpoint_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):

            with IN_PROGRESS_REQUESTS.labels(
                endpoint=endpoint_name
            ).track_inprogress():

                start_time = time.time()

                try:
                    response = f(*args, **kwargs)

                    REQUEST_COUNTER.labels(
                        endpoint=endpoint_name,
                        status="200",
                    ).inc()

                    return response

                except Exception:
                    REQUEST_COUNTER.labels(
                        endpoint=endpoint_name,
                        status="500",
                    ).inc()
                    raise

                finally:
                    duration = time.time() - start_time

                    REQUEST_DURATION.labels(
                        endpoint=endpoint_name
                    ).observe(duration)

        return decorated_function

    return decorator


# =========================================================
# APPLICATION ENDPOINTS
# =========================================================

@app.route("/")
@monitor_requests("/")
def home():
    return "Production Monitoring Enabled"


@app.route("/api/decorated")
@monitor_requests("/api/decorated")
def decorated_endpoint():
    time.sleep(0.5)
    return "Decorated Response"


# =========================================================
# PROMETHEUS METRICS ENDPOINT
# =========================================================

@app.route("/metrics")
def metrics():

    # Multiprocess mode for Gunicorn
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:

        registry = CollectorRegistry()

        multiprocess.MultiProcessCollector(registry)

        data = generate_latest(registry)

    else:
        data = generate_latest(REGISTRY)

    return Response(
        data,
        mimetype=CONTENT_TYPE_LATEST,
    )


# =========================================================
# GUNICORN HOOK
# =========================================================

def child_exit(server, worker):
    """
    Gunicorn hook for cleaning dead worker metrics.
    """
    multiprocess.mark_process_dead(worker.pid)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
