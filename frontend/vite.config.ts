import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig(({mode})=>{
  const env=loadEnv(mode,'..','')
  const preview=process.env.PREVIEW_ORIGIN||env.PREVIEW_ORIGIN||'http://127.0.0.1:8001'
  return { plugins: [react()], server: { proxy: { '/api': process.env.API_PROXY_TARGET||'http://127.0.0.1:8000' }, headers: {
    'Content-Security-Policy': `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://localhost:${process.env.VITE_DEV_PORT||'5173'}; frame-src ${preview}; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`,
    'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'
  } } }
})
