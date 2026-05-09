import React, { memo, useState, useCallback, useEffect, useRef, useMemo } from 'react';
import {
  Tabs,
  Button,
  Space,
  Tooltip,
  Empty,
  Spin,
  message,
  Typography,
  Select,
  Drawer,
} from 'antd';
import {
  CodeOutlined,
  EyeOutlined,
  CopyOutlined,
  CheckOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  MobileOutlined,
  TabletOutlined,
  DesktopOutlined,
  ReloadOutlined,
  DownloadOutlined,
  ExpandOutlined,
} from '@ant-design/icons';
import MarkdownRenderer from '@/utils/markdown';
import { prepareSandboxHtml, extractHtmlBlocks, detectContentType } from '@/utils/sanitize';
import './CanvasPanel.css';

const { Text } = Typography;

// 视图模式
export type ViewMode = 'preview' | 'code' | 'split';

// 设备预览尺寸
export type DeviceSize = 'mobile' | 'tablet' | 'desktop' | 'responsive';

// 设备尺寸映射
const DEVICE_SIZES: Record<DeviceSize, { width: string | number; label: string }> = {
  mobile: { width: 375, label: 'Mobile (375px)' },
  tablet: { width: 768, label: 'Tablet (768px)' },
  desktop: { width: 1024, label: 'Desktop (1024px)' },
  responsive: { width: '100%', label: 'Responsive' },
};

// Canvas 内容类型
export type CanvasContentType = 'html' | 'markdown' | 'code';

// CanvasPanel Props
export interface CanvasPanelProps {
  // 内容
  content: string;
  // 内容类型
  contentType?: CanvasContentType;
  // 初始视图模式
  defaultViewMode?: ViewMode;
  // 初始设备尺寸
  defaultDeviceSize?: DeviceSize;
  // 是否显示工具栏
  showToolbar?: boolean;
  // 是否显示设备切换
  showDeviceSwitcher?: boolean;
  // 是否全屏模式
  fullscreen?: boolean;
  // 全屏切换回调
  onFullscreenChange?: (fullscreen: boolean) => void;
  // 暗色模式
  darkMode?: boolean;
  // 标题
  title?: string;
  // 类名
  className?: string;
  // 样式
  style?: React.CSSProperties;
}

// 代码查看器组件
const CodeViewer: React.FC<{
  code: string;
  language?: string;
  darkMode?: boolean;
}> = memo(({ code, language = 'html', darkMode }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      message.success('代码已复制');
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      message.error('复制失败');
    }
  }, [code]);

  return (
    <div className={`code-viewer ${darkMode ? 'dark' : ''}`}>
      <div className="code-viewer-header">
        <Text type="secondary">{language.toUpperCase()}</Text>
        <Tooltip title={copied ? '已复制' : '复制代码'}>
          <Button
            type="text"
            size="small"
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            onClick={handleCopy}
          />
        </Tooltip>
      </div>
      <pre className="code-viewer-content">
        <code>{code}</code>
      </pre>
    </div>
  );
});

CodeViewer.displayName = 'CodeViewer';

// HTML 预览组件（使用沙箱 iframe）
const HtmlPreview: React.FC<{
  html: string;
  deviceSize: DeviceSize;
  darkMode?: boolean;
}> = memo(({ html, deviceSize, darkMode }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 准备沙箱 HTML
  const sandboxHtml = useMemo(() => {
    try {
      return prepareSandboxHtml(html, {
        title: 'Preview',
        darkMode,
      });
    } catch (err) {
      setError((err as Error).message);
      return '';
    }
  }, [html, darkMode]);

  // 处理 iframe 加载
  useEffect(() => {
    if (iframeRef.current && sandboxHtml) {
      setIsLoading(true);
      setError(null);

      const iframe = iframeRef.current;
      const doc = iframe.contentDocument || iframe.contentWindow?.document;

      if (doc) {
        try {
          doc.open();
          doc.write(sandboxHtml);
          doc.close();
          setIsLoading(false);
        } catch (err) {
          setError((err as Error).message);
          setIsLoading(false);
        }
      }
    }
  }, [sandboxHtml]);

  // 处理 iframe 错误
  const handleError = useCallback(() => {
    setError('加载预览失败');
    setIsLoading(false);
  }, []);

  // 设备尺寸
  const deviceWidth = DEVICE_SIZES[deviceSize].width;

  if (error) {
    return (
      <div className="html-preview-error">
        <Empty description={error} />
      </div>
    );
  }

  return (
    <div className="html-preview-wrapper">
      {isLoading && (
        <div className="html-preview-loading">
          <Spin tip="加载预览..." />
        </div>
      )}
      <div className="html-preview-container" style={{ maxWidth: deviceWidth }}>
        <iframe
          ref={iframeRef}
          className="html-preview-iframe"
          title="HTML Preview"
          sandbox="allow-same-origin allow-popups allow-forms"
          onError={handleError}
        />
      </div>
    </div>
  );
});

