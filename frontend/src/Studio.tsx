import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowDownToLine, ArrowRight, Check, ChevronDown, ChevronRight, Clock3, Gamepad2, History, Lightbulb, Send, Sparkles, Trophy, WandSparkles, X } from 'lucide-react'
import { api, newKey } from './api'
import { ReferenceImages } from './ReferenceImages'
import { Brand, BrandWaves, Countdown, ErrorNotice, GamePreview, Guide, Modal, Rail } from './components'
import type { Generation, Session, Starter, Workspace } from './types'

const IDEAS = [
 {genre:'ARCADE',title:'A cosmic collecting quest',prompt:'Create a space arcade game where I pilot a spaceship, collect stars and dodge asteroids. Use arrow keys, a score and three lives.',icon:'✦',className:'cosmic'},
 {genre:'PLATFORMER',title:'One giant leap',prompt:'Make a colorful platformer about a tiny robot climbing floating islands. Add arrow key movement, Space to jump, and a portal to win.',icon:'⌁',className:'island'},
 {genre:'PUZZLE',title:'A bright little challenge',prompt:'Create a keyboard-controlled puzzle game with a grid of lights. Switch all the lights on to win. Include a simple tutorial.',icon:'▦',className:'puzzle'}
]
const FOLLOWUPS=['Make it a little easier','Add a score counter','Give it more colorful graphics','Add a new challenge']
type Pending={key:string;prompt:string;id?:string;referenceIds?:string[]}

