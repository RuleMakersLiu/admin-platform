/**
 * HTML 安全过滤工具
 *
 * 基于 DOMPurify 的白名单（ALLOWED_TAGS / ALLOWED_ATTR / ALLOWED_URI_REGEXP）
 * 进行净化。白名单是唯一的真实控制：未列入的标签/属性一律移除，因此不再
 * 维护手写的危险标签/属性黑名单（曾经的 DANGEROUS_TAGS/ATTRS 在白名单开启时
 * 本就是冗余的）。
 *
 * XSS 攻击向量回归见 tests/sanitize.test.ts（script / on* / javascript: /
 * data: / iframe / svg / meta refresh / form-action / base / link 等均被拦截）。
 */

import DOMPurify from 'dompurify';

// DOMPurify 配置（白名单模式）
const PURIFY_CONFIG = {
  // 允许的标签
  ALLOWED_TAGS: [
    // 文本结构
    'p',
    'br',
    'span',
    'div',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'blockquote',
    'pre',
    'code',
    'em',
    'strong',
    'i',
    'b',
    'u',
    's',
    'del',
    'ins',
    'mark',
    'small',
    'sub',
    'sup',
    // 列表
    'ul',
    'ol',
    'li',
    'dl',
    'dt',
    'dd',
    // 表格
    'table',
    'thead',
    'tbody',
    'tfoot',
    'tr',
    'th',
    'td',
    'caption',
    'colgroup',
    'col',
    // 链接和媒体
    'a',
    'img',
    'figure',
    'figcaption',
    'picture',
    'source',
    'audio',
    'video',
    'track',
    // 语义化标签
    'article',
    'section',
    'nav',
    'aside',
    'header',
    'footer',
    'main',
    'address',
    'details',
    'summary',
    'dialog',
    // 其他
    'hr',
    'abbr',
    'cite',
    'dfn',
    'kbd',
    'samp',
    'var',
    'time',
    'wbr',
    'ruby',
    'rt',
    'rp',
    'bdi',
    'bdo',
  ],

  // 允许的属性
  ALLOWED_ATTR: [
    // 通用属性
    'id',
    'class',
    'title',
    'lang',
    'dir',
    'hidden',
    'tabindex',
    'role',
    'aria-*',
    'data-*',
    // 链接属性
    'href',
    'target',
    'rel',
    'download',
    'hreflang',
    'type',
    // 图片属性
    'src',
    'alt',
    'width',
    'height',
    'loading',
    'decoding',
    'srcset',
    'sizes',
    // 媒体属性
    'controls',
    'autoplay',
    'loop',
    'muted',
    'preload',
    'poster',
    'kind',
    'srclang',
    'label',
    'default',
    // 表格属性
    'colspan',
    'rowspan',
    'headers',
    'scope',
    'span',
    // 其他
    'datetime',
    'cite',
    'open',
    'reversed',
    'start',
    'value',
    'name',
  ],

  // 允许的 URI 协议（拒绝 javascript: / vbscript: / data: 等）
  ALLOWED_URI_REGEXP: /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,

  // 移除危险标签时保留其文本内容
  KEEP_CONTENT: true,

  ADD_ATTR: ['target'],
  ADD_TAGS: [],
};

/**
 * 为 iframe 沙箱准备 HTML 内容
 * 添加基础样式和必要的包装
 * @param html HTML 内容
 * @param options 配置选项
 * @returns 完整的 HTML 文档字符串
 */
