import {test,expect} from '@playwright/test'
import {APP_URL} from './urls'

test('organizer opens a contestant tab and both roles remain signed in',async({context,page})=>{
 await page.goto('/admin')
 await page.getByLabel('Organizer password',{exact:true}).fill('browser-test-password-2026')
 await page.getByRole('button',{name:'Open control room'}).click()
 await page.getByLabel('New team name').fill('Contestant View Test')
 await page.getByRole('button',{name:'Create team'}).click()
 const opened=context.waitForEvent('page')
 await page.getByRole('link',{name:'Open contestant view'}).click()
 const contestant=await opened
 await expect(contestant.getByRole('heading',{name:'Your ideas. Ready to play.'})).toBeVisible()
 await expect(contestant.locator('.team-chip strong')).toHaveText('Contestant View Test')
 await expect(contestant).toHaveURL(APP_URL+'/')
 await page.getByRole('button',{name:'Close dialog'}).click()
 await page.reload()
 await expect(page.getByRole('heading',{name:'Let’s make a great game jam.'})).toBeVisible()
 await contestant.reload()
 await expect(contestant.getByRole('heading',{name:'Your ideas. Ready to play.'})).toBeVisible()
 await contestant.getByRole('button',{name:'Sign out'}).click()
 await expect(contestant.getByRole('heading',{name:'Welcome, game maker.'})).toBeVisible()
 await page.reload()
 await expect(page.getByRole('heading',{name:'Let’s make a great game jam.'})).toBeVisible()
})
