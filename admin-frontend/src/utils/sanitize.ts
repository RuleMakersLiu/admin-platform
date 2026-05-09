/**
 * HTML 安全过滤工具
 * 用于清理和过滤潜在的恶意 HTML 内容
 */

import DOMPurify from 'dompurify';

// 危险标签列表 - 这些标签将被完全移除
const DANGEROUS_TAGS = [
  'script',
  'iframe',
  'frame',
  'frameset',
  'object',
  'embed',
  'applet',
  'meta',
  'link',
  'base',
  'form',
  'input',
  'button',
  'select',
  'textarea',
  'style',
];

// 危险属性列表 - 这些属性将被移除
const DANGEROUS_ATTRS = [
  'onabort',
  'onblur',
  'onchange',
  'onclick',
  'ondblclick',
  'onerror',
  'onfocus',
  'onkeydown',
  'onkeypress',
  'onkeyup',
  'onload',
  'onmousedown',
  'onmousemove',
  'onmouseout',
  'onmouseover',
  'onmouseup',
  'onreset',
  'onresize',
  'onscroll',
  'onselect',
  'onsubmit',
  'onunload',
  'onunload',
  'oncontextmenu',
  'ondrag',
  'ondragend',
  'ondragenter',
  'ondragleave',
  'ondragover',
  'ondragstart',
  'ondrop',
  'onhashchange',
  'onmessage',
  'onoffline',
  'ononline',
  'onpopstate',
  'onstorage',
  'onwheel',
  'formaction',
  'xlink:href',
];

// DOMPurify 配置
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

  // 允许的 URI 协议
  ALLOWED_URI_REGEXP: /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,

  // 禁止的标签
  FORBID_TAGS: DANGEROUS_TAGS,

  // 禁止的属性
  FORBID_ATTR: DANGEROUS_ATTRS,

  // 保持 HTML 实体
  KEEP_CONTENT: true,

  // 允许 data 属性
  ADD_ATTR: ['target'],

  // 强制添加 rel="noopener noreferrer" 到链接
  ADD_TAGS: [],
};

/**
 * 清理 HTML 内容，移除危险的标签和属性
 * @param html 原始 HTML 内容
 * @param options 可选的额外配置
 * @returns 清理后的安全 HTML
 */
export function sanitizeHtml(html: string, options?: Record<string, unknown>): string {
  if (!html || typeof html !== 'string') {
    return '';
  }

  const config = options ? { ...PURIFY_CONFIG, ...options } : PURIFY_CONFIG;

  // 使用 RETURN_TRUSTED_TYPE: false 确保返回 string 类型
  const finalConfig = { ...config, RETURN_TRUSTED_TYPE: false };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = DOMPurify.sanitize(html, finalConfig as any);
  return String(result);
}

/**
 * 清理内联样式
 * 移除可能包含 expression() 或 url(javascript:) 等危险内容
 * @param style 内联样式字符串
 * @returns 清理后的样式
 */
export function sanitizeStyle(style: string): string {
  if (!style || typeof style !== 'string') {
    return '';
  }

  // 移除危险的模式
  const dangerousPatterns = [
    /expression\s*\(/gi,
    /javascript\s*:/gi,
    /behavior\s*:/gi,
    /binding\s*:/gi,
    /-moz-binding\s*:/gi,
    /url\s*\(\s*['"]?\s*javascript:/gi,
  ];

  let sanitized = style;
  for (const pattern of dangerousPatterns) {
    sanitized = sanitized.replace(pattern, '');
  }

  return sanitized;
}

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

  // UI 预览沙箱：允许 <style> 和 style 属性（iframe 沙箱隔离，安全）
  const sandboxConfig = {
    ...PURIFY_CONFIG,
    FORBID_TAGS: DANGEROUS_TAGS.filter(t => t !== 'style'),
    ALLOWED_ATTR: [...PURIFY_CONFIG.ALLOWED_ATTR, 'style'],
  };
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
/**
 * 为 UI 预览准备 HTML 内容
 * LLM 输出的已是完整 HTML 文档，在 sandbox iframe 中渲染，浏览器沙箱已禁止 JS 执行
 * 只做轻量安全过滤：移除 script 标签和事件处理器
 * @param html 完整的 HTML 文档字符串
 * @returns 安全的完整 HTML 文档
 */
export function prepareUIPreviewHtml(html: string): string {
  if (!html || typeof html !== 'string') return '';

  // 轻量过滤：只移除 <script> 和事件属性，其余保留
  let safe = html;
  // 移除 <script>...</script>
  safe = safe.replace(/<script[\s\S]*?<\/script\s*>/gi, '');
  // 移除 on* 事件属性
  safe = safe.replace(/\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)/gi, '');
  // 移除 javascript: URL
  safe = safe.replace(/href\s*=\s*(?:"javascript:[^"]*"|'javascript:[^']*')/gi, 'href="#"');

  return safe;
}

export default {
  sanitizeHtml,
  sanitizeStyle,
  prepareSandboxHtml,
  prepareUIPreviewHtml,
  detectContentType,
  extractHtmlBlocks,
};
