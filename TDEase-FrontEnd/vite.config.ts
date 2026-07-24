import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vueDevTools from "vite-plugin-vue-devtools";
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import { fileURLToPath, URL } from 'node:url'
import path from 'node:path'
import loglevel from 'loglevel'

// @ts-expect-error process is a nodejs global
const devHost = process.env.TDEASE_FRONTEND_HOST;

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const proxyLogger = loglevel.getLogger('vite-proxy')
  proxyLogger.setLevel(mode === 'development' ? 'info' : 'warn')

  return {
    // Electron 打包态用 file:// 加载，需要相对路径 base（否则 /assets/... 解析到文件系统根）
    // dev server 对相对 base 同样正常工作
    base: './',
    plugins: [
      mode === 'development' && vueDevTools(),
      vue(),
      VueI18nPlugin({
        include: path.resolve(__dirname, 'src/locales/**/*.json'),
      }),
    ].filter(Boolean),
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) {
              return undefined
            }
            if (id.includes('xlsx')) {
              return 'vendor-xlsx'
            }
            if (id.includes('ag-grid-vue3')) {
              return 'vendor-grid-vue'
            }
            if (id.includes('ag-grid-community')) {
              return 'vendor-grid-core'
            }
            if (id.includes('@vue-flow') || id.includes('dagre')) {
              return 'vendor-workflow'
            }
            if (id.includes('/d3-') || id.includes('\\d3-') || id.includes('/d3/') || id.includes('\\d3\\')) {
              return 'vendor-d3'
            }
            if (id.includes('@uppy')) {
              return 'vendor-upload'
            }
            if (id.includes('element-plus') || id.includes('@element-plus') || id.includes('@iconify')) {
              return 'vendor-ui'
            }
            if (id.includes('markdown-it') || id.includes('dompurify')) {
              return 'vendor-ai'
            }
            if (
              id.includes('vue-router')
              || id.includes('/vue/')
              || id.includes('\\vue\\')
              || id.includes('pinia')
              || id.includes('@vueuse')
              || id.includes('@tanstack')
            ) {
              return 'vendor-vue'
            }
            return 'vendor-misc'
          },
        },
      },
    },

    // Keep the dev port fixed so local backend/proxy and Electron dev mode stay deterministic.
    clearScreen: false,
    server: {
      port: 1420,
      strictPort: true, // 必须占用 1420；否则直接失败，避免第二个 Vite 漂移到 1421 污染 HMR
      host: devHost || '0.0.0.0', // 允许外部访问
      open: '/', // 明确指定打开根路径
      hmr: devHost
        ? {
            protocol: "ws",
            host: devHost,
            port: 1421,
          }
        : undefined,
      watch: {
        ignored: [],
      },
      proxy: {
        '/health': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
          ws: true, // 支持 WebSocket
          configure: (proxy, _options) => {
            proxy.on('error', (err, _req, _res) => {
              proxyLogger.error('Proxy error', err)
            });
            proxy.on('proxyReq', (proxyReq, req, _res) => {
              proxyLogger.info('Proxying request', {
                method: req.method,
                url: req.url,
                path: proxyReq.path,
              })
            });
          },
        },
        '/ws': {
          target: 'http://127.0.0.1:8000',
          ws: true,
          changeOrigin: true,
        },
      }
    },

  }
});
