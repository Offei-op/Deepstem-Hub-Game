import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import { ReferenceImages, imageForUpload } from './ReferenceImages'
import { NewEventDialog, EventArchiveDialog } from './EventDialogs'
import { api } from './api'
import type { Config, StyleReference } from './types'

vi.mock('./api',()=>({api:vi.fn(),money:(micro:number)=>'$'+(micro/1e6).toFixed(2)}))
beforeEach(()=>{vi.mocked(api).mockReset();vi.mocked(api).mockResolvedValue({})})

const reference=(id:string):StyleReference=>({id,name:`style-${id}.jpg`,width:768,height:512,bytes:1000,created:1,url:`/api/references/${id}/image`})
const config:Config={event_key:'current-event',name:'Current jam',theme:'Gravity',announcement:'',paused:false,emergency_mode:false,frozen:true,phase:'ended',remaining_seconds:0,ends_at:null,max_teams:10,initial_allowance:12,emergency_allowance:3,budget_micro:20000000,max_concurrent:10,max_input_tokens:55000,max_output_tokens:12000,primary:'openai',fallback:'gemini'}

test('three reference images show clear remove controls and disable further additions',()=>{
 render(<ReferenceImages references={['one','two','three'].map(reference)} disabled={false} onChange={vi.fn()} onBusy={vi.fn()} onError={vi.fn()}/>)
 expect(screen.getAllByRole('img')).toHaveLength(3)
 expect(screen.getByRole('button',{name:'Add another image'})).toBeDisabled()
 expect(screen.getByRole('button',{name:'Remove reference style-one.jpg'})).toBeEnabled()
})

test('removing a reference refreshes the team list and releases the busy state',async()=>{
 const change=vi.fn().mockResolvedValue(undefined),busy=vi.fn()
 render(<ReferenceImages references={[reference('one')]} disabled={false} onChange={change} onBusy={busy} onError={vi.fn()}/>)
 fireEvent.click(screen.getByRole('button',{name:'Remove reference style-one.jpg'}))
 await waitFor(()=>expect(api).toHaveBeenCalledWith('/references/one','DELETE'))
 await waitFor(()=>expect(change).toHaveBeenCalledOnce())
 expect(busy.mock.calls.map(c=>c[0])).toEqual([true,false])
})

test('unsupported images are rejected before opening or uploading them',async()=>{
 await expect(imageForUpload(new File(['<svg/>'],'unsafe.svg',{type:'image/svg+xml'}))).rejects.toThrow('JPEG, PNG or WebP')
 expect(api).not.toHaveBeenCalled()
})

test('new event requires explicit confirmation and sends the active event identity',async()=>{
 const done=vi.fn().mockResolvedValue(undefined)
 const view=render(<NewEventDialog config={config} running={false} onClose={vi.fn()} onDone={done}/>)
 const create=screen.getByRole('button',{name:'Archive current & create event'})
 expect(create).toBeDisabled()
 fireEvent.change(screen.getByLabelText('New event name'),{target:{value:'November jam'}})
 fireEvent.change(screen.getByLabelText('Type NEW EVENT to confirm'),{target:{value:'NEW EVENT'}})
 expect(create).toBeEnabled()
 // A background dashboard refresh must not silently retarget an open confirmation.
 view.rerender(<NewEventDialog config={{...config,event_key:'event-created-by-another-organizer'}} running={false} onClose={vi.fn()} onDone={done}/>)
 fireEvent.click(create)
 await waitFor(()=>expect(api).toHaveBeenCalledWith('/admin/events','POST',expect.objectContaining({expected_event_key:'current-event',confirmation:'NEW EVENT',name:'November jam',minutes:120})))
 await waitFor(()=>expect(done).toHaveBeenCalledOnce())
})

test('new event stays disabled while games are generating',()=>{
 render(<NewEventDialog config={config} running onClose={vi.fn()} onDone={vi.fn()}/>)
 fireEvent.change(screen.getByLabelText('Type NEW EVENT to confirm'),{target:{value:'NEW EVENT'}})
 expect(screen.getByRole('button',{name:'Archive current & create event'})).toBeDisabled()
})

test('an empty archive explains where previous events will appear',async()=>{
 vi.mocked(api).mockResolvedValue([])
 render(<EventArchiveDialog onClose={vi.fn()}/>)
 expect(await screen.findByText('No archived events yet')).toBeInTheDocument()
 expect(api).toHaveBeenCalledWith('/admin/events')
})
