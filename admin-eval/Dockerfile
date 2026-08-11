# Build must provide an approved, scanned, signed digest, for example:
# --build-arg PYTHON_BASE_IMAGE=registry.local/base/python@sha256:<64 hex>
ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app
RUN useradd --system --uid 10001 --no-create-home eval
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
USER 10001:10001
EXPOSE 8091
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
