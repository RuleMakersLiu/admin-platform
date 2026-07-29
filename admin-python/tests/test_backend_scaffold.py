"""Phase 4b 增量一：后端工程脚手架兜底 + Java Dockerfile / 探测的单测。"""
from pathlib import Path

import pytest

from app.ai import backend_scaffold as bs
from app.ai.pipeline_skills import _detect_project_type, _generate_dockerfile


# ---------- is_java_backend ----------

def test_is_java_backend_true_for_java_file():
    assert bs.is_java_backend({"src/main/java/com/x/Foo.java": "x"}) is True


def test_is_java_backend_true_for_pom():
    assert bs.is_java_backend({"pom.xml": "<x/>"}) is True


def test_is_java_backend_false_for_python():
    assert bs.is_java_backend({"app/main.py": "x"}) is False


def test_is_java_backend_false_empty():
    assert bs.is_java_backend({}) is False


# ---------- 包推断 ----------

def test_common_package_prefix_strips_layers():
    pkgs = ["com.acme.ctrl.UserController", "com.acme.service.UserService", "com.acme.entity.User"]
    assert bs.common_package_prefix(pkgs) == "com.acme"


def test_common_package_prefix_no_common():
    assert bs.common_package_prefix(["com.a.x", "org.b.y"]) == ""


def test_detect_base_package_fallback():
    # 无可推断包 → 默认
    assert bs.detect_base_package({"README.md": "x"}) == "com.example.demo"


def test_detect_base_package_from_path():
    files = {"src/main/java/com/foo/bar/controller/X.java": "package com.foo.bar.controller;"}
    assert bs.detect_base_package(files) == "com.foo.bar"


# ---------- ensure_backend_scaffold ----------

def _biz_files():
    return {
        "src/main/java/com/acme/controller/UserController.java": "package com.acme.controller;",
        "src/main/java/com/acme/service/UserService.java": "package com.acme.service;",
        "src/main/java/com/acme/mapper/UserMapper.java": "package com.acme.mapper;",
        "src/main/java/com/acme/entity/User.java": "package com.acme.entity;",
        "db/schema.sql": "CREATE TABLE user (...)",
    }


def test_ensure_scaffold_injects_all_when_missing():
    res = bs.ensure_backend_scaffold(_biz_files())
    assert res["is_java"] is True
    assert res["base_package"] == "com.acme"
    injected = res["injected_files"]
    assert "pom.xml" in injected
    assert "src/main/resources/application.yml" in injected
    # 主类生成在基础包下
    main_path = "src/main/java/com/acme/Application.java"
    assert main_path in injected
    assert "@SpringBootApplication" in injected[main_path]
    assert "package com.acme;" in injected[main_path]


def test_pom_contains_spring_boot_and_mybatis():
    res = bs.ensure_backend_scaffold(_biz_files())
    pom = res["injected_files"]["pom.xml"]
    assert "spring-boot-starter-parent" in pom
    assert "mybatis-plus-spring-boot3-starter" in pom
    assert "mysql-connector-j" in pom
    assert "<groupId>com.acme</groupId>" in pom


def test_application_yml_has_mysql_datasource():
    res = bs.ensure_backend_scaffold(_biz_files())
    yml = res["injected_files"]["src/main/resources/application.yml"]
    assert "jdbc:mysql://" in yml
    assert "${MYSQL_HOST" in yml
    assert "8080" in yml


def test_ensure_scaffold_skips_when_pom_and_main_present():
    files = _biz_files()
    files["pom.xml"] = "<project/>"
    files["src/main/java/com/acme/Application.java"] = (
        "package com.acme;\n@SpringBootApplication\npublic class Application {}"
    )
    files["src/main/resources/application.yml"] = "server:\n  port: 8081"
    res = bs.ensure_backend_scaffold(files)
    assert res["injected_files"] == {}  # 齐全 → 不注入


def test_ensure_scaffold_skips_non_java():
    res = bs.ensure_backend_scaffold({"app/main.py": "print(1)"})
    assert res["is_java"] is False
    assert res["injected_files"] == {}


# ---------- backend_scaffolder skill 写盘 ----------

@pytest.mark.asyncio
async def test_backend_scaffolder_writes_files(tmp_path):
    res = await bs.backend_scaffolder(str(tmp_path), _biz_files())
    assert res["is_java"] is True
    assert (tmp_path / "pom.xml").exists()
    assert (tmp_path / "src" / "main" / "java" / "com" / "acme" / "Application.java").exists()
    assert (tmp_path / "src" / "main" / "resources" / "application.yml").exists()


# ---------- Java Dockerfile + 探测 ----------

def test_generate_dockerfile_java_is_multistage_maven():
    df = _generate_dockerfile("java")
    assert "maven:3.9-eclipse-temurin-17" in df
    assert "eclipse-temurin:17-jre" in df
    assert "mvn -B package -DskipTests" in df
    assert "EXPOSE 8080" in df


def test_detect_project_type_java_from_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    assert _detect_project_type(str(tmp_path)) == "java"


def test_detect_project_type_java_from_src_layout(tmp_path):
    jf = tmp_path / "src" / "main" / "java" / "com" / "x"
    jf.mkdir(parents=True)
    (jf / "Foo.java").write_text("x")
    assert _detect_project_type(str(tmp_path)) == "java"


def test_detect_project_type_node(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert _detect_project_type(str(tmp_path)) == "node"


def test_detect_project_type_python_default(tmp_path):
    assert _detect_project_type(str(tmp_path)) == "python"
