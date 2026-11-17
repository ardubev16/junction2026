"""OpenTelemetry instruments of the pipeline. Without an SDK they do nothing: the deployment runs the
server under `opentelemetry-instrument` (Dockerfile), configured by the OTEL_* variables, which also
traces every request, HTTP call (Wikipedia, the LLM) and SQL statement, and exports HTTP metrics."""

from opentelemetry import metrics, trace

tracer = trace.get_tracer("wikicross")
_meter = metrics.get_meter("wikicross")
STEP_SECONDS = _meter.create_histogram(
    "wikicross.diff.step.duration", unit="s", description="Seconds each /api/diff step took (app.STEPS)")
CACHE_LOOKUPS = _meter.create_counter(
    "wikicross.cache.lookups", description="Cache lookups, by cache (diff, llm) and result (hit, miss)")
