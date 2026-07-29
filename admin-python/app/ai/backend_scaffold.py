"""后端工程脚手架兜底：确保生成的后端代码是完整可构建的工程（Phase 4b 增量一）。

backend_dev 的 LLM 产物通常只含业务代码（Controller/Service/Entity/SQL），缺 pom.xml /
@SpringBootApplication 主类 / application.yml → 不可独立构建。本模块在 code_writer 写盘后
兜底：检测 Java 包结构，补齐缺失的 pom.xml、主类、application.yml（与前端 _ensure_vite_scaffold
同理——不信任 LLM 一定产出脚手架，由平台保证可构建）。

仅对 Java Spring Boot（默认后端技术栈）生效；非 Java 直接返回。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.ai.skills import skill_registry

logger = logging.getLogger(__name__)

# 末端的分层包名，推断基础包时应剥离（com.x.controller → com.x）
_LAYER_PACKAGES = {
    "controller", "controllers", "service", "services", "dao", "mapper", "mappers",
    "entity", "entities", "model", "models", "domain", "dto", "vo", "config",
    "configuration", "common", "util", "utils", "web", "api", "impl", "interceptor",
}


def _norm(p: str) -> str:
    return str(p).replace("\\", "/")


def is_java_backend(code_files: Dict[str, str]) -> bool:
    if not code_files:
        return False
    for p in code_files:
        s = _norm(p)
        if s.endswith(".java") and "src/main/java/" in s:
            return True
        if s.endswith(("pom.xml", "build.gradle", "build.gradle.kts")):
            return True
    return False


def _collect_java_packages(code_files: Dict[str, str]) -> List[str]:
    pkgs: List[str] = []
    for p, content in code_files.items():
        s = _norm(p)
        if not s.endswith(".java"):
            continue
        m = re.search(r"^\s*package\s+([\w.]+)\s*;", content or "", re.MULTILINE)
        if m:
            pkgs.append(m.group(1).strip())
            continue
        idx = s.find("src/main/java/")
        if idx >= 0:
            rel = s[idx + len("src/main/java/"):].rsplit("/", 1)[0]
            if rel:
                pkgs.append(rel.replace("/", "."))
    return pkgs


def common_package_prefix(pkgs: List[str]) -> str:
    """多个业务包（com.x.controller, com.x.service）→ 公共基础包（com.x），剥离末端分层名。"""
    if not pkgs:
        return ""
    splits = [p.split(".") for p in pkgs]
    prefix: List[str] = []
    for parts in zip(*splits):
        if len(set(parts)) == 1:
            prefix.append(parts[0])
        else:
            break
    while len(prefix) >= 3 and prefix[-1] in _LAYER_PACKAGES:
        prefix.pop()
    return ".".join(prefix)


def detect_base_package(code_files: Dict[str, str]) -> str:
    pkgs = _collect_java_packages(code_files)
    base = common_package_prefix(pkgs)
    if len(base.split(".")) >= 2:
        return base
    return "com.example.demo"


def find_spring_boot_main(code_files: Dict[str, str]) -> Optional[str]:
    """返回已存在的 @SpringBootApplication 主类路径（存在则不重复生成）。"""
    for p, content in code_files.items():
        s = _norm(p)
        if s.endswith(".java") and "@SpringBootApplication" in (content or ""):
            return s
    return None


def pom_xml(base_pkg: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.5</version>
        <relativePath/>
    </parent>
    <groupId>{base_pkg}</groupId>
    <artifactId>generated-backend</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>generated-backend</name>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>com.baomidou</groupId>
            <artifactId>mybatis-plus-spring-boot3-starter</artifactId>
            <version>3.5.5</version>
        </dependency>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludes>
                        <exclude>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                        </exclude>
                    </excludes>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
"""


def application_yml() -> str:
    return """server:
  port: 8080

spring:
  application:
    name: generated-backend
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
    url: jdbc:mysql://${MYSQL_HOST:127.0.0.1}:${MYSQL_PORT:3306}/${MYSQL_DB:admin_db}?useUnicode=true&characterEncoding=utf8&useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true
    username: ${MYSQL_USER:root}
    password: ${MYSQL_PASSWORD:root}

mybatis-plus:
  configuration:
    map-underscore-to-camel-case: true
    log-impl: org.apache.ibatis.logging.stdout.StdOutImpl
  global-config:
    db-config:
      logic-delete-field: isDeleted
      logic-delete-value: 1
      logic-not-delete-value: 0

logging:
  level:
    com: info
"""


def main_java(base_pkg: str) -> Tuple[str, str]:
    pkg_dir = base_pkg.replace(".", "/")
    path = f"src/main/java/{pkg_dir}/Application.java"
    content = f"""package {base_pkg};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.mybatis.spring.annotation.MapperScan;

@SpringBootApplication
@MapperScan({{"{base_pkg}.**.mapper", "{base_pkg}.**.dao"}})
public class Application {{
    public static void main(String[] args) {{
        SpringApplication.run(Application.class, args);
    }}
}}
"""
    return path, content


def ensure_backend_scaffold(code_files: Dict[str, str]) -> Dict[str, Any]:
    """纯逻辑：返回应补齐的文件 {path: content}。is_java=False 时返回空 injected_files。"""
    if not is_java_backend(code_files):
        return {"is_java": False, "injected_files": {}, "base_package": ""}

    base_pkg = detect_base_package(code_files)
    injected: Dict[str, str] = {}

    has_build = any(
        _norm(p).endswith(("pom.xml", "build.gradle", "build.gradle.kts")) for p in code_files
    )
    if not has_build:
        injected["pom.xml"] = pom_xml(base_pkg)

    if not find_spring_boot_main(code_files):
        path, content = main_java(base_pkg)
        injected[path] = content

    has_config = any(
        _norm(p).endswith((
            "application.yml", "application.yaml", "application.properties",
            "bootstrap.yml", "bootstrap.yaml",
        ))
        for p in code_files
    )
    if not has_config:
        injected["src/main/resources/application.yml"] = application_yml()

    return {"is_java": True, "injected_files": injected, "base_package": base_pkg}


@skill_registry.register(
    skill_id="backend_scaffolder",
    name="后端工程脚手架兜底",
    description="补齐 Java Spring Boot 缺失的 pom.xml/主类/application.yml，保证可独立构建",
    category="development",
    agent_type="SYSTEM",
    input_schema={"workspace_path": {"type": "string"}, "code_files": {"type": "object"}},
    output_schema={
        "is_java": {"type": "boolean"},
        "injected_files": {"type": "object"},
        "base_package": {"type": "string"},
    },
)
async def backend_scaffolder(
    workspace_path: str, code_files: Optional[Dict[str, str]] = None, **kwargs
) -> Dict[str, Any]:
    result = ensure_backend_scaffold(code_files or {})
    injected = result["injected_files"]
    if injected:
        root = Path(workspace_path)
        for rel, content in injected.items():
            fp = root / rel
            if not fp.exists():
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
        logger.info(
            "backend_scaffolder: injected %s (base_pkg=%s)",
            list(injected.keys()), result["base_package"],
        )
    return result
