from pathlib import Path

from app.ai.flow_manager import (
    _auto_fix_existing_feature_from_original,
    _auto_fix_frontend_preview_code_files,
    _frontend_existing_page_candidates,
    _frontend_fallback_page_candidates,
    _frontend_relevant_existing_page_paths,
    _validate_frontend_preview_code_files,
)
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


def test_preview_auto_fix_repairs_stable_missing_page_and_count_fields():
    files = {
        "src/views/Product/RetailList.vue": """
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
          list: Array.isArray(result.list) ? result.list : []
        }
      })
    }
  }
}
</script>
""",
        "src/api/product.js": """
import request from '@/utils/request'
export function getRetailList (parameter) {
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

    assert any("分页字段 page" in issue for issue in _validate_frontend_preview_code_files(files))
    assert any("分页字段 count" in issue for issue in _validate_frontend_preview_code_files(files))

    fixed, fixes = _auto_fix_frontend_preview_code_files(files)

    assert fixes
    assert "page: pageNo" in fixed["src/views/Product/RetailList.vue"]
    assert "count: totalCount" in fixed["src/views/Product/RetailList.vue"]
    assert _validate_frontend_preview_code_files(fixed) == []


def test_preview_auto_fix_repairs_stable_return_with_precomputed_list():
    files = {
        "src/views/product/retail/List.vue": """
<template>
  <s-table :data="loadData" />
</template>
<script>
import { getProductRetailList } from '@/api/product'
export default {
  data () {
    return {
      loadData: parameter => {
        return getProductRetailList(parameter)
          .then(res => {
            const result = res.result || res.data || res || {}
            const list = Array.isArray(result.list) ? result.list : []
            return {
              pageNo: result.pageNo || result.page || parameter.pageNo || 1,
              pageSize: result.pageSize || parameter.pageSize || 10,
              totalCount: result.totalCount || result.count || 0,
              totalPage: result.totalPage || Math.ceil((result.totalCount || result.count || 0) / (result.pageSize || parameter.pageSize || 10)),
              list: list
            }
          })
      }
    }
  }
}
</script>
""",
        "src/api/product.js": """
export function getProductRetailList () {
  return Promise.resolve({
    result: { page: 1, pageNo: 1, pageSize: 10, count: 1, totalCount: 1, list: [] }
  })
}
""",
    }

    assert any("分页字段 page" in issue for issue in _validate_frontend_preview_code_files(files))
    assert any("分页字段 count" in issue for issue in _validate_frontend_preview_code_files(files))

    fixed, fixes = _auto_fix_frontend_preview_code_files(files)

    assert fixes
    assert "page: result.pageNo || result.page || parameter.pageNo || 1" in fixed["src/views/product/retail/List.vue"]
    assert "count: result.totalCount || result.count || 0" in fixed["src/views/product/retail/List.vue"]
    assert _validate_frontend_preview_code_files(fixed) == []


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


def test_preview_validator_does_not_flag_api_module_array_helpers_as_first_screen_risk():
    files = {
        "src/views/Product/RetailList.vue": """
<template><s-table :data="loadData" /></template>
<script>
import { list } from '@/api/product'
export default {
  data () {
    return {
      loadData: parameter => list(parameter).then(res => {
        const payload = res.result || res.data || res
        const rows = Array.isArray(payload.list) ? payload.list : []
        return { page: 1, pageNo: 1, pageSize: 10, count: rows.length, totalCount: rows.length, list: rows }
      })
    }
  }
}
</script>
""",
        "src/api/product.js": """
import request from '@/utils/request'
export function list (parameter = {}) {
  const pairs = Object.keys(parameter).filter(key => parameter[key] !== '').map(key => [key, parameter[key]])
  return request({ url: '/product/retail/list', method: 'get', params: Object.fromEntries(pairs) })
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


def test_preview_validator_still_flags_page_array_reads_without_guard():
    files = {
        "src/views/Product/RetailList.vue": """
<template><div>{{ rows.length }}</div></template>
<script>
export default {
  data () {
    return { rows: null }
  },
  computed: {
    names () { return this.rows.map(item => item.name) }
  }
}
</script>
""",
    }

    assert any("访问数组前缺少默认空数组兜底" in issue for issue in _validate_frontend_preview_code_files(files))


def test_preview_validator_rejects_standalone_demo_preview_files():
    files = {
        "src/views/SandboxPreview/GeneratedPage.vue": """
<template><div>独立演示页面</div></template>
<script>
export default { name: 'StandalonePreview' }
</script>
""",
        "package.json": '{"scripts":{"dev":"vite"}}',
    }

    issues = _validate_frontend_preview_code_files(files)

    assert any("独立 demo/preview 页面" in issue for issue in issues)
    assert any("独立应用入口文件" in issue for issue in issues)
    assert any("独立预览组件命名" in issue for issue in issues)


def test_preview_validator_rejects_new_page_for_existing_feature_change():
    files = {
        "src/views/product/retail/List.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: () => Promise.resolve({
        page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: []
      })
    }
  }
}
</script>
""",
        "src/api/product.js": """
