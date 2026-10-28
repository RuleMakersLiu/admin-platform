import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api/generator': {
        target: 'http://localhost:8082',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/api/deploy': {
        target: 'http://localhost:8083',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/api': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // Vite 8（Rolldown）已移除 esbuild.pure；console 剥离改由 terser pure_funcs 等价实现
    // （仅剥 debug 级调用，保留 console.error/warn）
    minify: 'terser',
    terserOptions: {
      compress: {
        pure_funcs: ['console.log', 'console.debug', 'console.info', 'console.trace'],
      },
    },
    rollupOptions: {
      output: {
        // Vite 8 起 manualChunks 不再支持，改用 Rolldown advancedChunks
        advancedChunks: {
          groups: [
            { name: 'vendor', test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)([\\/]|$)/ },
            { name: 'antd', test: /node_modules[\\/](antd|@ant-design|rc-[^\\/]+)/ },
            {
              name: 'markdown',
              test: /node_modules[\\/](react-markdown|remark-[\w.-]+|rehype-[\w.-]+|micromark[\w.-]*|mdast-[\w.-]+|unified|unist-[\w.-]+|vfile[\w.-]*|highlight\.js|lowlight|hast-[\w.-]+)/,
            },
          ],
        },
      },
    },
  },
})
