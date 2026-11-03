import type { Session } from './types'
let csrf = ''
let role:'admin'|'team' = window.location.pathname.startsWith('/admin')?'admin':'team'
export function setSession(session: Session | null) { csrf = session?.csrf || '';role=session?.role||(window.location.pathname.startsWith('/admin')?'admin':'team') }
export function setViewRole(next:'admin'|'team'){role=next}
export class ApiError extends Error { constructor(message:string, public status:number) { super(message) } }
export async function api<T>(path:string, method='GET', data?:unknown):Promise<T> {
  const response = await fetch('/api'+path, { method, credentials:'same-origin',
    headers: method==='GET' ? {'X-Studio-Role':role} : {'Content-Type':'application/json','X-CSRF-Token':csrf,'X-Studio-Role':role},
    body:method==='GET'?undefined:JSON.stringify(data ?? {}) })
  if(!response.ok) {
    const body=await response.json().catch(()=>({detail:'The studio is unreachable. Please try again.'}))
    const message=typeof body.detail==='string'?body.detail:'Please check your input and try again.'
    if(response.status===401 && !path.startsWith('/auth/'))window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(message,response.status)
  }
  return response.json()
}
export function newKey(){return crypto.randomUUID().replaceAll('-','')}
export function money(micro:number){return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:4}).format(micro/1e6)}
export function clock(seconds:number){const n=Math.max(0,Math.floor(seconds));return `${String(Math.floor(n/3600)).padStart(2,'0')}:${String(Math.floor(n%3600/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