export function list () {
  return Promise.resolve({ result: { page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: [] } })
}
""",
    }

    issues = _validate_frontend_preview_code_files(
        files,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/mall/goods/RetailGoodsList.vue"],
    )

    assert any("不是项目代码参考中已确认存在的页面" in issue for issue in issues)


def test_preview_validator_rejects_unrelated_existing_page_for_existing_feature_change():
    files = {
        "src/views/activityManage/ActivityManageList.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  name: 'ActivityManageList',
  data () {
    return {
      loadData: () => Promise.resolve({
        page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: []
      })
    }
  }
}
</script>
""",
        "src/api/product.js": """
export function list () {
  return Promise.resolve({ result: { page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: [] } })
}
""",
    }

    issues = _validate_frontend_preview_code_files(
        files,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/product/RetailGoodsList.vue"],
    )

    assert any("不是项目代码参考中已确认存在的页面" in issue for issue in issues)


def test_relevant_existing_page_paths_ignore_activity_for_retail_product_request():
    files = {
        "src/views/activityManage/ActivityManageList.vue": "活动管理列表，活动名称，活动状态，投放渠道",
        "src/views/product/RetailGoodsList.vue": "零售商品列表，商品名称，商品ID，商品状态，库存",
        "src/views/product/ProductPoolList.vue": "商品池列表，商品名称，商品ID，商品状态",
        "src/views/product/ProductCategory.vue": "商品分类管理，类目名称",
    }

    assert _frontend_relevant_existing_page_paths(
        files,
        "我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
    ) == ["src/views/product/RetailGoodsList.vue"]


def test_existing_feature_validator_rejects_rewritten_selected_list_page():
    original_page = """
<template>
  <a-card>
    <a-form>
      <a-form-item label="商品编号">
        <a-input v-model="queryParam.productCode" />
      </a-form-item>
    </a-form>
    <s-table ref="table" :columns="columns" :data="loadData">
      <span slot="action"></span>
    </s-table>
  </a-card>
</template>
<script>
import { ListMixin } from '@/mixins/ListMixin'
export default {
  name: 'SelfOperateCommodityList',
  mixins: [ListMixin],
  data () {
    return {
      queryParam: {},
      url: { list: '/api/product/glsw/product/selfOperatedList' },
      columns: []
    }
  }
}
</script>
"""
    generated_files = {
        "src/views/selfOperateCommodity/commodityList/List.vue": """
<template>
  <a-card>
    <a-form>
      <a-form-item label="商品ID"><a-input v-model="filters.productId" /></a-form-item>
    </a-form>
    <s-table ref="table" :columns="columns" :data="loadData" />
  </a-card>
</template>
<script>
import { getRetailCommodityList } from '@/api/commodityCenter'
export default {
  data () {
    return {
      filters: { productId: '' },
      columns: [],
      loadData: parameter => getRetailCommodityList(parameter).then(res => ({
        page: res.page || 1,
        count: res.count || 0,
        list: Array.isArray(res.list) ? res.list : []
      }))
    }
  }
}
</script>
""",
        "src/api/commodityCenter.js": "export function getRetailCommodityList () { return Promise.resolve({ list: [] }) }",
    }

    issues = _validate_frontend_preview_code_files(
        generated_files,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/selfOperateCommodity/commodityList/List.vue"],
        existing_frontend_files={"src/views/selfOperateCommodity/commodityList/List.vue": original_page},
    )

    assert any("新增的 API 文件" in issue for issue in issues)
    assert any("移除了它" in issue for issue in issues)
    assert any("queryParam.productCode" in issue for issue in issues)
    assert any("/api/product/glsw/product/selfOperatedList" in issue for issue in issues)


