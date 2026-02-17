/// <reference types="vitest" />
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, normalizePath, type ProxyOptions } from 'vite'
import vue from '@vitejs/plugin-vue'
import type { IncomingMessage, ClientRequest, IncomingHttpHeaders } from 'node:http'

const __dirname = dirname(fileURLToPath(import.meta.url))

const VITE_PROXY_TARGET = 'http://127.0.0.1:62081'

const CHUNK_ROUTES = [
  {
    name: 'runtime',
    match: [
      'node_modules/vue/',
      'node_modules/vue-i18n/',
      'node_modules/base64-helpers/',
      'lib/shared/encoding/base64',
    ],
  },
  {
    name: 'treeview',
    match: ['node_modules/reka-ui/', 'lib/shared/components/Tree'],
  },
] as const

const createProxyConfig = (target: string, includeAuth = false): ProxyOptions => ({
  target,
  changeOrigin: true,
  secure: false,
  cookieDomainRewrite: '',
  configure: (proxy) => {
    proxy.on('proxyReq', (proxyReq: ClientRequest, req: IncomingMessage) => {
      if (includeAuth) {
        proxyReq.setHeader('Authorization', 'ApiKey test:test')
      }
      if (req.headers.cookie) {
        proxyReq.setHeader('Cookie', req.headers.cookie)
      }
    })
    proxy.on('proxyRes', (proxyRes: IncomingMessage & { headers: IncomingHttpHeaders }, req, res) => {
      const cookies = proxyRes.headers['set-cookie']
      if (cookies) {
        proxyRes.headers['set-cookie'] = cookies.map((cookie: string) =>
          cookie.replace(/Domain=[^;]+;?/gi, ''),
        )
      }
      if (req.headers.origin) {
        res.setHeader('Access-Control-Allow-Origin', req.headers.origin)
        res.setHeader('Access-Control-Allow-Credentials', 'true')
      }
    })
  },
})

export default defineConfig(({ mode }) => {
  const isProduction = mode === 'production'

  return {
    plugins: [vue()],
    appType: 'spa',
    test: {
      globals: true,
      environment: 'jsdom',
    },
    server: {
      port: 3000,
      cors: {
        origin: true,
        credentials: true,
        methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With'],
      },
      proxy: {
        '/api': createProxyConfig(VITE_PROXY_TARGET, true),
        '/locations': createProxyConfig(VITE_PROXY_TARGET),
        '/administration': createProxyConfig(VITE_PROXY_TARGET),
        '/media': createProxyConfig(VITE_PROXY_TARGET),
        '/static': createProxyConfig(VITE_PROXY_TARGET),
      },
    },
    resolve: {
      alias: {
        '@': resolve(__dirname, './lib'),
      },
    },
    define: {
      'process.env.NODE_ENV': isProduction ? '"production"' : '"development"',
      '__VUE_OPTIONS_API__': false,
      '__VUE_PROD_DEVTOOLS__': false,
      '__VUE_PROD_HYDRATION_MISMATCH_DETAILS__': true,
    },
    build: {
      manifest: 'manifest.json',
      sourcemap: !isProduction,
      minify: isProduction,
      lib: {
        name: 'StorageService',
        entry: {
          'location-directory-picker': resolve(
            __dirname,
            'lib/location-directory-picker/index.ts',
          ),
        },
        formats: ['es'],
      },
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            const normalized = normalizePath(id)
            for (const route of CHUNK_ROUTES) {
              if (route.match.some(pattern => normalized.includes(pattern))) {
                return route.name
              }
            }
            return undefined
          },
          chunkFileNames: '[name]-[hash].js',
        },
      },
    },
  }
})
