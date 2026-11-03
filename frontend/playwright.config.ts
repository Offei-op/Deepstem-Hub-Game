import { defineConfig } from '@playwright/test'
const py=process.env.PYTHON_EXECUTABLE||(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python')
const runId=process.env.E2E_RUN_ID||Date.now().toString()
const appPort=process.env.E2E_APP_PORT||'15173',apiPort=process.env.E2E_API_PORT||'18000',previewPort=process.env.E2E_PREVIEW_PORT||'18001'
const appUrl=`http://localhost:${appPort}`,previewUrl=`http://127.0.0.1:${previewPort}`
const env={E2E_RUN_ID:runId,E2E_APP_ORIGIN:appUrl,E2E_API_PORT:apiPort,E2E_PREVIEW_PORT:previewPort,PREVIEW_ORIGIN:previewUrl,API_PROXY_TARGET:`http://127.0.0.1:${apiPort}`,VITE_DEV_PORT:appPort}
export default defineConfig({
 testDir:'./e2e',timeout:60000,expect:{timeout:10000},workers:1,reporter:'list',
 use:{baseURL:appUrl,viewport:{width:1440,height:1100},
   browserName:'chromium',...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{}),
   screenshot:'only-on-failure',trace:'retain-on-failure'},
 webServer:[
   {command:`"${py}" ../scripts/test_server.py api`,url:`http://127.0.0.1:${apiPort}/api/health`,env,timeout:60000,reuseExistingServer:false},
   {command:`"${py}" ../scripts/test_server.py preview`,url:`${previewUrl}/health`,env,timeout:60000,reuseExistingServer:false},
   {command:`npm run dev -- --host 127.0.0.1 --port ${appPort} --strictPort`,url:appUrl,env,timeout:60000,reuseExistingServer:false}
 ]
})