def test_existing_feature_validator_allows_minimal_label_change_on_selected_page():
    original_page = """
<template>
  <a-form>
    <a-form-item label="商品编号"><a-input placeholder="请输入商品编号" v-model="queryParam.productCode" /></a-form-item>
  </a-form>
  <s-table ref="table" :columns="columns" :data="loadData" />
</template>
<script>
import { ListMixin } from '@/mixins/ListMixin'
export default {
  mixins: [ListMixin],
  data () {
    return {
      queryParam: {},
      url: { list: '/api/product/glsw/product/selfOperatedList' },
      columns: []
    }
  }
}
</script>
"""
    generated_page = original_page.replace("商品编号", "商品ID")

    issues = _validate_frontend_preview_code_files(
        {"src/views/selfOperateCommodity/commodityList/List.vue": generated_page},
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/selfOperateCommodity/commodityList/List.vue"],
        existing_frontend_files={"src/views/selfOperateCommodity/commodityList/List.vue": original_page},
    )

    assert issues == []


def test_existing_feature_auto_fix_reverts_to_original_equivalent_filter():
    original_page = """
<template>
  <a-form>
    <a-form-item label="商品编号"><a-input placeholder="请输入商品编号" v-model="queryParam.productCode" /></a-form-item>
  </a-form>
  <s-table ref="table" :columns="columns" :data="loadData" />
</template>
<script>
import { ListMixin } from '@/mixins/ListMixin'
export default {
  mixins: [ListMixin],
  data () {
    return {
      queryParam: {},
      url: { list: '/api/product/glsw/product/selfOperatedList' },
      columns: []
    }
  }
}
</script>
"""
    generated_files = {
        "src/views/selfOperateCommodity/commodityList/List.vue": """
<template>
  <a-form><a-input v-model="filters.productId" /></a-form>
  <s-table :data="loadData" />
</template>
<script>
import { list } from '@/api/selfOperateCommodity'
export default {
  data () {
    return { filters: {}, loadData: () => list() }
  }
}
</script>
""",
        "src/api/selfOperateCommodity.js": "export function list () { return Promise.resolve({ list: [] }) }",
    }

    fixed, fixes = _auto_fix_existing_feature_from_original(
        generated_files,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/selfOperateCommodity/commodityList/List.vue"],
        existing_frontend_files={"src/views/selfOperateCommodity/commodityList/List.vue": original_page},
    )

    assert fixes
    assert list(fixed) == ["src/views/selfOperateCommodity/commodityList/List.vue"]
    assert "商品ID" in fixed["src/views/selfOperateCommodity/commodityList/List.vue"]
    assert "queryParam.productCode" in fixed["src/views/selfOperateCommodity/commodityList/List.vue"]
    assert "/api/product/glsw/product/selfOperatedList" in fixed["src/views/selfOperateCommodity/commodityList/List.vue"]
    assert _validate_frontend_preview_code_files(
        fixed,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/selfOperateCommodity/commodityList/List.vue"],
        existing_frontend_files={"src/views/selfOperateCommodity/commodityList/List.vue": original_page},
    ) == []


