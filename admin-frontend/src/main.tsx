import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

const brightTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#315cf6',
    colorInfo: '#315cf6',
    colorSuccess: '#16a34a',
    colorWarning: '#f59e0b',
    colorError: '#dc2626',

    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBgLayout: '#f6f8fc',
    colorBgSpotlight: 'rgba(17, 24, 39, 0.9)',

    colorBorder: '#e5eaf3',
    colorBorderSecondary: '#eef2f8',

    colorText: '#111827',
    colorTextSecondary: '#5b6475',
    colorTextTertiary: '#7b8496',
    colorTextQuaternary: '#a6afbf',

    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,

    boxShadow: '0 14px 36px rgba(15, 23, 42, 0.08)',
    boxShadowSecondary: '0 8px 24px rgba(15, 23, 42, 0.06)',

    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  },
  components: {
    Menu: {
      itemBg: 'transparent',
      itemHoverBg: '#f3f6ff',
      itemSelectedBg: '#edf3ff',
      itemColor: '#445066',
      itemHoverColor: '#315cf6',
      itemSelectedColor: '#315cf6',
    },
    Table: {
      headerBg: '#f8fafd',
      headerColor: '#334155',
      rowHoverBg: '#f5f8ff',
      borderColor: '#edf1f7',
    },
    Card: {
      colorBgContainer: '#ffffff',
      colorBorderSecondary: '#edf1f7',
    },
    Input: {
      colorBgContainer: '#ffffff',
      colorBorder: '#dbe3ef',
      hoverBorderColor: '#8aa4ff',
      activeBorderColor: '#315cf6',
      colorText: '#111827',
      colorTextPlaceholder: '#9aa4b5',
    },
    Button: {
      primaryShadow: '0 8px 18px rgba(49, 92, 246, 0.22)',
    },
    Modal: {
      contentBg: '#ffffff',
      headerBg: '#ffffff',
      titleColor: '#111827',
    },
    Dropdown: {
      colorBgElevated: '#ffffff',
    },
    Select: {
      colorBgContainer: '#ffffff',
      colorBorder: '#dbe3ef',
      optionSelectedBg: '#edf3ff',
    },
    Message: {
      contentBg: '#ffffff',
    },
    Notification: {
      colorBgElevated: '#ffffff',
    },
  },
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={brightTheme}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
