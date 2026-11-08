# Optional always-on runtime for AIBA's EXISTING /api/layers adapter.
# This Dockerfile does not provision a host or add AIS/OpenSky credentials.
FROM python:3.11-slim
WORKDIR /app
COPY dashboard/collect_layers.py /app/dashboard/collect_layers.py
COPY requirements-layers.txt /app/requirements-layers.txt
RUN python -m pip install --no-cache-dir -r requirements-layers.txt \
    && useradd --uid 10001 --create-home atlas \
    && mkdir -p /app/public /app/runtime \
    && chown -R atlas:atlas /app/runtime /app/public
USER atlas
EXPOSE 8765
ENV PYTHONUNBUFFERED=1
# Exposes /api/layers only when published through a TLS reverse proxy.
CMD ["python","dashboard/collect_layers.py","--serve","/app/public","--output","/app/runtime/layers.json","--bind","0.0.0.0","--port","8765","--interval","120"]
