/**轻量代码编辑器（CodeMirror）：语法高亮 + 行号 + 格式校验提示。
 * 按文件扩展名自动选语言。用于 needs_human 在线编辑生成的代码。*/
import CodeMirror from '@uiw/react-codemirror'
import { javascript } from '@codemirror/lang-javascript'
import { html } from '@codemirror/lang-html'
import { css } from '@codemirror/lang-css'
import { oneDark } from '@codemirror/theme-one-dark'

const EXT_LANG: Record<string, () => any> = {
  '.js': () => javascript({ jsx: true }),
  '.jsx': () => javascript({ jsx: true }),
  '.ts': () => javascript({ typescript: true }),
  '.tsx': () => javascript({ jsx: true, typescript: true }),
  '.mjs': () => javascript(),
  '.vue': () => html(),
  '.html': () => html(),
  '.htm': () => html(),
  '.xml': () => html(),
  '.css': () => css(),
  '.scss': () => css(),
  '.less': () => css(),
  '.json': () => javascript(),
}

function getExtension(filename: string): string {
  const parts = filename.toLowerCase().split('.')
  return parts.length > 1 ? '.' + parts[parts.length - 1] : ''
}

interface CodeEditorProps {
  value: string
  onChange?: (value: string) => void
  filename?: string
  height?: string
  readOnly?: boolean
}

export default function CodeEditor({ value, onChange, filename, height = '300px', readOnly = false }: CodeEditorProps) {
  const ext = getExtension(filename || '')
  const langExt = EXT_LANG[ext]?.() || javascript()

  return (
    <CodeMirror
      value={value}
      height={height}
      theme={oneDark}
      extensions={[langExt]}
      onChange={onChange}
      readOnly={readOnly}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLine: !readOnly,
        highlightActiveLineGutter: !readOnly,
        foldGutter: true,
        autocompletion: !readOnly,
        bracketMatching: true,
        closeBrackets: !readOnly,
        indentOnInput: !readOnly,
      }}
      style={{ fontSize: 13, borderRadius: 6, overflow: 'hidden' }}
    />
  )
}