export function Studio({session,logout}:{session:Session;logout:()=>void}){
 const [data,setData]=useState<Workspace|null>(null),[tab,setTab]=useState('studio'),[prompt,setPrompt]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[active,setActive]=useState<string|null>(null),[selected,setSelected]=useState<number|null>(null),[starters,setStarters]=useState<Starter[]>([]),[history,setHistory]=useState(false),[submit,setSubmit]=useState(false),[success,setSuccess]=useState(''),[recover,setRecover]=useState<Pending|null>(null)
 const [referenceBusy,setReferenceBusy]=useState(false)
 const promptRef=useRef<HTMLTextAreaElement>(null),chatEnd=useRef<HTMLDivElement>(null)
 const storageKey=`deepstem-pending-${session.team_id}`
 const load=useCallback(async()=>{const next=await api<Workspace>('/workspace');setData(next);setSelected(old=>old??next.team.current_version);setActive(old=>next.team.active_request??old);return next},[])
 useEffect(()=>{void load().catch(e=>setError(e.message));api<Starter[]>('/starters').then(setStarters).catch(e=>setError(e.message));try{const stored=sessionStorage.getItem(storageKey);if(stored){const p=JSON.parse(stored) as Pending;setRecover(p);if(p.id)setActive(p.id)}}catch{/* Browser storage is optional; server idempotency still applies. */}const id=setInterval(()=>{void load().catch(e=>setError(e.message))},10000);return()=>clearInterval(id)},[load,storageKey])
 useEffect(()=>{if(!active)return;let live=true,fetching=false;const poll=async()=>{if(fetching)return;fetching=true;try{const r=await api<Generation>(`/generations/${active}`);if(!live)return;if(r.status!=='running'){setActive(null);setBusy(false);setRecover(null);try{sessionStorage.removeItem(storageKey)}catch{}if(r.status==='success'){setSelected(r.version_id);setSuccess('Your new version is ready. Give it a play!')}else setError(r.error||'Generation did not finish. Your last working game is safe.');await load()}}catch(e){if(live)setError((e as Error).message)}finally{fetching=false}};void poll();const id=setInterval(poll,1200);return()=>{live=false;clearInterval(id)}},[active,load,storageKey])
 useEffect(()=>{if(!success)return;const id=setTimeout(()=>setSuccess(''),6000);return()=>clearTimeout(id)},[success])
 async function generate(pending?:Pending){const p=pending??recover??{key:newKey(),prompt:prompt.trim(),referenceIds:(data?.references??[]).map(r=>r.id)};if(!p.prompt)return;setBusy(true);setError('');setRecover(p);try{sessionStorage.setItem(storageKey,JSON.stringify(p))}catch{}try{const r=await api<Generation>('/generations','POST',{key:p.key,prompt:p.prompt,reference_ids:p.referenceIds});const saved={...p,id:r.id};try{sessionStorage.setItem(storageKey,JSON.stringify(saved))}catch{}setRecover(saved);setActive(r.id);setPrompt('');if(r.status!=='running'){if(r.status==='success'){setSelected(r.version_id);setSuccess('This request was already saved. Your version is ready.')}else setError(r.error);setActive(null);setBusy(false);setRecover(null);try{sessionStorage.removeItem(storageKey)}catch{}await load()}}catch(e){setError((e as Error).message);setBusy(false); // Keep the key after ambiguous network failure; retry sends exactly the same request.
   const status=(e as {status?:number}).status;if(status&&status<500&&status!==408){setRecover(null);try{sessionStorage.removeItem(storageKey)}catch{}}
 }}
 function chooseIdea(value:string){setPrompt(value);setTab('studio');setTimeout(()=>promptRef.current?.focus(),0)}
 async function starter(id:string){setBusy(true);setError('');try{const v=await api<{id:number}>(`/starters/${id}`,'POST');await load();setSelected(v.id);setTab('studio');setSuccess('Starter saved. Play it, download it, or ask AI to make it yours.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function restore(){try{await api(`/versions/${selected}/restore`,'POST');await load();setSuccess('Version restored. Your next prompt will build on this game.')}catch(e){setError((e as Error).message)}}
 if(!data)return <div className="app-loading"><Brand/><span className="spinner"/><p>Getting your workspace ready…</p><ErrorNotice message={error}/></div>
 const version=data.versions.find(v=>v.id===selected)
 const event=data.event
 const ended=event.frozen||event.phase==='ended'||(event.phase==='running'&&event.remaining_seconds<=0)
 const locked=ended||event.phase!=='running'
 const aiDisabled=locked||event.paused||event.emergency_mode||data.team.remaining<=0||busy||!!active||referenceBusy
 return <div className="app-shell studio-shell">
  <Rail session={session} tab={tab} setTab={setTab} logout={logout} onSubmission={()=>{setTab('studio');setTimeout(()=>document.querySelector('.submission-card')?.scrollIntoView({behavior:'smooth',block:'center'}),0)}}/>
  <div className="app-main">
   <header className="app-header"><div className="header-breadcrumb"><span>Deepstem Hub</span><ChevronRight size={18}/><strong>AI Game Jam Studio</strong></div><Countdown event={event}/><div className="team-chip"><span>{data.team.name.slice(0,2).toUpperCase()}</span><div><strong>{data.team.name}</strong><small>Team workspace</small></div></div></header>
   <main className="workspace-main" id="main-content">
    <div className="workspace-intro"><div><h1>{tab==='starters'?'A head start for your next idea.':tab==='guide'?'Let’s make something playable.':'Your ideas. Ready to play.'}</h1><p>{tab==='starters'?'Choose a playable starter, then make it your own.':'Describe a game. Play it. Make it yours.'}</p></div><div className="theme-card"><span className="theme-star"><Gamepad2 size={29}/></span><div><small>The jam theme</small><strong>{event.theme}</strong></div></div></div>
    {(event.announcement||event.emergency_mode)&&<div className="notice announcement"><Lightbulb size={22}/><span>{event.announcement||'AI is taking a break. Keep playing and downloading, or try a starter game.'}</span></div>}
    {event.demo_mode&&<div className="demo-strip"><span className="pill">Practice mode</span><span>You’re using offline starter games. Your organizer can connect AI for custom games and changes.</span></div>}
    {locked&&<div className="notice"><Clock3 size={22}/><span>{ended?'Building is finished. You can still play and download every saved game. Your final entry is locked.':'Waiting for the competition clock. Your organizer will start or resume building soon.'}</span></div>}
    <ErrorNotice message={error} dismiss={()=>setError('')}/>{success&&<div role="status" className="notice success"><Check size={22}/><span>{success}</span></div>}
    {tab==='guide'?<Guide/>:tab==='starters'?<div className="starter-grid">{starters.map((s,i)=><article className={`starter-card starter-${s.id}`} key={s.id}><div className="starter-art"><span>{['✦','⌁','▦','ϟ','❋'][i]}</span><div className="pixel-ground"/></div><div className="starter-body"><span className="eyebrow">{s.genre}</span><h2>{s.title}</h2><p>{s.description}</p><button className="secondary" disabled={locked||busy||!!active} onClick={()=>void starter(s.id)}>Start with this game<ArrowRight size={20}/></button><small>Uses no AI requests. Download and play offline.</small></div></article>)}</div>:<>
     <div className="studio-grid">
      <section className="assistant-panel" aria-labelledby="assistant-title">
       <div className="panel-heading"><div><span className="section-icon purple"><Sparkles size={22}/></span><h2 id="assistant-title">Your AI co-creator</h2></div></div>
       <div className="assistant-intro"><p>{data.versions.length?'Ready for the next idea? Ask for one change at a time.':'Start with a small idea. Tell me who’s playing, what they do, and how they win.'}</p></div>
       <div className="prompt-area">
        <form onSubmit={e=>{e.preventDefault();void generate()}}>
         <label className="composer-label" htmlFor="game-prompt">{data.versions.length?'What would you like to change?':'What game do you want to make?'}</label>
         <div className="prompt-box"><textarea id="game-prompt" ref={promptRef} aria-label="Describe your game or changes" aria-describedby="composer-help" placeholder={data.versions.length?'Try “Make the player jump higher” or “Add moving enemies”.':'A game where a tiny astronaut collects stars and dodges meteors. Use arrow keys to move and give me three lives.'} value={prompt} onChange={e=>setPrompt(e.target.value)} maxLength={3000} rows={6} disabled={!!active||busy}/><div className="prompt-box-footer"><span><Sparkles size={16}/> Your imagination goes here</span><span>{prompt.length} / 3000</span></div></div>
         <p id="composer-help" className="composer-help"><Lightbulb size={18}/>{data.versions.length?'Your next version builds on the restored or current game. Older versions stay saved.':'A clear goal and simple controls make a great first game.'}</p>
         <ReferenceImages references={data.references??[]} disabled={ended||busy||!!active||!!recover} onChange={load} onBusy={setReferenceBusy} onError={setError}/>
         {active&&<div className="generation-progress" role="status"><span className="spinner"/><div><strong>Building your world…</strong><p>This can take a minute or two. Your saved games are safe.</p></div></div>}
         <button className="primary generate-button" disabled={aiDisabled||prompt.trim().length<4}><Sparkles size={22}/>{active?'Creating your game…':data.versions.length?'Update game':'Generate game'}{!active&&<ArrowRight size={21}/>}</button>
        </form>
        {recover&&!active&&!busy&&<button className="secondary retry-button" onClick={()=>void generate(recover)}>Reconnect to your last request safely</button>}
        <div className="allowance-line"><span><strong>{data.team.remaining}</strong> requests left</span><span><Check size={17}/> Games save automatically</span></div>
        <div className="followups"><span>{data.versions.length?'Try a next step':'Need a starting point?'}</span>{(data.versions.length?FOLLOWUPS.slice(0,3):['A space arcade game','A jumping platformer','A puzzle with lights']).map((p,i)=><button key={p} onClick={()=>chooseIdea(data.versions.length?p:IDEAS[i].prompt)} disabled={aiDisabled}>{p}<ArrowRight size={16}/></button>)}</div>
       </div>
       {data.versions.length>0&&<details className="conversation-history" open><summary><History size={20}/>Conversation & saved games<span className="pill muted">{data.versions.length}</span></summary><div className="chat-scroll">{data.versions.slice().reverse().map(v=><div className="chat-pair" key={v.id}><div className="user-message"><div className="message-meta">Your team<span>{new Date(v.created*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</span></div><p>{v.prompt}</p></div><div className="assistant-message"><span className="mini-assistant"><Sparkles size={19}/></span><div><p>{v.explanation}</p><button className={'version-link '+(v.id===selected?'selected':'')} onClick={()=>setSelected(v.id)}><Gamepad2 size={19}/>{v.title}<span>v{v.number}</span><ArrowRight size={18}/></button></div></div></div>)}<div ref={chatEnd}/></div></details>}
      </section>
      <div className="preview-column">
       <GamePreview versionId={selected} versionNumber={version?.number} title={version?.title} onRestore={restore} current={selected===data.team.current_version} disabled={locked||!!active}/>
       <div className="version-bar"><button onClick={()=>setHistory(!history)} aria-expanded={history} className="text-button"><History size={20}/>Version history<span className="pill muted">{data.versions.length}</span><ChevronDown size={18}/></button><span>{version?`Viewing v${version.number} · ${version.title}`:'Every successful game gets a saved version.'}</span></div>
       {history&&<div className="history-list">{data.versions.length?data.versions.slice().reverse().map(v=><button key={v.id} onClick={()=>setSelected(v.id)} className={selected===v.id?'selected':''}><span className="version-number">v{v.number}</span><div><strong>{v.title}</strong><p>{v.prompt}</p><small>{new Date(v.created*1000).toLocaleString()}</small></div>{selected===v.id&&<Check size={20}/>}</button>):<p>Your first generated game will appear here. Previous versions always stay available.</p>}</div>}
       <section className="submission-card" tabIndex={-1}><div className="submission-icon"><Trophy size={27}/></div><div><h3>{data.submission?'Your game is in!':'Ready for the judges?'}</h3><p>{data.submission?`${data.submission.title} is submitted. ${ended?'Ready for the judges.':'You can update it before time runs out.'}`:'Choose your favorite version and submit before the clock runs out.'}</p></div><button className="primary" disabled={!selected||locked||busy||!!active} onClick={()=>setSubmit(true)}>{data.submission?'Update submission':'Submit game'}<ArrowUpIcon/></button></section>
      </div>
     </div>
     <footer className="studio-footer"><span><span className="live-dot"/> Your ideas are safely saved.</span><button className="text-button" onClick={()=>setTab('starters')}>Explore starter games<ArrowRight size={18}/></button><button className="text-button" onClick={()=>setTab('guide')}>Need a hand?</button></footer>
    </>}
   </main><BrandWaves/>
  </div>
  {submit&&selected&&<SubmitDialog versionId={selected} title={version?.title||'My game'} description={data.submission?.description||''} onClose={()=>setSubmit(false)} onDone={()=>{setSubmit(false);setSuccess('Submitted! Your game is ready for the judges.');void load()}}/>}
 </div>
}
function ArrowUpIcon(){return <Send size={14}/>}
function SubmitDialog({versionId,title,description,onClose,onDone}:{versionId:number;title:string;description:string;onClose:()=>void;onDone:()=>void}){
 const [name,setName]=useState(title),[desc,setDesc]=useState(description),[busy,setBusy]=useState(false),[error,setError]=useState('')
 return <Modal title="Give your game its big moment." onClose={onClose}><p className="muted-text">Submit the version you are previewing. You can update your entry until building ends.</p><form onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api('/submissions','POST',{version_id:versionId,title:name,description:desc});onDone()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}><label>Game title<input value={name} onChange={e=>setName(e.target.value)} required maxLength={100}/></label><label>What’s your game about?<textarea value={desc} onChange={e=>setDesc(e.target.value)} required minLength={5} maxLength={1000} rows={4} placeholder="Tell the judges what to do and why it’s fun."/></label><ErrorNotice message={error}/><button className="primary" disabled={busy}><Trophy size={16}/>{busy?'Submitting…':'Submit for judging'}</button></form></Modal>
}
