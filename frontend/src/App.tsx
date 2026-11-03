import { useEffect, useRef, useState } from 'react'
import { ArrowRight, ArrowUpRight, Code2, KeyRound, Shield, Sparkles, Users, Clock3 } from 'lucide-react'
import { api, setSession, setViewRole } from './api'
import { Brand, BrandWaves, ErrorNotice } from './components'
import type { Session } from './types'
import { Studio } from './Studio'
import { Admin } from './Admin'

function Login({onLogin,initialError}:{onLogin:(s:Session)=>void;initialError:string}){
 const [admin,setAdmin]=useState(window.location.pathname.startsWith('/admin'))
 const [code,setCode]=useState(''),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(initialError)
 function mode(organizer:boolean){setAdmin(organizer);setError('');window.history.replaceState({},'',organizer?'/admin':'/')}
 async function submit(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{onLogin(await api<Session>(admin?'/auth/admin':'/auth/team','POST',admin?{password}:{code}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="login-page">
  <header className="login-header"><Brand/><span className="event-location">AI GAME JAM STUDIO <span className="live-dot"/> UMaT · Ghana</span><button className="secondary" onClick={()=>mode(!admin)}>{admin?'Team sign in':'Organizer access'}<ArrowUpRight size={18}/></button></header>
  <main className="login-main">
   <div className="login-story"><span className="eyebrow">BUILD SOMETHING WORTH PLAYING</span><h1>Big ideas.<br/><span>Playable</span> worlds.</h1><p>Turn your ideas into games with AI.<br/>No coding experience needed.</p><div className="story-tags"><span><Users size={20}/>10 teams</span><span><Clock3 size={20}/>2 hours</span><span><Sparkles size={20}/>One big idea</span></div><div className="login-art"><svg viewBox="0 460 900 310" role="img" aria-label="Three student game makers creating together at their laptops"><image href="/brand/game-makers.png" width="1586" height="992" preserveAspectRatio="none"/></svg></div></div>
   <div className="login-form-side"><div className="login-card">
    <div className="login-modes" aria-label="Sign-in options"><button aria-pressed={!admin} onClick={()=>mode(false)}>Team access</button><button aria-pressed={admin} onClick={()=>mode(true)}>Organizer access</button></div>
    <div className="card-icon">{admin?<Shield size={28}/>:<KeyRound size={28}/>}</div><h2>{admin?'Welcome, organizer.':'Welcome, game maker.'}</h2><p>{admin?'Set up your teams, connect AI, and get the jam started.':'Enter your team code and start creating.'}</p>
    {admin&&<div className="local-access-help">Running on your laptop? Open <strong>Start Studio.cmd</strong> for automatic organizer sign-in. You can also use your password below.</div>}
    <form onSubmit={submit}>
     {admin?<label>Organizer password<input autoFocus type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required maxLength={200} placeholder="Enter your organizer password"/></label>:<label>Your team access code<div className="input-with-icon"><KeyRound size={20}/><input autoFocus value={code} onChange={e=>setCode(e.target.value.toUpperCase())} autoComplete="off" spellCheck={false} required maxLength={80} placeholder="DS-XXXXXXXXXX"/></div><span className="field-help">Ask your organizer if you haven’t received a code.</span></label>}
     <ErrorNotice message={error}/><button className="primary login-submit" disabled={busy}>{busy?'Opening your studio…':admin?'Open control room':'Enter the studio'}<ArrowRight size={20}/></button>
    </form><div className="login-assurance"><Shield size={18}/>{admin?'Your organizer session stays private.':'No account or API key needed.'}</div>
   </div><div className="login-tip"><Code2 size={24}/><p><strong>First time making a game?</strong><br/>You’re in the right place. Start with one small idea.</p></div></div>
  </main><section className="login-steps" aria-label="How the studio works">{[['Describe','Tell us your game idea in plain language.'],['Generate','Use AI to create your first game.'],['Play','Test and explore with your team.'],['Make it yours','Ask for changes. Bring your ideas to life.']].map(([title,description],i)=><div key={title}><span>{i+1}</span><div><h3>{title}</h3><p>{description}</p></div></div>)}</section><footer className="login-footer"><span>DeepStem HUB × ASCES · UMaT</span><span>Made for curious minds.</span><span>AI Game Jam · 2026</span></footer><BrandWaves/>
 </div>
}

export default function App(){
 const [session,updateSession]=useState<Session|null>(null),[loading,setLoading]=useState(true),[startupError,setStartupError]=useState('')
 const initialized=useRef(false)
 function received(s:Session|null){setSession(s);updateSession(s)}
 useEffect(()=>{
  const consumeLocalLink=()=>{const params=new URLSearchParams(window.location.hash.slice(1));const token=params.get('local-organizer'),code=params.get('team-code'),eventPassword=params.get('event-organizer');if(!token&&!code&&!eventPassword)return false
   window.history.replaceState({},'',token||eventPassword?'/admin':'/');setViewRole(token||eventPassword?'admin':'team');setLoading(true)
   const request=eventPassword?api<Session>('/auth/admin','POST',{password:eventPassword}):token?api<Session>('/auth/local-organizer','POST',{token}):api<Session>('/auth/team','POST',{code})
   request.then(received).catch(e=>setStartupError(e.message)).finally(()=>setLoading(false))
   return true
  }
  if(!initialized.current){initialized.current=true;setViewRole(window.location.pathname.startsWith('/admin')?'admin':'team');if(!consumeLocalLink())api<Session>('/auth/session').then(received).catch(()=>{}).finally(()=>setLoading(false))}
  const expire=()=>received(null);window.addEventListener('session-expired',expire);window.addEventListener('hashchange',consumeLocalLink)
  return()=>{window.removeEventListener('session-expired',expire);window.removeEventListener('hashchange',consumeLocalLink)}
 },[])
 async function logout(){try{await api('/auth/logout','POST');received(null)}catch(e){window.alert((e as Error).message)}}
 if(loading)return <div className="app-loading"><Brand/><span className="spinner"/><p>Opening your studio…</p></div>
 return session?session.role==='admin'?<Admin session={session} logout={logout}/>:<Studio session={session} logout={logout}/>:<Login onLogin={received} initialError={startupError}/>
}
