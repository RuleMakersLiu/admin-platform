import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

// 科技风暗色主题配置
const techTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    // 主色调
    colorPrimary: '#00d4ff',
    colorInfo: '#00d4ff',
    colorSuccess: '#00ff88',
    colorWarning: '#ffaa00',
    colorError: '#ff2a6d',

    // 背景色
    colorBgContainer: 'rgba(15, 15, 25, 0.9)',
    colorBgElevated: 'rgba(20, 20, 30, 0.95)',
    colorBgLayout: '#0a0a0f',
    colorBgSpotlight: 'rgba(0, 212, 255, 0.1)',

    // 边框
    colorBorder: 'rgba(0, 212, 255, 0.15)',
    colorBorderSecondary: 'rgba(255, 255, 255, 0.06)',

    // 文字颜色
    colorText: '#e0e0e0',
    colorTextSecondary: '#888',
    colorTextTertiary: '#555',
    colorTextQuaternary: '#333',

    // 圆角
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,

    // 阴影
    boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
    boxShadowSecondary: '0 4px 12px rgba(0, 0, 0, 0.3)',

    // 字体
    fontFamily: "'Orbitron', 'Rajdhani', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  },
  components: {
    Menu: {
      darkItemBg: 'transparent',
      darkItemHoverBg: 'rgba(0, 212, 255, 0.08)',
      darkItemSelectedBg: 'rgba(0, 212, 255, 0.15)',
      darkItemColor: '#888',
      darkItemHoverColor: '#00d4ff',
      darkItemSelectedColor: '#00d4ff',
    },
    Table: {
      headerBg: 'rgba(0, 212, 255, 0.08)',
      headerColor: '#00d4ff',
      rowHoverBg: 'rgba(0, 212, 255, 0.05)',
      borderColor: 'rgba(0, 212, 255, 0.1)',
    },
    Card: {
      colorBgContainer: 'rgba(15, 15, 25, 0.9)',
      colorBorderSecondary: 'rgba(0, 212, 255, 0.15)',
    },
    Input: {
      colorBgContainer: 'rgba(20, 20, 30, 0.8)',
      colorBorder: 'rgba(0, 212, 255, 0.2)',
      hoverBorderColor: 'rgba(0, 212, 255, 0.4)',
      activeBorderColor: '#00d4ff',
      colorText: '#e0e0e0',
      colorTextPlaceholder: '#555',
    },
    Button: {
      primaryShadow: '0 4px 15px rgba(0, 212, 255, 0.4)',
    },
    Modal: {
      contentBg: 'rgba(15, 15, 25, 0.95)',
      headerBg: 'transparent',
      titleColor: '#00d4ff',
    },
    Dropdown: {
      colorBgElevated: 'rgba(15, 15, 25, 0.95)',
    },
    Select: {
      colorBgContainer: 'rgba(20, 20, 30, 0.8)',
      colorBorder: 'rgba(0, 212, 255, 0.2)',
      optionSelectedBg: 'rgba(0, 212, 255, 0.15)',
    },
    Message: {
      contentBg: 'rgba(15, 15, 25, 0.95)',
    },
    Notification: {
      colorBgElevated: 'rgba(15, 15, 25, 0.95)',
    },
  },
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={techTheme}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
