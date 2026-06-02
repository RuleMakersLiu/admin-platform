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


def test_sandbox_preview_patches_stable_response_contract():
    service = SandboxPreviewService()
    content = """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: parameter => getRetailList(parameter).then(res => {
        const result = res.result || res.data || res
        return {
          pageNo: result.pageNo || result.page || 1,
          pageSize: result.pageSize || 10,
          totalCount: result.totalCount || result.count || 0,
          totalPage: result.totalPage || Math.ceil((result.totalCount || 0) / (result.pageSize || 10)),
          data: Array.isArray(result.list) ? result.list : []
        }
      })
    }
  }
}
</script>
"""

    patched = service._patch_generated_vue_content(content)

    assert "const list =" in patched
    assert "page: pageNo" in patched
    assert "count: totalCount" in patched
    assert "list," in patched
    assert "data: list" in patched


def test_sandbox_preview_patches_stable_response_contract_without_page_field():
    service = SandboxPreviewService()
    content = """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: parameter => getRetailList(parameter).then(res => {
        const result = res.result || res.data || res
        return {
          pageNo: result.pageNo || result.page || 1,
          pageSize: result.pageSize || 10,
          totalCount: result.totalCount || result.count || 0,
          count: result.totalCount || result.count || 0,
          list: Array.isArray(result.list || result.data) ? (result.list || result.data) : []
        }
      })
    }
  }
}
</script>
"""

    patched = service._patch_generated_vue_content(content)

    assert "page: pageNo" in patched
    assert "count: totalCount" in patched
    assert "list," in patched


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

    assert service._generated_api_probe_specs(files) == [
        {"path": "api/product/retail/detail", "expects_list": False},
        {"path": "api/product/retail/list", "expects_list": True},
        {"path": "api/product/retail/stock/list", "expects_list": True},
        {"path": "api/promotion/list", "expects_list": True},
    ]


def test_sandbox_preview_ignores_commented_api_paths():
    service = SandboxPreviewService()
    files = {
        "src/api/product.js": """
import request from '@/utils/request'

export function getRetailList (parameter) {
  // return request({ url: '/product/retail/list', method: 'get', params: parameter })
  return Promise.resolve({ result: { list: [], pageNo: 1, pageSize: 10, totalCount: 0 } })
}

/*
export function oldApi () {
  return request({ url: '/legacy/list', method: 'get' })
}
*/
"""
    }

    assert service._generated_api_probe_specs(files) == []


def test_vue_cli_preview_keeps_original_dev_server_and_routes_wds_resources(tmp_path: Path):
    service = SandboxPreviewService()
    root = tmp_path / "web-product-agent"
    root.mkdir()
    (root / "package.json").write_text(
        '{"scripts":{"serve":"vue-cli-service serve"}}',
        encoding="utf-8",
    )
    (root / "vue.config.js").write_text("const vueConfig = {}\nmodule.exports = vueConfig\n", encoding="utf-8")

    command = service._dev_command(root, 43000)
    service._patch_vue_cli_preview_base(root)
    vue_config = (root / "vue.config.js").read_text(encoding="utf-8")

    assert "--no-inline" not in command
    assert "--no-hot" not in command
    assert "historyApiFallback" in vue_config
    assert "disableDotRule" in vue_config
    assert "SANDBOX_PREVIEW_PUBLIC_PATH_PATCH_V4" in vue_config
    assert "vueConfig.devServer.public = process.env.VUE_APP_SANDBOX_PREVIEW_PUBLIC || 'localhost'" in vue_config
    assert "vueConfig.devServer.sockPath = process.env.VUE_APP_SANDBOX_PREVIEW_BASE + 'sockjs-node'" in vue_config
    assert "delete vueConfig.devServer.proxy['sockjs-node']" in vue_config
    assert "delete vueConfig.devServer.proxy['/api'].pathRewrite" in vue_config
    assert "vueConfig.devServer.inline = false" in vue_config


def test_vue_cli_service_patch_disables_wds_client_in_sandbox(tmp_path: Path):
    service = SandboxPreviewService()
    root = tmp_path / "web-product-agent"
    serve_js = root / "node_modules" / "@vue" / "cli-service" / "lib" / "commands" / "serve.js"
    serve_js.parent.mkdir(parents=True)
    serve_js.write_text(
        """
function serve () {
    // inject dev & hot-reload middleware entries
    if (!isProduction) {
      addDevClientToEntry(webpackConfig, devClients)
    }
}
""",
        encoding="utf-8",
    )

    service._patch_vue_cli_service_no_hmr(root)

    patched = serve_js.read_text(encoding="utf-8")
    assert "SANDBOX_PREVIEW_DISABLE_WDS_CLIENT_PATCH" in patched
    assert "if (!isProduction && !process.env.VUE_APP_SANDBOX_PREVIEW_DISABLE_WDS_CLIENT)" in patched


def test_preview_api_base_does_not_double_api_prefix_for_original_project(tmp_path: Path):
    service = SandboxPreviewService()
    root = tmp_path / "web-product-agent"
    api_dir = root / "src" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "index.js").write_text("export default { login: '/api/product/admins/login' }\n", encoding="utf-8")

    assert (
        service._api_base_url_for_preview(root, {"VUE_APP_API_BASE_URL": "/api"}, "pipe_demo")
        == "/api/flow/pipeline/pipe_demo/sandbox-preview"
    )


def test_preview_proxy_targets_require_explicit_api_proxy(monkeypatch):
    service = SandboxPreviewService()
    monkeypatch.setattr("app.services.sandbox_preview_service.settings.pipeline_preview_api_proxy", "")

    try:
        service._preview_proxy_targets({"VUE_APP_SOCKET_HOST": "http://dzg-dev_wma.gemantic.com"})
    except RuntimeError as exc:
        assert "VUE_APP_PROXY" in str(exc)
    else:
        raise AssertionError("VUE_APP_SOCKET_HOST must not be used as API proxy fallback")


def test_preview_proxy_targets_use_configured_test_api_proxy(monkeypatch):
    service = SandboxPreviewService()
    monkeypatch.setattr("app.services.sandbox_preview_service.settings.pipeline_preview_api_proxy", "https://malladmin-jdagent.hctest.tech/")

    targets = service._preview_proxy_targets({"VUE_APP_SOCKET_HOST": "http://dzg-dev_wma.gemantic.com"})

    assert targets == {
        "api": "https://malladmin-jdagent.hctest.tech",
        "java": "https://malladmin-jdagent.hctest.tech",
        "log": "https://malladmin-jdagent.hctest.tech",
    }
