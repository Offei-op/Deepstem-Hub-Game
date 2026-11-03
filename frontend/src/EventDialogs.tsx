import { useEffect, useState } from 'react'
import { Archive, ArrowDownToLine, Gamepad2, Plus } from 'lucide-react'
import { api, money } from './api'
import { ErrorNotice, GamePreview, Modal } from './components'
import type { Config, Dashboard, Version } from './types'

export function NewEventDialog({config,running,onClose,onDone}:{config:Config;running:boolean;onClose:()=>void;onDone:()=>Promise<void>}){
 const [eventKey]=useState(config.event_key||'legacy')
 const [name,setName]=useState(''),[theme,setTheme]=useState(config.theme),[minutes,setMinutes]=useState(120)
 const [budget,setBudget]=useState(config.budget_micro/1e6),[allowance,setAllowance]=useState(config.initial_allowance)
 const [emergency,setEmergency]=useState(config.emergency_allowance),[teams,setTeams]=useState(config.max_teams)
 const [confirmation,setConfirmation]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
 return <Modal title="A fresh event. A new adventure." onClose={()=>{if(!busy)onClose()}}>
  <p className="event-dialog-intro">The current event will move to your read-only archive. Its games, submissions, prompts and spending remain available. Your AI connection and website addresses stay configured.</p>
  <div className="notice"><Archive size={22}/><span>Current team codes will stop working. Create new teams after this step. The new clock starts in “ready”, with building and submissions reopened.</span></div>
  <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await api('/admin/events','POST',{expected_event_key:eventKey,confirmation,name,theme,minutes,budget_micro:Math.round(budget*1e6),initial_allowance:allowance,emergency_allowance:emergency,max_teams:teams});await onDone()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>
   <label>New event name<input value={name} onChange={e=>setName(e.target.value)} minLength={2} maxLength={120} placeholder="For example: UMaT Game Jam — November" required autoFocus/></label>
   <label>Competition theme<input value={theme} onChange={e=>setTheme(e.target.value)} maxLength={120} required/></label>
   <div className="form-grid">
    <label>Building time (minutes)<input type="number" value={minutes} onChange={e=>setMinutes(+e.target.value)} min={1} max={480} required/></label>
    <label>Event spending ceiling (USD)<input type="number" value={budget} onChange={e=>setBudget(+e.target.value)} min={0} max={1000} step="0.01" required/></label>
    <label>Maximum teams<input type="number" value={teams} onChange={e=>setTeams(+e.target.value)} min={1} max={10} required/></label>
    <label>Requests per team<input type="number" value={allowance} onChange={e=>setAllowance(+e.target.value)} min={1} max={100} required/></label>
    <label>Emergency reserve per team<input type="number" value={emergency} onChange={e=>setEmergency(+e.target.value)} min={0} max={100} required/></label>
   </div>
   <p className="event-dialog-intro">The new spending ceiling applies to this event. Earlier provider charges remain on your API account.</p>
   <label>Type NEW EVENT to confirm<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="NEW EVENT" autoComplete="off" required pattern="NEW EVENT"/></label>
   {running&&<p role="status" className="notice">Wait for current game generations to finish before creating the event.</p>}
   <ErrorNotice message={error}/>
   <div className="event-dialog-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>Keep current event</button><button className="primary" disabled={busy||running||confirmation!=='NEW EVENT'}><Plus size={19}/>{busy?'Creating event…':'Archive current & create event'}</button></div>
  </form>
 </Modal>
}

type ArchiveSummary={id:number;name:string;theme:string;created:number;teams:number}
export function EventArchiveDialog({onClose}:{onClose:()=>void}){
 const [archives,setArchives]=useState<ArchiveSummary[]>([]),[selected,setSelected]=useState<number|null>(null)
 const [data,setData]=useState<Dashboard|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true)
 const [versions,setVersions]=useState<Version[]>([]),[version,setVersion]=useState<number|null>(null)
 useEffect(()=>{let live=true;api<ArchiveSummary[]>('/admin/events').then(rows=>{if(live){setArchives(rows);setSelected(rows[0]?.id??null)}}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},[])
 useEffect(()=>{if(selected===null)return;let live=true;setLoading(true);setData(null);setVersion(null);setVersions([]);api<Dashboard>(`/admin/events/${selected}`).then(row=>{if(live)setData(row)}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},[selected])
 async function inspect(teamId:number,current:number|null){try{setError('');const rows=await api<Version[]>(`/admin/teams/${teamId}/versions`);setVersions(rows);setVersion(current??rows.at(-1)?.id??null)}catch(e){setError((e as Error).message)}}
 return <Modal title="Your event archive" onClose={onClose}>
  <p className="event-dialog-intro">Past competitions stay read-only. Play or download saved games and export the complete event record.</p>
  <ErrorNotice message={error}/>
  {!archives.length&&!loading?<div className="archive-empty"><Archive size={32}/><h3>No archived events yet</h3><p>Your current event will appear here when you create a new one.</p></div>:<>
   <label>Choose an archived event<select value={selected??''} onChange={e=>setSelected(+e.target.value)}>{archives.map(row=><option key={row.id} value={row.id}>{row.name} · {new Date(row.created*1000).toLocaleDateString()}</option>)}</select></label>
   {loading&&<p role="status">Opening archive…</p>}
   {data&&<div className="archive-detail">
    <div className="archive-summary"><span className="pill muted">READ-ONLY ARCHIVE</span><h3>{data.event.name||'Game Jam'}</h3><p>Theme: {data.event.theme}</p><p>{data.metrics.teams} teams · {data.metrics.success} games generated · {money(data.metrics.spent_micro)} estimated spending</p><a className="secondary" href={`/api/admin/events/${selected}/export?role=admin`}><ArrowDownToLine size={18}/>Export this event</a></div>
    <h3>Teams & saved games</h3><div className="archive-teams">{data.teams.map(team=><article key={team.id}><div><strong>{team.name}</strong><p>{team.used} successful requests · {team.remaining} unused</p></div><button className="secondary" disabled={!team.current_version} onClick={()=>void inspect(team.id,team.current_version)}><Gamepad2 size={19}/>Inspect game</button></article>)}{!data.teams.length&&<p>No teams were registered for this event.</p>}</div>
    {versions.length>0&&<label>Saved game version<select value={version??''} onChange={e=>setVersion(+e.target.value)}>{versions.map(v=><option key={v.id} value={v.id}>v{v.number} · {v.title}</option>)}</select></label>}
    {version&&<GamePreview versionId={version} title={versions.find(v=>v.id===version)?.title}/>}
    <details className="usage-details"><summary>Final submissions ({data.submissions.length})</summary>{data.submissions.map(s=><article className="archived-submission" key={s.team_id}><h3>{s.title}</h3><p>{s.team_name} · {s.description}</p><button className="secondary" onClick={()=>{setVersions([]);setVersion(s.version_id)}}><Gamepad2 size={18}/>Play submitted game</button><a className="text-button" href={`/api/versions/${s.version_id}/download?role=admin`}>Download HTML</a></article>)}</details>
    <details className="usage-details"><summary>Prompt history & usage ({data.metrics.requests} requests)</summary>{data.requests.map(r=><article className="archive-request" key={r.id}><strong>{data.teams.find(t=>t.id===r.team_id)?.name} · {r.status} · {money(r.cost_micro)}</strong><p>{r.prompt}</p>{r.error&&<p>{r.error}</p>}</article>)}<p>Export this event for the complete provider, token and request ledger.</p></details>
   </div>}
  </>}
 </Modal>
}
