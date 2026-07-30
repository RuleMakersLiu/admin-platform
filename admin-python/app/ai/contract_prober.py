"""活契约探针 skill（Phase 4c）：对运行中的后端 backend_runner 发 HTTP 探针，按契约断言接口是否
真起、真响应、字段结构是否一致。

与 backend_scaffold 同构（独立模块 + @skill_registry.register + flow_manager 副作用导入）。
断言逻辑抽自 sandbox_preview_service._smoke_test_generated_apis（status<400 / JSON /
list 类要 result.list、detail 类要 dict）。后端由 backend_runner_service 起（4b-2），
探针直打 direct_backend_url（不经前端 proxy）；调用 direct_backend_url 即刷新 last_active 防回收。
后端未就绪时 fail-open（返回 skipped），不阻塞流水线。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from app.ai.skills import skill_registry

logger = logging.getLogger(__name__)


def _assert_response(spec: Dict[str, Any], response: httpx.Response) -> Dict[str, Any]:
    """对单个探针响应做三层断言（抽自 _smoke_test_generated_apis）。返回带 ok/issue 的结果项。"""
    path = spec.get("path", "")
    method = spec.get("method", "GET")
    expects_list = bool(spec.get("expects_list"))
    status = response.status_code
    base = {"path": path, "method": method, "status": status}

    if status >= 400:
        return {**base, "ok": False, "issue": f"HTTP {status}"}
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return {**base, "ok": False, "issue": f"非 JSON 响应（{content_type}）"}
    try:
        payload = response.json()
    except ValueError:
        return {**base, "ok": False, "issue": "JSON 无法解析"}

    result = payload.get("result") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else None
    if expects_list and (not isinstance(result, dict) or not isinstance(result.get("list"), list)):
        return {**base, "ok": False, "issue": "列表接口未返回 result.list 数组"}
    if not expects_list and not isinstance(result or data or payload, dict):
        return {**base, "ok": False, "issue": "详情接口未返回对象"}
    return {**base, "ok": True, "issue": ""}


@skill_registry.register(
    skill_id="contract_prober",
    name="活契约探针",
    description="对运行中的后端发 HTTP 探针，按契约断言接口是否真起、真响应、字段结构是否一致（4c）",
    category="testing",
    agent_type="SYSTEM",
    input_schema={
        "pipeline_id": {"type": "string"},
        "endpoints": {"type": "array", "description": "契约接口清单 [{path, method, expects_list}]"},
    },
    output_schema={
        "passed": {"type": "boolean"},
        "skipped": {"type": "boolean"},
        "results": {"type": "array"},
        "summary": {"type": "string"},
    },
)
async def contract_prober(
    pipeline_id: str,
    endpoints: List[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """对 backend_runner 起的后端逐个探针 endpoints，返回 {passed, results, summary}。

    后端未就绪（direct_backend_url 为 None）→ skipped（fail-open，不判失败）。
    """
    endpoints = endpoints or []
    from app.services.backend_runner_service import backend_runner_service

    base = backend_runner_service.direct_backend_url(pipeline_id)
    if not base:
        return {"passed": True, "skipped": True, "results": [],
                "summary": "后端未就绪，活契约探针跳过（fail-open）"}

    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for spec in endpoints[:10]:  # 最多探 10 个接口
            method = str(spec.get("method", "GET")).upper()
            raw_path = str(spec.get("path", ""))
            path = raw_path.lstrip("/")
            # 防 SSRF / path 注入：path 必须相对（无 scheme/host/.. 遍历/空格/@）
            if "://" in path or path.startswith("..") or any(c in path for c in ("@", " ")):
                results.append({"path": raw_path, "method": method, "status": 0,
                                "ok": False, "issue": "非法 path（SSRF 防护拒绝）"})
                continue
            url = f"{base}/{path}"
            try:
                resp = await client.request(method, url)
                results.append(_assert_response(spec, resp))
            except Exception as exc:  # noqa: BLE001
                results.append({"path": raw_path, "method": method,
                                "status": 0, "ok": False, "issue": f"请求失败: {exc}"})

    failures = [r for r in results if not r.get("ok")]
    passed = not failures
    if failures:
        summary = f"探针 {len(results)} 个接口，{len(failures)} 个未过：" + "; ".join(
            f"{r['path']}({r['issue']})" for r in failures[:5]
        )
    else:
        summary = f"探针 {len(results)} 个接口，全部通过"
    logger.info("contract_prober[%s]: %s", pipeline_id, summary)
    return {"passed": passed, "skipped": False, "results": results, "summary": summary}
