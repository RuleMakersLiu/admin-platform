import React, { memo, useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { message, Tooltip, Button, Space } from 'antd';
import { CopyOutlined, PlayCircleOutlined, CheckOutlined } from '@ant-design/icons';
import 'highlight.js/styles/github-dark.css';

// 代码块组件 - 支持复制和执行
interface CodeBlockProps {
  language?: string;
  children: string;
}

const CodeBlock: React.FC<CodeBlockProps> = memo(({ language, children }) => {
  const [copied, setCopied] = useState(false);
  const [executing, setExecuting] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      message.success('已复制到剪贴板');
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      message.error('复制失败');
    }
  }, [children]);

  const handleExecute = useCallback(() => {
    // 对于 JavaScript 代码，输出到控制台
    if (language === 'javascript' || language === 'js' || language === 'typescript' || language === 'ts') {
      try {
        setExecuting(true);
        console.log('执行代码:', children);
        message.info('代码已输出到控制台');
      } catch (err) {
        message.error('执行失败: ' + (err as Error).message);
      } finally {
        setExecuting(false);
      }
    } else {
      message.info(`暂不支持执行 ${language} 代码`);
    }
  }, [children, language]);

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-language">{language || 'text'}</span>
        <Space size={4}>
          {(language === 'javascript' || language === 'js' || language === 'typescript' || language === 'ts') && (
            <Tooltip title="在控制台执行">
              <Button
                type="text"
                size="small"
                icon={<PlayCircleOutlined />}
                onClick={handleExecute}
                loading={executing}
                className="code-action-btn"
              />
            </Tooltip>
          )}
          <Tooltip title={copied ? '已复制' : '复制代码'}>
            <Button
              type="text"
              size="small"
              icon={copied ? <CheckOutlined /> : <CopyOutlined />}
              onClick={handleCopy}
              className="code-action-btn"
            />
          </Tooltip>
        </Space>
      </div>
      <pre className="code-block-content">
        <code className={`language-${language || 'text'}`}>{children}</code>
      </pre>
    </div>
  );
});

CodeBlock.displayName = 'CodeBlock';

// 从 React children 提取纯文本（rehype-highlight 会把 children 变成元素数组）
const extractText = (node: React.ReactNode): string => {
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (React.isValidElement(node) && node.props.children) {
    return extractText(node.props.children)
  }
  return ''
}

// 自定义代码组件
const CodeComponent: React.FC<{
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}> = ({ inline, className, children }) => {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : undefined;
  const codeText = extractText(children).replace(/\n$/, '');

  if (inline) {
    return <code className="inline-code">{children}</code>;
  }

  return <CodeBlock language={language}>{codeText}</CodeBlock>;
};

// Markdown 渲染器 Props
interface MarkdownRendererProps {
  content: string;
  className?: string;
}

// Markdown 渲染器组件
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = memo(({ content, className }) => {
  return (
    <div className={`markdown-body ${className || ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          code: CodeComponent as any,
          // 自定义链接渲染 - 在新窗口打开
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          // 自定义表格渲染
          table: ({ children }) => (
            <div className="table-wrapper">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});

MarkdownRenderer.displayName = 'MarkdownRenderer';

export default MarkdownRenderer;
