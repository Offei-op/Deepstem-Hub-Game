import {StrictMode} from 'react'
import {render,screen,waitFor,act} from '@testing-library/react'
import {vi} from 'vitest'
import App from './App'

vi.mock('./Admin',()=>({Admin:()=> <h1>Local organizer is ready</h1>}))
afterEach(()=>{vi.unstubAllGlobals();window.history.replaceState({},'','/')})

test('private online organizer fragment uses normal password login and is removed immediately',async()=>{
 window.history.replaceState({},'','/admin#event-organizer=test-private-event-password')
 const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({role:'admin',team_id:null,csrf:'test-csrf'})})
 vi.stubGlobal('fetch',fetchMock)
 render(<StrictMode><App/></StrictMode>)
 await screen.findByRole('heading',{name:'Local organizer is ready'})
 expect(fetchMock).toHaveBeenCalledTimes(1)
 expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/admin')
 expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({password:'test-private-event-password'})
 expect(window.location.hash).toBe('')
})

test('one-use launcher link signs in once under StrictMode and removes its fragment',async()=>{
 window.history.replaceState({},'','/admin#local-organizer=a-private-one-use-test-token')
 const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({role:'admin',team_id:null,csrf:'test-csrf'})})
 vi.stubGlobal('fetch',fetchMock)
 render(<StrictMode><App/></StrictMode>)
 await screen.findByRole('heading',{name:'Local organizer is ready'})
 expect(fetchMock).toHaveBeenCalledTimes(1)
 expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/local-organizer')
 expect(window.location.hash).toBe('')
})

test('a launcher link also works when the sign-in page is already open',async()=>{
 window.history.replaceState({},'','/admin')
 const fetchMock=vi.fn().mockImplementation(async(path:string)=>path==='/api/auth/session'
  ?{ok:false,status:401,json:async()=>({detail:'Sign in'})}
  :{ok:true,json:async()=>({role:'admin',team_id:null,csrf:'test-csrf'})})
 vi.stubGlobal('fetch',fetchMock)
 render(<App/>)
 await screen.findByRole('heading',{name:'Welcome, organizer.'})
 act(()=>{window.location.hash='local-organizer=a-fresh-local-link-token'})
 await screen.findByRole('heading',{name:'Local organizer is ready'})
 await waitFor(()=>expect(window.location.hash).toBe(''))
 expect(fetchMock.mock.calls.filter(c=>c[0]==='/api/auth/local-organizer')).toHaveLength(1)
})
