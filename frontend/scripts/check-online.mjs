// Read-only public-network rehearsal: normal organizer login, saved preview, no AI calls.
import {readFile,mkdir} from 'node:fs/promises'
import {fileURLToPath} from 'node:url'
import {chromium} from '@playwright/test'
const root=new URL('../../',import.meta.url)
const status=JSON.parse(await readFile(new URL('artifacts/online-status.json',root),'utf8'))
if(status.status!=='ready')throw new Error('Start Event Online first; no ready public links were found.')
const access=await readFile(new URL('data-private/online-access.html',root),'utf8')
const privateUrl=access.match(/href="([^"]*#event-organizer=[^"]+)"/)?.[1]?.replaceAll('&amp;','&')
if(!privateUrl)throw new Error('The private organizer access file is missing.')
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true})
try{
 const context=await browser.newContext({viewport:{width:1366,height:900}})
 const page=await context.newPage()
 const response=await page.goto(status.app_url,{waitUntil:'domcontentloaded',timeout:45000})
 if(!response?.ok())throw new Error('Public website did not return success.')
 const csp=response.headers()['content-security-policy']||''
 if(!csp.includes(`frame-src ${status.preview_url};`))throw new Error('Public app preview policy does not match.')
 await page.getByRole('heading',{name:'Welcome, game maker.'}).waitFor()
 await page.goto(privateUrl,{waitUntil:'domcontentloaded',timeout:45000})
 await page.getByRole('heading',{name:'Let’s make a great game jam.'}).waitFor({timeout:30000})
 if(page.url().includes('#'))throw new Error('Private organizer fragment was retained.')
 const cookies=await context.cookies(status.app_url)
 const session=cookies.find(c=>c.name==='deepstem_admin_session')
 if(!session?.secure||!session.httpOnly||session.sameSite!=='Strict')throw new Error('Secure organizer cookie was not set.')
 const denied=await context.request.get(status.preview_url+'/api/admin/dashboard')
 if(denied.status()!==404)throw new Error('Preview origin exposed an application route.')
 const dashboard=await page.evaluate(async()=>{
  const r=await fetch('/api/admin/dashboard',{headers:{'X-Studio-Role':'admin'}})
  if(!r.ok)throw new Error('Organizer API authentication failed.')
  return r.json()
 })
 const team=dashboard.teams.find(t=>t.current_version)
 let gameVerified=false
 if(team){
  const requestPromise=page.waitForRequest(r=>r.url().startsWith(status.preview_url+'/play/'),{timeout:30000})
  await page.getByRole('button',{name:`Inspect ${team.name}`,exact:true}).click()
  await page.frameLocator('iframe').locator('canvas').waitFor({timeout:30000})
  const request=await requestPromise
  if((await request.allHeaders()).cookie?.includes('deepstem_'))throw new Error('An application session cookie reached the preview origin.')
  if(await page.locator('iframe').getAttribute('sandbox')!=='allow-scripts')throw new Error('Incorrect frame sandbox.')
  const frame=page.frames().find(f=>f.url().startsWith(status.preview_url+'/play/'))
  const isolated=await frame.evaluate(()=>{
   let parentBlocked=false,storageBlocked=false,cookiesBlocked=false
   try{void parent.document.body}catch{parentBlocked=true}
   try{localStorage.setItem('isolation-check','1')}catch{storageBlocked=true}
   try{void document.cookie}catch{cookiesBlocked=true}
   return parentBlocked&&storageBlocked&&cookiesBlocked
  })
  if(!isolated)throw new Error('Saved game could access application context or storage.')
  await mkdir(new URL('artifacts',root),{recursive:true})
  await page.screenshot({path:fileURLToPath(new URL('artifacts/online-preview-verified.png',root)),fullPage:true})
  await page.getByRole('button',{name:'Close dialog'}).click()
  gameVerified=true
 }
 await context.close()
 console.log(JSON.stringify({publicWebsite:true,privateOrganizerLogin:true,secureCookies:true,previewOriginSeparate:true,previewApiBlocked:true,savedGameIsolation:gameVerified?'passed':'no saved game available',paidAiCalls:0},null,2))
}finally{await browser.close()}
