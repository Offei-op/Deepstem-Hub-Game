import { useEffect, useState } from 'react'
import { Check, KeyRound, ShieldCheck } from 'lucide-react'
import { api } from './api'
import { ErrorNotice, Modal } from './components'

type Provider = {configured:boolean;model:string;input_price:number|null;output_price:number|null}
type Providers = Record<'openai'|'gemini',Provider>

export function ProviderSetup({onClose,onSaved}:{onClose:()=>void;onSaved:()=>void}){
 const [providers,setProviders]=useState<Providers|null>(null),[provider,setProvider]=useState<'openai'|'gemini'>('openai')
 const [key,setKey]=useState(''),[model,setModel]=useState(''),[input,setInput]=useState(''),[output,setOutput]=useState('')
 const [primary,setPrimary]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false)
 useEffect(()=>{api<Providers>('/admin/providers').then(setProviders).catch(e=>setError(e.message))},[])
 useEffect(()=>{if(!providers)return;const p=providers[provider];setModel(p.model);setInput(p.input_price===null?'':String(p.input_price));setOutput(p.output_price===null?'':String(p.output_price));setKey('')},[provider,providers])
 return <Modal title="Connect your AI assistant" onClose={onClose} footer={<button className="primary" type="submit" form="provider-connection" disabled={busy||!providers}><KeyRound size={20}/>{busy?'Saving connection…':'Save AI connection'}</button>}>
  <p className="muted-text">Add the organizer’s API key here. Your team members never need keys or paid accounts.</p>
  <form id="provider-connection" className="provider-setup" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');setSaved(false);try{
   const r=await api<{providers:Providers}>('/admin/providers','POST',{provider,api_key:key||null,model,input_price:+input,output_price:+output,make_primary:primary})
   setProviders(r.providers);setKey('');setSaved(true);onSaved()
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>
   <label>AI provider<select value={provider} onChange={e=>setProvider(e.target.value as 'openai'|'gemini')}><option value="openai">OpenAI</option><option value="gemini">Google Gemini</option></select></label>
   <label>API key {providers?.[provider].configured&&<span className="field-status"><Check size={16}/>A key is already saved. Leave blank to keep it.</span>}<input type="password" value={key} onChange={e=>setKey(e.target.value)} required={!providers?.[provider].configured} minLength={10} maxLength={500} autoComplete="off" spellCheck={false} placeholder={providers?.[provider].configured?'Enter a replacement key (optional)':'Paste your organizer API key'}/></label>
   <label>Model ID<input value={model} onChange={e=>setModel(e.target.value)} required maxLength={100} placeholder="Exact model ID from your provider account"/><span className="field-help">Choose a model that supports structured JSON output and game code generation.</span></label>
   <fieldset className="pricing-fields"><legend>Model pricing · USD per million tokens</legend><p>Copy the current prices for this model. These let the studio reserve spending safely.</p><div className="form-grid"><label>Input price<input type="number" min="0" max="10000" step="any" value={input} onChange={e=>setInput(e.target.value)} required placeholder="USD / million"/></label><label>Output price<input type="number" min="0" max="10000" step="any" value={output} onChange={e=>setOutput(e.target.value)} required placeholder="USD / million"/></label></div></fieldset>
   <label className="checkbox-label"><input type="checkbox" checked={primary} onChange={e=>setPrimary(e.target.checked)}/>Use this provider for new games</label>
   <div className="connection-links"><a href={provider==='openai'?'https://platform.openai.com/api-keys':'https://aistudio.google.com/apikey'} target="_blank" rel="noreferrer">Get an API key ↗</a><a href={provider==='openai'?'https://developers.openai.com/api/docs/pricing':'https://ai.google.dev/gemini-api/docs/pricing'} target="_blank" rel="noreferrer">Check model pricing ↗</a></div>
   <ErrorNotice message={error}/>{saved&&<div className="notice success" role="status"><Check size={20}/><span>AI connection saved and ready. No paid request was made.</span></div>}
   <p className="private-note"><ShieldCheck size={18}/>Saved privately on the server. Keys are never sent back to the browser or to game previews.</p>
  </form>
 </Modal>
}
