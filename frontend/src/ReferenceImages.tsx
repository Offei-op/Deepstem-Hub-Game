import { useRef, useState } from 'react'
import { ImagePlus, Trash2 } from 'lucide-react'
import { api } from './api'
import type { StyleReference } from './types'

export async function imageForUpload(file:File):Promise<string> {
 if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw new Error('Choose a JPEG, PNG or WebP image.')
 if(file.size>5_000_000)throw new Error('Choose an image smaller than 5 MB.')
 const url=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(new Error('This image could not be read.'));reader.onload=()=>resolve(String(reader.result));reader.readAsDataURL(file)})
  const image=new Image()
  image.src=url
  await image.decode().catch(()=>{throw new Error('This image could not be opened. Try another file.')})
  if(image.naturalWidth*image.naturalHeight>16_000_000)throw new Error('Choose an image up to 16 megapixels.')
  const ratio=Math.min(1,1024/Math.max(image.naturalWidth,image.naturalHeight))
  const canvas=document.createElement('canvas')
  canvas.width=Math.max(1,Math.round(image.naturalWidth*ratio));canvas.height=Math.max(1,Math.round(image.naturalHeight*ratio))
  const ctx=canvas.getContext('2d')
  if(!ctx)throw new Error('Image resizing is unavailable in this browser.')
  ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height)
  return canvas.toDataURL('image/jpeg',0.85).split(',')[1]
}

export function ReferenceImages({references,disabled,onChange,onBusy,onError}:{references:StyleReference[];disabled:boolean;onChange:()=>Promise<unknown>;onBusy:(busy:boolean)=>void;onError:(message:string)=>void}) {
 const [working,setWorking]=useState(false),[notice,setNotice]=useState('')
 const input=useRef<HTMLInputElement>(null)
 async function upload(files:FileList|null){
  if(!files?.length)return
  if(files.length+references.length>3){onError('Choose up to three reference images in total.');return}
  setWorking(true);onBusy(true);onError('');setNotice('Saving your style references…')
  try{for(const file of Array.from(files)){const base64=await imageForUpload(file);await api('/references','POST',{name:file.name.slice(0,100),base64})}setNotice('References saved. They will guide your next generation.')}
  catch(e){onError((e as Error).message);setNotice('')}
  finally{await onChange().catch(()=>{});setWorking(false);onBusy(false);if(input.current)input.current.value=''}
 }
 async function remove(reference:StyleReference){
  setWorking(true);onBusy(true);onError('')
  try{await api(`/references/${reference.id}`,'DELETE');await onChange();setNotice('Reference removed from future generations.')}
  catch(e){onError((e as Error).message)}finally{setWorking(false);onBusy(false)}
 }
 return <section className="style-references" aria-labelledby="style-references-title">
  <div className="reference-heading"><h3 id="style-references-title">Guide the visual style</h3><span>{references.length} / 3 images</span></div>
  <p id="reference-help">Add screenshots or artwork to guide the colours, shapes and mood. Optional—your team’s images stay saved for future edits.</p>
  {references.length>0&&<ul className="reference-grid">{references.map((reference,i)=><li key={reference.id}><img src={reference.url+'?role=team'} alt={`Style reference ${i+1}: ${reference.name}`}/><div><span title={reference.name}>{reference.name}</span><button type="button" className="icon-button" aria-label={`Remove reference ${reference.name}`} disabled={disabled||working} onClick={()=>void remove(reference)}><Trash2 size={18}/></button></div></li>)}</ul>}
  <input ref={input} id="style-image-files" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden disabled={disabled||working||references.length>=3} onChange={e=>void upload(e.target.files)}/>
  <button type="button" className="secondary reference-add" aria-describedby="reference-help" disabled={disabled||working||references.length>=3} onClick={()=>input.current?.click()}><ImagePlus size={20}/>{working?'Saving images…':references.length?'Add another image':'Add style references'}</button>
  <p className="reference-meta">JPEG, PNG or WebP · up to 5 MB each. Images are sent to the event’s AI provider when you generate.</p>
  <span className="reference-status" role="status">{notice}</span>
 </section>
}
