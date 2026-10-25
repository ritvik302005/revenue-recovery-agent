import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Preload the two Latin font files so text renders in the right face at once
// (no late swap that shifts the hero). Their names are hashed at build time,
// so the links are added to index.html after bundling.
const FONT_FILES = /(archivo-latin-wdth-normal|martian-mono-latin-wdth-normal)-[\w-]+\.woff2$/

function preloadFonts() {
  return {
    name: 'preload-fonts',
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        if (!ctx.bundle) return html
        const links = Object.keys(ctx.bundle)
          .filter((file) => FONT_FILES.test(file))
          .map((file) => `<link rel="preload" href="/${file}" as="font" type="font/woff2" crossorigin>`)
        return html.replace('</head>', `    ${links.join('\n    ')}\n  </head>`)
      },
    },
  }
}

export default defineConfig({
  plugins: [react(), preloadFonts()],
  server: {
    port: 5173,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    // Tests never depend on a local frontend/.env: no bot check unless a test stubs a key.
    env: { VITE_TURNSTILE_SITE_KEY: '' },
  },
})
