import {APP_URL,PREVIEW_URL} from './urls'
import {test,expect} from '@playwright/test'
import {mkdir,writeFile} from 'node:fs/promises'

test('readable creative workflow at 1366×768 and 1920×1080',async({browser,page})=>{
 test.setTimeout(120000)
 await mkdir('../artifacts/brand-revamp',{recursive:true})
 await page.goto('/admin')
 await page.getByLabel('Organizer password',{exact:true}).fill('browser-test-password-2026')
 await page.getByRole('button',{name:'Open control room'}).click()
 await expect(page.getByRole('heading',{name:'Let’s make a great game jam.'})).toBeVisible()
 const session=await (await page.request.get('/api/auth/session')).json()
 const headers={'Origin':APP_URL,'X-CSRF-Token':session.csrf}
 await page.request.post('/api/admin/timer',{headers,data:{action:'reset',minutes:120}})
 await page.request.patch('/api/admin/event',{headers,data:{frozen:false,paused:false,emergency_mode:false,primary:'mock',fallback:''}})
 await page.request.post('/api/admin/timer',{headers,data:{action:'start'}})
 await page.reload()
 const created=await page.request.post('/api/admin/teams',{headers,data:{name:'Curious Creators'}})
 expect(created.ok()).toBe(true)
 const code=(await created.json()).code
 const teamContext=await browser.newContext()
 const guestContext=await browser.newContext()
 const guest=await guestContext.newPage()
 await guest.goto(APP_URL+'/')
 await expect(guest.getByRole('heading',{name:'Welcome, game maker.'})).toBeVisible()
 const team=await teamContext.newPage()
 await team.goto(APP_URL+'/')
 await team.getByLabel('Your team access code').fill(code)
 await team.getByRole('button',{name:'Enter the studio'}).click()
 await expect(team.getByRole('heading',{name:'Your ideas. Ready to play.'})).toBeVisible()
 const measurements=[]
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  const name=`${size.width}x${size.height}`
  await guest.setViewportSize(size)
  await guest.screenshot({path:`../artifacts/brand-revamp/login-team-${name}.png`,animations:'disabled'})
  await guest.locator('.login-modes button').nth(1).click()
  await guest.screenshot({path:`../artifacts/brand-revamp/login-organizer-${name}.png`,animations:'disabled'})
  await guest.locator('.login-modes button').nth(0).click()
  await page.setViewportSize(size);await page.evaluate(()=>scrollTo(0,0))
  await page.screenshot({path:`../artifacts/brand-revamp/organizer-${name}.png`})
  await page.getByRole('button',{name:'Connect AI',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'Connect your AI assistant'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Save AI connection'})).toBeEnabled()
  await page.screenshot({path:`../artifacts/brand-revamp/connect-ai-${name}.png`,animations:'disabled'})
  await page.getByRole('button',{name:'Close dialog'}).click()
  await team.setViewportSize(size);await team.evaluate(()=>scrollTo(0,0))
  await team.screenshot({path:`../artifacts/brand-revamp/studio-empty-${name}.png`})
  const sizes=await team.evaluate(()=>{
   const px=(s:string)=>parseFloat(getComputedStyle(document.querySelector(s)!).fontSize)
   return {width:innerWidth,height:innerHeight,zoom:devicePixelRatio,body:px('body'),description:px('.workspace-intro p'),composer:px('#game-prompt'),button:px('.generate-button'),heading:px('.panel-heading h2'),pageWidth:document.documentElement.scrollWidth,editor:document.querySelector('#game-prompt')!.getBoundingClientRect().toJSON(),generate:document.querySelector('.generate-button')!.getBoundingClientRect().toJSON()}
  })
  measurements.push(sizes)
  expect(sizes.body).toBeGreaterThanOrEqual(16);expect(sizes.description).toBeGreaterThanOrEqual(14)
  expect(sizes.composer).toBeGreaterThanOrEqual(16);expect(sizes.button).toBeGreaterThanOrEqual(15)
  expect(sizes.heading).toBeGreaterThanOrEqual(20);expect(sizes.pageWidth).toBeLessThanOrEqual(size.width)
  expect(sizes.editor.height).toBeGreaterThanOrEqual(160)
  expect(sizes.generate.height).toBeGreaterThanOrEqual(48)
  await team.getByRole('button',{name:'Generate game',exact:true}).scrollIntoViewIfNeeded()
  await expect(team.getByRole('button',{name:'Generate game',exact:true})).toBeInViewport()
  expect(await page.getByRole('button',{name:'Connect AI',exact:true}).evaluate(el=>el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44)
 }
 await team.getByRole('textbox',{name:'Describe your game or changes'}).fill('Create a colorful arcade game where I collect stars')
 await team.getByRole('button',{name:'Generate game',exact:true}).click()
 await expect(team.getByTitle('Cosmic Collector preview')).toBeVisible()
 await expect(team.frameLocator('iframe').locator('canvas')).toBeVisible()
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  await team.setViewportSize(size);await team.evaluate(()=>scrollTo(0,0))
  await team.screenshot({path:`../artifacts/brand-revamp/studio-playing-${size.width}x${size.height}.png`})
  await team.screenshot({path:`../artifacts/brand-revamp/studio-full-${size.width}x${size.height}.png`,fullPage:true})
 }
 // Populate a real six-entry gallery in the isolated mock database.
 const teamSession=await (await team.request.get('/api/auth/session',{headers:{'X-Studio-Role':'team'}})).json()
 const teamHeaders={'Origin':APP_URL,'X-CSRF-Token':teamSession.csrf,'X-Studio-Role':'team'}
 const workspace=await (await team.request.get('/api/workspace',{headers:teamHeaders})).json()
 expect((await team.request.post('/api/submissions',{headers:teamHeaders,data:{version_id:workspace.team.current_version,title:'Starbound',description:'Collect the stars and bring our little explorer safely home.'}})).ok()).toBe(true)
 const starters=await (await team.request.get('/api/starters',{headers:teamHeaders})).json()
 for(const [i,title] of ['Gravity Garden','Neon Dash','Forest Guardian','Timekeeper','Hidden Hero'].entries()){
  const created=await page.request.post('/api/admin/teams',{headers,data:{name:['Bright Sparks','Copper Code','Tarkwa Titans','Team Orbit','Code Collective'][i]}})
  expect(created.ok()).toBe(true)
  const other=await browser.newContext()
  const auth=await other.request.post(APP_URL+'/api/auth/team',{headers:{Origin:APP_URL},data:{code:(await created.json()).code}})
  expect(auth.ok()).toBe(true)
  const otherHeaders={'Origin':APP_URL,'X-CSRF-Token':(await auth.json()).csrf,'X-Studio-Role':'team'}
  const saved=await other.request.post(APP_URL+`/api/starters/${starters[i].id}`,{headers:otherHeaders,data:{}})
  expect(saved.ok()).toBe(true)
  expect((await other.request.post(APP_URL+'/api/submissions',{headers:otherHeaders,data:{version_id:(await saved.json()).id,title,description:'A small world full of surprising challenges. Use the keyboard to explore and play.'}})).ok()).toBe(true)
  await other.close()
 }
 await page.reload()
 await page.getByRole('button',{name:'Submission gallery'}).click()
 await expect(page.locator('.gallery-card')).toHaveCount(6)
 expect(await page.locator('iframe').count()).toBe(0)
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  await page.setViewportSize(size)
  await page.screenshot({path:`../artifacts/brand-revamp/gallery-${size.width}x${size.height}.png`,fullPage:true})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 }
 await page.getByRole('button',{name:'Play game: Starbound',exact:true}).click()
 await expect(page.getByTitle('Starbound preview')).toBeVisible()
 await expect(page.frameLocator('iframe').locator('canvas')).toBeVisible()
 await page.getByRole('button',{name:'Close dialog'}).click()
 await expect(page.locator('iframe')).toHaveCount(0)
 await page.getByRole('button',{name:'Event',exact:true}).click()
 // Save configuration through the actual form without sending a paid generation.
 await page.getByRole('button',{name:'Connect AI',exact:true}).click()
 await page.getByLabel('API key',{exact:true}).fill('browser-test-key-never-a-real-credential')
 await page.getByLabel('Model ID',{exact:false}).fill('browser-test-model')
 await page.getByLabel('Input price',{exact:true}).fill('1')
 await page.getByLabel('Output price',{exact:true}).fill('2')
 await page.getByLabel('Use this provider for new games').uncheck()
 await page.getByRole('button',{name:'Save AI connection'}).click()
 await expect(page.getByText('AI connection saved and ready. No paid request was made.')).toBeVisible()
 await expect(page.getByPlaceholder('Enter a replacement key (optional)')).toHaveValue('')
 await writeFile('../artifacts/brand-revamp/measurements.json',JSON.stringify(measurements,null,2))
 await teamContext.close()
 await guestContext.close()
})