def test_preview_validator_rejects_data_return_using_runtime_result_variable():
    files = {
        "src/views/selfOperateCommodity/commodityList/List.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      page: result.page || 1,
      count: parameter.count || 0,
      list: []
    }
  },
  methods: { loadData () { return Promise.resolve({ page: 1, count: 0, list: [] }) } }
}
</script>
""",
    }

    issues = _validate_frontend_preview_code_files(files)

    assert any("data() 初始返回对象引用了" in issue for issue in issues)


def test_preview_validator_allows_vue_ref_event_expression():
    files = {
        "src/views/selfOperateCommodity/commodityList/List.vue": """
<template>
  <a-button @click="$refs.table.refresh(true)">查询</a-button>
  <s-table ref="table" :data="loadData" />
</template>
<script>
export default {
  data () {
    return {
      loadData: () => Promise.resolve({ page: 1, count: 0, list: [] })
    }
  }
}
</script>
""",
    }

    issues = _validate_frontend_preview_code_files(files)

    assert not any("模板事件 $refs 未实现" in issue for issue in issues)


def test_existing_page_candidates_include_confidence_and_reason():
    files = {
        "src/views/activityManage/ActivityManageList.vue": "活动管理列表，活动名称，活动状态，投放渠道",
        "src/views/product/RetailGoodsList.vue": "零售商品列表，商品名称，商品ID，商品状态，库存",
    }

    candidates = _frontend_existing_page_candidates(
        files,
        "我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
    )

    assert candidates == [
        {
            "path": "src/views/product/RetailGoodsList.vue",
            "confidence": 0.92,
            "matched_terms": ["goods", "product", "retail", "商品", "零售"],
            "reason": "命中业务词：goods, product, retail, 商品, 零售",
            "display_name": "零售商品列表",
            "menu_hint": "商品相关列表页",
            "route_hint": "",
            "developer_hint": "src/views/product/RetailGoodsList.vue",
        }
    ]


def test_existing_page_candidates_map_retail_goods_menu_to_commodity_list_source():
    files = {
        "src/views/commodityList/ProductList.vue": """
<template>
  <a-form>
    <a-form-item label="商品名称"><a-input v-model="queryParam.productName" /></a-form-item>
    <a-form-item label="商品ID"><a-input v-model="queryParam.productCode" /></a-form-item>
  </a-form>
  <s-table ref="table" :columns="columns" :data="loadData" />
</template>
""",
        "src/views/selfOperateCommodity/commodityList/List.vue": """
<template>
  <a-form>
    <a-form-item label="商品名称"><a-input v-model="queryParam.productName" /></a-form-item>
    <a-form-item label="商品编号"><a-input v-model="queryParam.productCode" /></a-form-item>
  </a-form>
  <s-table ref="table" :columns="columns" :data="loadData" />
