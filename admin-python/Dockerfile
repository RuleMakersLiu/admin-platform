FROM python:3.11-slim AS builder

WORKDIR /app

# builder 也走清华 apt 源（防 build-essential 层缓存失效时默认源国内拉取失败）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
# 含 [dev] extra（pytest/pytest-asyncio/pytest-cov/ruff/...），让镜像可直接跑测试套件
RUN pip install --no-cache-dir -e .[dev] \
      -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

# 说明：曾用 `FROM node:22-slim AS node-runtime` 多阶段拿 node/npm/pnpm，但本机拉 docker hub
# 镜像基本不通（daocloud mirror 401、直连超时），故改在最终阶段用 apt 装 nodejs/npm、pnpm 走淘宝源。
FROM python:3.11-slim

WORKDIR /app

# 系统依赖全部走清华 apt 源（绕开 docker hub）。
# docker-cli（仅客户端，非 docker.io 守护进程）：Phase A 沙箱独立容器化——admin-python 经挂载的
# docker.sock 编排隔离沙箱容器。Debian 的 docker.io 只含 dockerd，CLI 在独立的 docker-cli 包。
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq5 \
    maven \
    nodejs \
    npm \
    curl \
    docker-cli \
    && rm -rf /var/lib/apt/lists/*
# JDK 18（业务项目锁定）：18 非 LTS 已 EOL，trixie apt 源无（仅 21/25），故从华为云镜像下载 OpenJDK 18 tarball。
# JAVA_HOME/bin 放 PATH 最前，确保 `java` 指向 18（apt maven 可能顺带把 openjdk-21 装进 /usr/bin）。
RUN mkdir -p /usr/lib/jvm \
    && curl -fsSL https://mirrors.huaweicloud.com/openjdk/18/openjdk-18_linux-x64_bin.tar.gz -o /tmp/jdk18.tar.gz \
    && tar -xzf /tmp/jdk18.tar.gz -C /usr/lib/jvm \
    && rm /tmp/jdk18.tar.gz
ENV JAVA_HOME=/usr/lib/jvm/jdk-18
ENV PATH="${JAVA_HOME}/bin:${PATH}"
# maven 用阿里云镜像加速依赖下载（容器内构建生成的后端工程；mvn 优先用 $JAVA_HOME 的 JDK18）
RUN mkdir -p /root/.m2 && printf '%s\n' \
    '<settings><mirrors><mirror>' \
    '<id>aliyun</id><mirrorOf>central</mirrorOf>' \
    '<url>https://maven.aliyun.com/repository/public</url>' \
    '</mirror></mirrors></settings>' > /root/.m2/settings.xml
# pnpm：淘宝 npm 源全局安装（nodejs/npm 由 apt 提供，已进 PATH，无需额外 symlink）
RUN npm install -g pnpm@10.11.0 --registry=https://registry.npmmirror.com

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app
# E2E: 安装 chromium 浏览器二进制 + 系统依赖（prototype 阶段 Playwright 断言用）
RUN python -m playwright install --with-deps chromium

# 沙箱降权（阶段 B）：建非根用户（uid/gid 1500）+ maven 镜像配置全局化，放最后保 playwright 缓存不失效。
# 1) 不可信子进程降权到此身份（见 sandbox_security.drop_privilege_kwargs）；容器仍以 root 运行（保源码
#    bind-mount 热更新 / chromium / build 期 pip），仅子进程降权，故不加 USER。
# 2) 降权后 mvn（uid 1500）无法进入 700 的 /root 读 /root/.m2/settings.xml → 把镜像配置写入全局
#    /usr/share/maven/conf/settings.xml（世界可读），否则回退 Maven Central 挂起。
RUN groupadd -r sandbox -g 1500 && useradd -r -u 1500 -g sandbox -M -d /tmp -s /usr/sbin/nologin sandbox \
    && mkdir -p /usr/share/maven/conf \
    && cp /root/.m2/settings.xml /usr/share/maven/conf/settings.xml

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8081/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