HtmlPreview.displayName = 'HtmlPreview';

// CanvasPanel 主组件
const CanvasPanel: React.FC<CanvasPanelProps> = memo(
  ({
    content,
    contentType: propContentType,
    defaultViewMode = 'preview',
    defaultDeviceSize = 'responsive',
    showToolbar = true,
    showDeviceSwitcher = true,
    fullscreen = false,
    onFullscreenChange,
    darkMode = false,
    title = 'Canvas',
    className,
    style,
  }) => {
    // 状态
    const [viewMode, setViewMode] = useState<ViewMode>(defaultViewMode);
    const [deviceSize, setDeviceSize] = useState<DeviceSize>(defaultDeviceSize);
    const [isFullscreen, setIsFullscreen] = useState(fullscreen);
    const containerRef = useRef<HTMLDivElement>(null);

    // 自动检测内容类型
    const detectedContentType = useMemo(() => {
      if (propContentType) return propContentType;

      const detected = detectContentType(content);
      if (detected === 'html') return 'html';
      if (detected === 'markdown') return 'markdown';
      if (detected === 'code') return 'code';
      return 'markdown'; // 默认使用 markdown
    }, [content, propContentType]);

    // 提取 HTML 代码块
    const htmlBlocks = useMemo(() => {
      if (detectedContentType === 'html') {
        // 如果内容本身就是 HTML
        if (content.trim().startsWith('<')) {
          return [{ language: 'html', code: content }];
        }
        // 否则尝试从 Markdown 中提取
        return extractHtmlBlocks(content);
      }
      return [];
    }, [content, detectedContentType]);

    // 当前要预览的 HTML 内容
    const previewHtml = useMemo(() => {
      if (htmlBlocks.length > 0) {
        return htmlBlocks[0].code;
      }
      return content;
    }, [htmlBlocks, content]);

    // 切换全屏
    const toggleFullscreen = useCallback(() => {
      const newFullscreen = !isFullscreen;
      setIsFullscreen(newFullscreen);
      onFullscreenChange?.(newFullscreen);
    }, [isFullscreen, onFullscreenChange]);

    // 刷新预览
    const handleRefresh = useCallback(() => {
      // 强制重新渲染 iframe
      if (containerRef.current) {
        const iframe = containerRef.current.querySelector<HTMLIFrameElement>('.html-preview-iframe');
        if (iframe) {
          const src = iframe.src;
          iframe.src = '';
          setTimeout(() => {
            iframe.src = src || 'about:blank';
          }, 100);
        }
      }
    }, []);

    // 下载 HTML
    const handleDownload = useCallback(() => {
      const blob = new Blob([previewHtml], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'canvas-preview.html';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('HTML 已下载');
    }, [previewHtml]);

    // 复制 HTML
    const handleCopyHtml = useCallback(async () => {
      try {
        await navigator.clipboard.writeText(previewHtml);
        message.success('HTML 已复制到剪贴板');
      } catch (err) {
        message.error('复制失败');
      }
    }, [previewHtml]);

    // 设备选项
    const deviceOptions = Object.entries(DEVICE_SIZES).map(([key, value]) => ({
      value: key,
      label: value.label,
    }));

    // 视图选项
    const viewTabs = [
      {
        key: 'preview',
        label: (
          <span>
            <EyeOutlined />
            预览
          </span>
        ),
      },
      {
        key: 'code',
        label: (
          <span>
            <CodeOutlined />
            代码
          </span>
        ),
      },
      {
        key: 'split',
        label: (
          <span>
            <ExpandOutlined />
            分屏
          </span>
        ),
      },
    ];

    // 渲染内容
    const renderContent = () => {
      if (!content) {
        return (
          <div className="canvas-empty">
            <Empty description="暂无内容" />
          </div>
        );
      }

      switch (detectedContentType) {
        case 'html':
          return renderHtmlContent();
        case 'markdown':
          return renderMarkdownContent();
        case 'code':
          return renderCodeContent();
        default:
          return renderMarkdownContent();
      }
    };

    // 渲染 HTML 内容
    const renderHtmlContent = () => {
      if (viewMode === 'preview') {
        return <HtmlPreview html={previewHtml} deviceSize={deviceSize} darkMode={darkMode} />;
      }

      if (viewMode === 'code') {
        return <CodeViewer code={previewHtml} language="html" darkMode={darkMode} />;
      }

      // 分屏模式
      return (
        <div className="canvas-split-view">
          <div className="canvas-split-preview">
            <HtmlPreview html={previewHtml} deviceSize={deviceSize} darkMode={darkMode} />
          </div>
          <div className="canvas-split-code">
            <CodeViewer code={previewHtml} language="html" darkMode={darkMode} />
          </div>
        </div>
      );
    };

    // 渲染 Markdown 内容
    const renderMarkdownContent = () => {
      // 检查是否包含可预览的 HTML 代码块
      if (htmlBlocks.length > 0) {
        return renderHtmlContent();
      }

      return (
        <div className={`canvas-markdown ${darkMode ? 'dark' : ''}`}>
          <MarkdownRenderer content={content} />
        </div>
      );
    };

    // 渲染代码内容
    const renderCodeContent = () => {
      return (
        <div className={`canvas-markdown ${darkMode ? 'dark' : ''}`}>
          <MarkdownRenderer content={'```\n' + content + '\n```'} />
        </div>
      );
    };

    // 工具栏组件
    const toolbar = showToolbar && (
      <div className="canvas-toolbar">
        <div className="toolbar-left">
          <Text strong className="canvas-title">
            {title}
          </Text>

          {/* 视图切换 */}
          <Tabs
            activeKey={viewMode}
            onChange={(key) => setViewMode(key as ViewMode)}
            items={viewTabs}
            size="small"
            className="view-tabs"
          />
        </div>

        <div className="toolbar-right">
          <Space>
            {/* 设备切换 */}
            {showDeviceSwitcher && detectedContentType === 'html' && viewMode !== 'code' && (
              <Select
                value={deviceSize}
                onChange={setDeviceSize}
                options={deviceOptions}
                style={{ width: 150 }}
                size="small"
                suffixIcon={
                  deviceSize === 'mobile' ? (
                    <MobileOutlined />
                  ) : deviceSize === 'tablet' ? (
                    <TabletOutlined />
                  ) : deviceSize === 'desktop' ? (
                    <DesktopOutlined />
                  ) : (
                    <DesktopOutlined />
                  )
                }
              />
            )}

            {/* 刷新 */}
            <Tooltip title="刷新预览">
              <Button type="text" size="small" icon={<ReloadOutlined />} onClick={handleRefresh} />
            </Tooltip>

            {/* 复制 */}
            <Tooltip title="复制代码">
              <Button type="text" size="small" icon={<CopyOutlined />} onClick={handleCopyHtml} />
            </Tooltip>

            {/* 下载 */}
            <Tooltip title="下载 HTML">
              <Button
                type="text"
                size="small"
                icon={<DownloadOutlined />}
                onClick={handleDownload}
              />
            </Tooltip>

            {/* 全屏切换 */}
            <Tooltip title={isFullscreen ? '退出全屏' : '全屏'}>
              <Button
                type="text"
                size="small"
                icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                onClick={toggleFullscreen}
              />
            </Tooltip>
          </Space>
        </div>
      </div>
    );

    // 全屏抽屉
    if (isFullscreen) {
      return (
        <Drawer
          open={true}
          onClose={toggleFullscreen}
          title={toolbar}
          width="100vw"
          className={`canvas-drawer ${darkMode ? 'dark' : ''}`}
          styles={{
            body: { padding: 0, height: 'calc(100vh - 55px)' },
          }}
          closable={false}
        >
          <div className="canvas-content" ref={containerRef}>
            {renderContent()}
          </div>
        </Drawer>
      );
    }

    return (
      <div
        className={`canvas-panel ${darkMode ? 'dark' : ''} ${className || ''}`}
        style={style}
        ref={containerRef}
      >
        {toolbar}
        <div className="canvas-content">{renderContent()}</div>
      </div>
    );
  }
);

CanvasPanel.displayName = 'CanvasPanel';

export default CanvasPanel;
