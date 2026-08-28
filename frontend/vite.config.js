import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { quasar, transformAssetUrls } from '@quasar/vite-plugin'

// Served by nginx under /grugrutyp/ alongside the untouched legacy site at /.
export default defineConfig({
  base: '/grugrutyp/',
  plugins: [
    vue({
      template: {
        transformAssetUrls,
        compilerOptions: {
          // reactive-dep-tree registers itself as a real custom element (it bundles its
          // own Vue 2 runtime), so Vue 3 must not try to resolve it as a component.
          isCustomElement: (tag) => tag === 'reactive-dep-tree',
        },
      },
    }),
    quasar({ sassVariables: fileURLToPath(new URL('./src/quasar-variables.sass', import.meta.url)) }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 9000,
    proxy: {
      '/grugrutyp/api': {
        target: 'http://127.0.0.1:8020',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/grugrutyp\/api/, ''),
      },
    },
  },
})
