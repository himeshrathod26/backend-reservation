from prometheus_client import Counter, Gauge, Histogram

RES_CONFIRMED = Counter("reservations_confirmed_total", "Confirmed reservations")
RES_DECLINED = Counter("reservations_declined_total", "Declined reservations", ["reason"])
REQS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "path"])
SEATS_AVAILABLE = Gauge("seats_available", "Available seats", ["show_id"])