export function prepareSandboxHtml(
  html: string,
  options: {
    title?: string;
    baseStyle?: string;
    additionalStyles?: string;
    darkMode?: boolean;
  } = {}
): string {
  const {
    title = 'Canvas Preview',
    baseStyle = '',
    additionalStyles = '',
    darkMode = false,
  } = options;

  // UI 预览沙箱：在白名单基础上额外放开内联 style 属性（iframe 沙箱隔离，安全）。
  // 注意：<style> 标签不在白名单中，会被移除；样式应通过内联 style 或下方默认样式提供。
  const sandboxConfig = {
    ...PURIFY_CONFIG,
    ALLOWED_ATTR: [...PURIFY_CONFIG.ALLOWED_ATTR, 'style'],
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sanitizedContent = DOMPurify.sanitize(html, sandboxConfig as any);

  // 默认基础样式
  const defaultStyles = `
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    html, body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      color: ${darkMode ? '#e0e0e0' : '#333333'};
      background-color: ${darkMode ? '#141414' : '#ffffff'};
      padding: 24px;
      min-height: 100%;
    }

    a {
      color: ${darkMode ? '#40a9ff' : '#1890ff'};
      text-decoration: none;
    }

    a:hover {
      text-decoration: underline;
    }

    img {
      max-width: 100%;
      height: auto;
    }

    pre, code {
      font-family: 'SF Mono', 'Fira Code', 'Fira Mono', Consolas, Monaco, monospace;
    }

    pre {
      background: ${darkMode ? '#2d2d2d' : '#f6f8fa'};
      padding: 16px;
      border-radius: 6px;
      overflow-x: auto;
    }

    code {
      background: ${darkMode ? '#2d2d2d' : '#f6f8fa'};
      padding: 2px 6px;
      border-radius: 3px;
    }

    pre code {
      background: transparent;
      padding: 0;
    }

    table {
      border-collapse: collapse;
      width: 100%;
      margin: 16px 0;
    }

    th, td {
      border: 1px solid ${darkMode ? '#434343' : '#e8e8e8'};
      padding: 8px 12px;
      text-align: left;
    }

    th {
      background: ${darkMode ? '#2d2d2d' : '#fafafa'};
      font-weight: 600;
    }

    blockquote {
      border-left: 4px solid ${darkMode ? '#40a9ff' : '#1890ff'};
      padding-left: 16px;
      margin: 16px 0;
      color: ${darkMode ? 'rgba(255,255,255,0.65)' : '#666666'};
    }

    h1, h2, h3, h4, h5, h6 {
      margin-top: 24px;
      margin-bottom: 16px;
      font-weight: 600;
      line-height: 1.25;
    }

    h1 { font-size: 2em; }
    h2 { font-size: 1.5em; }
    h3 { font-size: 1.25em; }
    h4 { font-size: 1em; }
    h5 { font-size: 0.875em; }
    h6 { font-size: 0.85em; color: ${darkMode ? 'rgba(255,255,255,0.65)' : '#666'}; }

    ul, ol {
      padding-left: 2em;
      margin: 16px 0;
    }

    li {
      margin: 4px 0;
    }

    /* Ant Design 兼容样式 */
    .ant-btn, button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 4px 15px;
      border-radius: 6px;
      border: 1px solid ${darkMode ? '#434343' : '#d9d9d9'};
      background: ${darkMode ? '#1f1f1f' : '#fff'};
      color: ${darkMode ? '#e0e0e0' : '#333'};
      cursor: pointer;
      font-size: 14px;
      line-height: 1.5714;
      transition: all 0.2s;
    }
    .ant-btn:hover, button:hover {
      color: ${darkMode ? '#40a9ff' : '#4096ff'};
      border-color: ${darkMode ? '#40a9ff' : '#4096ff'};
    }
    .ant-btn-primary, .ant-btn-primary:hover {
      background: #1677ff;
      border-color: #1677ff;
      color: #fff;
    }
    .ant-card {
      background: ${darkMode ? '#1f1f1f' : '#fff'};
      border-radius: 8px;
      border: 1px solid ${darkMode ? '#303030' : '#f0f0f0'};
      padding: 16px;
      margin-bottom: 12px;
    }
    .ant-input {
      padding: 4px 11px;
      border-radius: 6px;
      border: 1px solid ${darkMode ? '#434343' : '#d9d9d9'};
      background: ${darkMode ? '#141414' : '#fff'};
      color: ${darkMode ? '#e0e0e0' : '#333'};
      width: 100%;
      font-size: 14px;
    }
    .ant-table {
      width: 100%;
      border-collapse: collapse;
    }
    .ant-tag {
      display: inline-block;
      padding: 0 7px;
      border-radius: 4px;
      font-size: 12px;
      line-height: 20px;
    }
    .ant-layout, .ant-layout-content {
      min-height: auto;
    }
    .ant-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }
    .ant-col {
      flex: 1;
      min-width: 0;
    }
    .ant-statistic {
      text-align: center;
    }
    .ant-statistic-title {
      font-size: 14px;
      color: ${darkMode ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)'};
      margin-bottom: 4px;
    }
    .ant-statistic-content {
      font-size: 24px;
      font-weight: 600;
      color: ${darkMode ? '#e0e0e0' : '#333'};
    }
    .ant-flex {
      display: flex;
    }
  `;

  return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' https:; img-src 'self' data: https:; media-src 'self' https:;">
  <title>${title}</title>
  <style>
    ${defaultStyles}
    ${baseStyle}
    ${additionalStyles}
  </style>
</head>
<body>
  ${sanitizedContent}
</body>
</html>`;
}

/**
 * 检测内容类型
 * @param content 内容字符串
 * @returns 内容类型
 */
export function detectContentType(content: string): 'html' | 'markdown' | 'code' | 'text' {
  if (!content || typeof content !== 'string') {
    return 'text';
  }

  const trimmed = content.trim();

  // 检测 HTML
  if (
    trimmed.startsWith('<!DOCTYPE') ||
    trimmed.startsWith('<html') ||
    /<[a-z][\s\S]*>/i.test(trimmed)
  ) {
    // 排除简单的行内标签如 <code>
    const tagCount = (trimmed.match(/<[a-z][^>]*>/gi) || []).length;
    const blockTags = ['<div', '<p>', '<h1', '<h2', '<h3', '<section', '<article', '<table', '<ul', '<ol', '<form'];
    const hasBlockTag = blockTags.some(tag => trimmed.toLowerCase().includes(tag));

    if (tagCount > 3 || hasBlockTag) {
      return 'html';
    }
  }

  // 检测代码块
  if (trimmed.startsWith('```') && trimmed.endsWith('```')) {
    return 'code';
  }

  // 检测 Markdown 特征
  const mdPatterns = [
    /^#{1,6}\s+/m,           // 标题
    /\*\*.*?\*\*/,           // 粗体
    /\*.*?\*/,               // 斜体
    /^\s*[-*+]\s+/m,         // 无序列表
    /^\s*\d+\.\s+/m,         // 有序列表
    /\[.*?\]\(.*?\)/,        // 链接
    /`[^`]+`/,               // 行内代码
    /^>\s+/m,                // 引用
    /\|.+\|/,                // 表格
  ];

  if (mdPatterns.some((pattern) => pattern.test(trimmed))) {
    return 'markdown';
  }

  return 'text';
}

/**
 * 从消息内容中提取 HTML 代码块
 * @param content 消息内容
 * @returns 提取的 HTML 代码块列表
 */
export function extractHtmlBlocks(content: string): Array<{ language: string; code: string }> {
  const blocks: Array<{ language: string; code: string }> = [];

  // 匹配代码块模式
  const codeBlockRegex = /```(\w+)?[ \t]*\n?([\s\S]*?)```/g;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    const language = match[1] || 'text';
    const code = match[2].trim();

    // 只提取 HTML 或相关代码
    if (
      language === 'html' ||
      language === 'htm' ||
      language === 'xml' ||
      language === 'svg' ||
      (language === '' && /<[a-z][\s\S]*>/i.test(code))
    ) {
      blocks.push({ language, code });
    }
  }

  return blocks;
}

export default {
  prepareSandboxHtml,
  detectContentType,
  extractHtmlBlocks,
};