</template>
<script>
export default { data () { return { url: { list: '/api/product/glsw/product/selfOperatedList' } } } }
</script>
""",
        "src/views/selfOperateCommodity/commodityList/Operate.vue": "商品编辑页，SKU设置，商品名称",
        "src/views/supplyChainMidPlatform/commodityManage/commodityList/List.vue": "供应链商品列表，商品ID，商品名称",
        "src/views/commodityCenter/commodityPool/CommodityPoolList.vue": "商品池列表，零售商品，商品ID，商品名称",
        "src/views/orderList/modules/detailContent/retail.vue": "零售订单详情，商品名称，商品ID",
    }

    candidates = _frontend_existing_page_candidates(
        files,
        "我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
    )

    assert candidates
    assert candidates[0]["path"] == "src/views/selfOperateCommodity/commodityList/List.vue"
    assert candidates[0]["display_name"] == "自营零售商品列表"
    assert "商城管理" in candidates[0]["menu_hint"]
    assert candidates[0]["route_hint"] == "/product/goods/list"
    assert "src/views/selfOperateCommodity/commodityList/Operate.vue" not in [
        candidate["path"] for candidate in candidates
    ]
    assert "src/views/commodityCenter/commodityPool/CommodityPoolList.vue" not in [
        candidate["path"] for candidate in candidates
    ]


def test_fallback_page_candidates_offer_uncertain_options_when_no_strong_match():
    files = {
        "src/views/activityManage/ActivityManageList.vue": "活动管理列表，活动名称，活动状态，投放渠道",
        "src/views/order/OrderList.vue": "订单列表，订单状态，支付状态",
        "src/views/product/ProductPoolList.vue": "商品池列表，商品名称，商品ID，商品状态",
    }

    candidates = _frontend_fallback_page_candidates(
        files,
        "我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
    )

    assert candidates == []


def test_fallback_page_candidates_can_offer_same_business_area_uncertain_options():
    files = {
        "src/views/product/RetailArchive.vue": "零售商品归档，商品名称，状态",
        "src/views/product/ProductPoolList.vue": "商品池列表，商品名称，商品ID，商品状态",
    }

    candidates = _frontend_fallback_page_candidates(
        files,
        "我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
    )

    assert candidates
    assert candidates[0]["path"] == "src/views/product/RetailArchive.vue"
    assert candidates[0]["uncertain"] is True
    assert candidates[0]["confidence"] <= 0.52


def test_preview_validator_allows_existing_page_for_existing_feature_change():
    files = {
        "src/views/mall/goods/RetailGoodsList.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: () => Promise.resolve({
        page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: []
      })
    }
  }
}
</script>
""",
        "src/api/product.js": """
export function list () {
  return Promise.resolve({ result: { page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: [] } })
}
""",
    }

    assert _validate_frontend_preview_code_files(
        files,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/mall/goods/RetailGoodsList.vue"],
    ) == []


def test_preview_validator_rejects_mock_list_for_existing_feature_change():
    files = {
        "src/views/product/RetailGoodsList.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: () => Promise.resolve({
        page: 1, pageNo: 1, pageSize: 10, count: 0, totalCount: 0, list: []
      })
    }
  }
}
</script>
""",
        "src/api/product.js": """
const mockProductList = [{ productId: '10001', productName: '旧商品' }]
export function list () {
  return new Promise(resolve => resolve({
    result: { page: 1, pageNo: 1, pageSize: 10, count: 1, totalCount: 1, list: mockProductList }
  }))
}
""",
    }

    issues = _validate_frontend_preview_code_files(
        files,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/product/RetailGoodsList.vue"],
    )

    assert any("生成了 mock 列表数据" in issue for issue in issues)
    assert any("模拟接口 Promise" in issue for issue in issues)


def test_preview_validator_allows_existing_api_param_patch_without_mock():
    files = {
        "src/views/product/RetailGoodsList.vue": """
<template><s-table :data="loadData" /></template>
<script>
export default {
  data () {
    return {
      loadData: parameter => list({ ...parameter, productId: this.queryParam.productId }).then(res => ({
        page: res.result.page,
        pageNo: res.result.pageNo,
        pageSize: res.result.pageSize,
        count: res.result.count,
        totalCount: res.result.totalCount,
        list: Array.isArray(res.result.list) ? res.result.list : []
      }))
    }
  }
}
</script>
""",
        "src/api/product.js": """
import request from '@/utils/request'
export function list (parameter) {
  return request({ url: '/product/retail/list', method: 'get', params: { ...parameter, productId: parameter.productId } })
}
""",
    }

    assert _validate_frontend_preview_code_files(
        files,
        user_request="我想给商城管理平台现有的零售商品列表增加一个商品ID的筛选项",
        existing_frontend_paths=["src/views/product/RetailGoodsList.vue"],
    ) == []


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
