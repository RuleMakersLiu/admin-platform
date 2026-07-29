FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
# 含 [dev] extra（pytest/pytest-asyncio/pytest-cov/ruff/...），让镜像可直接跑测试套件
RUN pip install --no-cache-dir -e .[dev] \
      -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

FROM node:22-slim AS node-runtime
RUN npm install -g pnpm@10.11.0

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq5 \
    openjdk-17-jdk-headless \
    maven \
    && rm -rf /var/lib/apt/lists/*
# 后端沙箱 runner（4b-2）：生成的 Java Spring Boot 工程在本容器内 mvn 打包 + java -jar 起服务
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${PATH}:${JAVA_HOME}/bin"
# maven 用阿里云镜像加速依赖下载（容器内构建生成的后端工程）
RUN mkdir -p /root/.m2 && printf '%s\n' \
    '<settings><mirrors><mirror>' \
    '<id>aliyun</id><mirrorOf>central</mirrorOf>' \
    '<url>https://maven.aliyun.com/repository/public</url>' \
    '</mirror></mirrors></settings>' > /root/.m2/settings.xml

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app
# E2E: 安装 chromium 浏览器二进制 + 系统依赖（prototype 阶段 Playwright 断言用）
RUN python -m playwright install --with-deps chromium
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf ../lib/node_modules/pnpm/bin/pnpm.cjs /usr/local/bin/pnpm \
    && ln -sf ../lib/node_modules/pnpm/bin/pnpx.cjs /usr/local/bin/pnpx

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8081/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
