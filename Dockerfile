# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    KADAL_DB_PATH=/data/kadal_kural.db
RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
COPY --from=build /install /usr/local
USER app
WORKDIR /home/app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
CMD ["uvicorn", "kadal_kural.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
