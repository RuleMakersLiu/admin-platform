import httpx
from pathlib import Path

from app.ai.flow_manager import _validate_frontend_preview_code_files
from app.services.sandbox_preview_service import SandboxPreviewService


def test_preview_validator_rejects_stable_without_list_contract():
    files = {
        "src/views/Product/RetailList.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: parameter => api(parameter).then(res => res.result)
    }
  }
}
</script>
""",
        "src/api/product.js": """
import request from '@/utils/request'
export function list (parameter) {
  return request({ url: '/product/retail/list', method: 'get', params: parameter })
}
if (process.env.NODE_ENV === 'development') {
  const Mock = require('mockjs2')
  Mock.mock(/\\/product\\/retail\\/list/, 'get', () => ({
    code: 200,
    result: { data: [], pageNo: 1, pageSize: 10, totalCount: 0 }
  }))
}
""",
    }

    issues = _validate_frontend_preview_code_files(files)

    assert any("必须处理分页对象 list 字段" in issue for issue in issues)
    assert any("列表 mock 缺少 list 数组字段" in issue for issue in issues)
    assert any("列表 mock 缺少分页字段 count" in issue for issue in issues)


def test_preview_validator_accepts_stable_with_consistent_list_contract():
    files = {
        "src/views/Product/RetailList.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: parameter => api(parameter).then(res => res.result || res.data || res)
    }
  },
  methods: {
    normalize (payload) {
      return payload && Array.isArray(payload.list) ? payload : {
        page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: []
      }
    }
  }
}
</script>
""",
        "src/api/product.js": """
import request from '@/utils/request'
export function list (parameter) {
  return request({ url: '/product/retail/list', method: 'get', params: parameter })
}
if (process.env.NODE_ENV === 'development') {
  const Mock = require('mockjs2')
  Mock.mock(/\\/product\\/retail\\/list/, 'get', () => ({
    code: 200,
    result: { page: 1, pageNo: 1, pageSize: 10, count: 1, totalCount: 1, list: [] }
  }))
}
""",
    }

    assert _validate_frontend_preview_code_files(files) == []


def test_preview_validator_accepts_detail_page_without_table_contract():
    files = {
        "src/views/Product/RetailDetail.vue": """
<template>
  <a-card>
    <a-descriptions>
      <a-descriptions-item label="商品名称">{{ detail.productName || '-' }}</a-descriptions-item>
    </a-descriptions>
    <a-button @click="handleBack">返回</a-button>
  </a-card>
</template>
<script>
import { getRetailProductDetail } from '@/api/product'
export default {
  data () {
    return { detail: {} }
  },
  created () {
    getRetailProductDetail({ id: 1 }).then(res => { this.detail = res.result || res.data || {} })
  },
  methods: {
    handleBack () { this.$router.back() }
  }
}
</script>
""",
        "src/api/product.js": """
import request from '@/utils/request'
export function getRetailProductDetail (parameter) {
  return request({ url: '/product/retail/detail', method: 'get', params: parameter })
}
if (process.env.NODE_ENV === 'development') {
  const Mock = require('mockjs2')
  Mock.mock(/\\/product\\/retail\\/detail/, 'get', () => ({
    code: 200,
    result: { productId: '10001', productName: '测试商品' }
  }))
}
""",
    }

    assert _validate_frontend_preview_code_files(files) == []


def test_preview_validator_accepts_miniprogram_page_pair():
    files = {
        "pages/product/detail.wxml": """
<view class="page">
  <view>{{ detail.productName || '-' }}</view>
  <button bindtap="handleBack">返回</button>
</view>
""",
        "pages/product/detail.js": """
Page({
  data: { detail: {} },
  handleBack() { wx.navigateBack() }
})
""",
        "pages/product/detail.wxss": ".page { padding: 24rpx; }",
        "pages/product/detail.json": '{"navigationBarTitleText":"商品详情"}',
        "public/sandbox-miniapp-preview.html": """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>商品详情</title></head>
<body>
  <main id="app">商品详情</main>
  <script>document.getElementById('app').dataset.ready = 'true'</script>
</body>
</html>
""",
    }

    assert _validate_frontend_preview_code_files(files) == []


def test_preview_validator_rejects_miniprogram_page_without_logic_file():
    files = {
        "pages/product/detail.wxml": '<button bindtap="handleBack">返回</button>',
    }

    assert any("缺少同名小程序逻辑文件" in issue for issue in _validate_frontend_preview_code_files(files))


def test_sandbox_preview_installs_miniprogram_html_preview(tmp_path: Path):
    service = SandboxPreviewService()
    files = {
        "pages/product/detail.wxml": "<view>商品详情</view>",
        "pages/product/detail.js": "Page({ data: {} })",
        "public/sandbox-miniapp-preview.html": "<!doctype html><html><body><script></script></body></html>",
    }

    preview_path = service._install_miniapp_html_preview(tmp_path, files)

    assert preview_path == "sandbox-miniapp-preview.html"
    assert (tmp_path / "public" / "sandbox-miniapp-preview.html").exists()


def test_sandbox_proxy_normalizes_common_table_response_shapes():
    service = SandboxPreviewService()
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"data": [{"id": 1}], "pageNo": 2, "pageSize": 10, "totalCount": 86},
    )

    normalized = service._normalize_api_response("api/product/retail/list", response)
    payload = normalized.json()

    assert payload["result"]["list"] == [{"id": 1}]
    assert payload["result"]["page"] == 2
    assert payload["result"]["pageNo"] == 2
    assert payload["result"]["pageSize"] == 10
    assert payload["result"]["count"] == 86
    assert payload["data"]["list"] == [{"id": 1}]


def test_sandbox_preview_extracts_generated_list_api_paths():
    service = SandboxPreviewService()
    files = {
        "src/api/product.js": """
const API_PREFIX = '/product/retail'
export function byTemplate (parameter) {
  return request({ url: `${API_PREFIX}/list`, method: 'get', params: parameter })
}
export function byConcat (parameter) {
  return request({ url: API_PREFIX + '/stock/list', method: 'get', params: parameter })
}
export function byLiteral (parameter) {
  return request({ url: '/promotion/list', method: 'get', params: parameter })
}
export function byDetail (parameter) {
  return request({ url: API_PREFIX + '/detail', method: 'get', params: parameter })
}
"""
    }

    assert service._generated_list_api_paths(files) == [
        "api/product/retail/list",
        "api/product/retail/stock/list",
        "api/promotion/list",
    ]
    assert service._generated_api_probe_specs(files) == [
        {"path": "api/product/retail/detail", "expects_list": False},
        {"path": "api/product/retail/list", "expects_list": True},
        {"path": "api/product/retail/stock/list", "expects_list": True},
        {"path": "api/promotion/list", "expects_list": True},
    ]
