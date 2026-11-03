import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import { Countdown, GamePreview, Guide } from './components'
import { clock, money, api, setSession } from './api'

afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers()})
test('formats event time and budget without negative counters',()=>{
 expect(clock(7200)).toBe('02:00:00');expect(clock(-5)).toBe('00:00:00');expect(money(1_500_000)).toBe('$1.50')
})
test('renders an accessible empty state with disabled game controls',()=>{
 render(<GamePreview versionId={null}/>);expect(screen.getByText(/A little prompt/)).toBeInTheDocument()
 expect(screen.getByRole('button',{name:'Restart game'})).toBeDisabled()
 expect(document.querySelector('iframe')).toBeNull()
})
test('game frame has only script sandbox permission and a separate origin URL',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({url:'http://127.0.0.1:8001/play/signed-token'})}))
 render(<GamePreview versionId={4} title="Cosmic Collector"/>)
 await waitFor(()=>expect(screen.getByTitle('Cosmic Collector preview')).toBeInTheDocument())
 const frame=screen.getByTitle('Cosmic Collector preview')
 expect(frame).toHaveAttribute('sandbox','allow-scripts');expect(frame).toHaveAttribute('referrerpolicy','no-referrer')
 expect(frame).toHaveAttribute('src','http://127.0.0.1:8001/play/signed-token')
 expect(screen.getByRole('link',{name:'Download standalone game'})).toHaveAttribute('href','/api/versions/4/download')
 fireEvent.click(screen.getByRole('button',{name:'Stop preview'}));expect(document.querySelector('iframe')).toBeNull()
})
test('restoring an earlier version is an explicit action',()=>{
 const restore=vi.fn();vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({url:'http://127.0.0.1:8001/play/x'})}))
 render(<GamePreview versionId={2} current={false} onRestore={restore}/>)
 fireEvent.click(screen.getByRole('button',{name:'Restore this version'}));expect(restore).toHaveBeenCalledOnce()
})
test('paused countdown keeps synchronized server remaining time',()=>{
 render(<Countdown event={{phase:'paused',remaining_seconds:3661,server_time:100}}/>);
 expect(screen.getByText('01:01:01')).toBeInTheDocument();expect(screen.getByText('CLOCK PAUSED')).toBeInTheDocument()
})
test('guide explains generation and offline contingency',()=>{
 render(<Guide/>);expect(screen.getByText(/Download regularly/)).toBeInTheDocument();expect(screen.getByText('Make it yours')).toBeInTheDocument()
})
test('API sends session csrf and understandable validation errors',async()=>{
 const fetchMock=vi.fn().mockResolvedValue({ok:false,status:409,json:async()=>({detail:'AI is paused'})});vi.stubGlobal('fetch',fetchMock)
 setSession({role:'team',team_id:1,csrf:'session-csrf'})
 await expect(api('/generations','POST',{prompt:'game'})).rejects.toThrow('AI is paused')
 expect(fetchMock.mock.calls[0][1].headers['X-CSRF-Token']).toBe('session-csrf')
})
