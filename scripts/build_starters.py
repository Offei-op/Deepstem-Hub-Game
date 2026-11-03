"""Rebuild the five bundled, network-free games. No dependencies required."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'backend/app/starters'
COMMON = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
*{box-sizing:border-box}body{margin:0;background:#090f1d;color:#eef3ff;font:15px system-ui,sans-serif;display:grid;place-items:center;min-height:100vh}main{width:min(100%,960px);padding:18px}header,footer{display:flex;justify-content:space-between;align-items:center;gap:16px}h1{font-size:20px;margin:0}p{color:#9eaccb;font-size:13px}canvas{display:block;width:100%;background:#101b31;border:1px solid #273552;border-radius:12px;max-height:75vh;object-fit:contain}button{border:1px solid #37666d;background:#153740;color:#98ffdf;padding:10px 20px;border-radius:8px;cursor:pointer}button:focus-visible{outline:3px solid #a99cff}#status{color:#8df0c9;font-weight:700}footer{font-size:12px;color:#9eaccb;padding-top:14px}
</style></head><body><main><header><div><h1>__TITLE__</h1><p>__OBJECTIVE__</p></div><button id="restart">↻ Restart</button></header>
<canvas id="game" width="960" height="600" tabindex="0" aria-label="__TITLE__ keyboard game"></canvas><footer><span>__CONTROLS__</span><span id="status">Ready</span></footer></main><script>
'use strict';
const canvas=document.getElementById('game'),ctx=canvas.getContext('2d'),statusEl=document.getElementById('status');
const W=960,H=600,keys={};let state,score,elapsed,last=0,dt=1;
const rand=(a,b)=>a+Math.random()*(b-a),clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
function rect(x,y,w,h,c){ctx.fillStyle=c;ctx.fillRect(x,y,w,h)}
function circle(x,y,r,c){ctx.fillStyle=c;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill()}
function label(t,x,y,size=20,color='#eff6ff'){ctx.font=`700 ${size}px system-ui`;ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(t,x,y)}
function backdrop(){rect(0,0,W,H,'#0c1528');ctx.strokeStyle='#18273d';ctx.lineWidth=1;for(let x=0;x<W;x+=48){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke()}for(let y=0;y<H;y+=48){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke()}for(let i=0;i<36;i++)circle((i*139+17)%W,(i*83+23)%H,1.3,'#3d5270')}
function finish(win){state=win?'won':'lost'}
function overlay(){if(state==='playing')return;rect(0,0,W,H,'#07101cdd');label(state==='won'?'YOU DID IT!':'ONE MORE TRY?',W/2,H/2-20,40,state==='won'?'#91f6cb':'#c5b5ff');label('Press R or Restart to play again',W/2,H/2+32,19)}
__GAME__
function restart(){state='playing';score=0;elapsed=0;for(const key in keys)delete keys[key];init();canvas.focus()}
document.getElementById('restart').addEventListener('click',restart);
window.addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight',' ','Enter'].includes(e.key))e.preventDefault();keys[e.key.toLowerCase()]=true;if(e.key.toLowerCase()==='r')restart();if(typeof onKey==='function'&&!e.repeat&&state==='playing')onKey(e.key)});
window.addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false});window.addEventListener('blur',()=>{for(const key in keys)delete keys[key]});
function loop(now){dt=Math.min((now-last)/16.667,2)||1;last=now;if(state==='playing'){elapsed+=dt/60;update()}backdrop();draw();overlay();statusEl.textContent=`${state==='playing'?'PLAYING':state==='won'?'COMPLETE':'GAME OVER'} · Score ${Math.floor(score)}`;requestAnimationFrame(loop)}
restart();requestAnimationFrame(loop);
</script></body></html>'''

GAMES = {
'arcade': ('Cosmic Collector', 'Collect 20 stardust orbs. Avoid the falling meteors. You have 3 shields.', '← → / A D move · R restart', '''
let player,stars,rocks,lives,spawn;
function init(){player={x:W/2,y:530};stars=[];rocks=[];lives=3;spawn=0}
function update(){player.x=clamp(player.x+((keys.arrowright||keys.d?1:0)-(keys.arrowleft||keys.a?1:0))*7*dt,24,W-24);spawn-=dt;if(spawn<=0){spawn=35;stars.push({x:rand(25,W-25),y:-20});if(Math.random()<0.8)rocks.push({x:rand(25,W-25),y:-45})}for(const s of stars){s.y+=(3+score/12)*dt;if(Math.hypot(s.x-player.x,s.y-player.y)<35){score++;s.y=700}}for(const r of rocks){r.y+=(4+score/10)*dt;if(Math.hypot(r.x-player.x,r.y-player.y)<31){lives--;r.y=700}}stars=stars.filter(s=>s.y<650);rocks=rocks.filter(r=>r.y<650);if(lives<=0)finish(false);if(score>=20)finish(true)}
function draw(){label('STARDUST '+score+' / 20',150,45,20,'#7cf2ce');label('SHIELDS '+'◆'.repeat(Math.max(0,lives)),800,45,18,'#baafff');stars.forEach(s=>{circle(s.x,s.y,15,'#255b58');circle(s.x,s.y,7,'#8df5c8')});rocks.forEach(r=>{circle(r.x,r.y,17,'#aa5d6d');circle(r.x-4,r.y-4,6,'#ed9c9c')});ctx.fillStyle='#a799ff';ctx.beginPath();ctx.moveTo(player.x,player.y-24);ctx.lineTo(player.x-23,player.y+20);ctx.lineTo(player.x,player.y+10);ctx.lineTo(player.x+23,player.y+20);ctx.closePath();ctx.fill();rect(player.x-5,player.y+20,10,12+Math.random()*10,'#7cf2ce')}
'''),
'runner': ('Neon Dash', 'Jump over barriers. Reach 1,000 points without a collision.', 'Space / ↑ jump · R restart', '''
let player,obstacles,cooldown,jumpHeld;
function init(){player={y:455,vy:0};obstacles=[];cooldown=80;jumpHeld=false}
function update(){const jumping=keys[' ']||keys.arrowup||keys.w;if(jumping&&!jumpHeld&&player.y>=455){player.vy=-13}jumpHeld=jumping;player.vy+=0.58*dt;player.y=Math.min(455,player.y+player.vy*dt);if(player.y===455)player.vy=0;score+=dt/3;cooldown-=dt;if(cooldown<=0){obstacles.push({x:1000,w:rand(26,42),h:rand(38,65)});cooldown=rand(75,110)}const speed=6+score/350;for(const o of obstacles){o.x-=speed*dt;if(o.x<160&&o.x+o.w>125&&player.y+30>490-o.h)finish(false)}obstacles=obstacles.filter(o=>o.x>-70);if(score>=1000)finish(true)}
function draw(){label('DISTANCE '+Math.floor(score)+' / 1000',W/2,65,24,'#84f2d0');rect(0,490,W,4,'#80e9cc');for(let i=0;i<24;i++)rect(((i*65-elapsed*180)%(W+100)+W+100)%(W+100),520,25,3,'#294952');obstacles.forEach(o=>{rect(o.x,490-o.h,o.w,o.h,'#e39b99');rect(o.x+5,496-o.h,o.w-10,6,'#ffd4b6')});rect(125,player.y,34,34,'#ad9aff');rect(149,player.y+7,6,6,'#161e33');rect(130,player.y+34,7,5,'#88f2d1');rect(148,player.y+34,7,5,'#88f2d1')}
'''),
'platformer': ('Skybound', 'Climb the floating islands and reach the glowing portal.', '← → / A D move · Space / ↑ jump · R restart', '''
let player,platforms,jumpHeld;
function init(){player={x:65,y:510,vy:0,ground:true};jumpHeld=false;platforms=[{x:0,y:550,w:220},{x:200,y:460,w:145},{x:380,y:370,w:150},{x:560,y:280,w:145},{x:750,y:190,w:180}]}
function update(){const oldY=player.y;player.x=clamp(player.x+((keys.arrowright||keys.d?1:0)-(keys.arrowleft||keys.a?1:0))*4.8*dt,0,W-26);const jump=keys[' ']||keys.arrowup||keys.w;if(jump&&!jumpHeld&&player.ground){player.vy=-13;player.ground=false}jumpHeld=jump;player.vy+=0.48*dt;player.y+=player.vy*dt;player.ground=false;for(const p of platforms){if(player.vy>=0&&player.x+26>p.x&&player.x<p.x+p.w&&oldY+30<=p.y+2&&player.y+30>=p.y){player.y=p.y-30;player.vy=0;player.ground=true}}score=Math.max(score,Math.floor((550-player.y)/4));if(player.y>H+40)finish(false);if(player.x>845&&player.y<191)finish(true)}
function draw(){label('FIND YOUR WAY UP',W/2,48,22,'#8ff2cf');platforms.forEach((p,i)=>{rect(p.x,p.y,p.w,18,'#2a4853');rect(p.x,p.y,p.w,5,'#82dec4');rect(p.x+8,p.y+18,p.w-16,13,'#182e3d')});circle(880,151,30,'#3e3569');circle(880,151,20,'#b4a2ff');circle(880,151,10,'#e5ddff');rect(player.x,player.y,26,30,'#c3adff');rect(player.x+17,player.y+7,5,5,'#162337')}
'''),
'puzzle': ('Light Circuit', 'Switch all 16 lights ON. A switch flips itself and its neighbors.', 'Arrow keys select · Space / Enter switch · Click tiles · R restart', '''
let board,cursor,moves;
function flip(i){const x=i%4,y=Math.floor(i/4);for(const [dx,dy]of [[0,0],[-1,0],[1,0],[0,-1],[0,1]]){const a=x+dx,b=y+dy;if(a>=0&&a<4&&b>=0&&b<4)board[b*4+a]=!board[b*4+a]}}
function init(){board=Array(16).fill(true);cursor=0;moves=0;[0,3,5,10,12].forEach(flip)}
function onKey(k){if(k==='ArrowRight')cursor=(cursor+1)%16;if(k==='ArrowLeft')cursor=(cursor+15)%16;if(k==='ArrowDown')cursor=(cursor+4)%16;if(k==='ArrowUp')cursor=(cursor+12)%16;if(k===' '||k==='Enter'){flip(cursor);moves++}}
canvas.addEventListener('click',e=>{if(state!=='playing')return;const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)*W/r.width,y=(e.clientY-r.top)*H/r.height;const a=Math.floor((x-280)/100),b=Math.floor((y-110)/100);if(a>=0&&a<4&&b>=0&&b<4){cursor=b*4+a;flip(cursor);moves++}});
function update(){score=board.filter(Boolean).length;if(score===16)finish(true)}
function draw(){label('LIGHTS '+score+' / 16    ·    MOVES '+moves,W/2,65,24,'#8df3cb');for(let i=0;i<16;i++){const x=280+(i%4)*100,y=110+Math.floor(i/4)*100;rect(x,y,90,90,board[i]?'#74ddbb':'#1e2c44');circle(x+45,y+45,15,board[i]?'#c4ffe9':'#38475f');if(i===cursor){ctx.strokeStyle='#c1b0ff';ctx.lineWidth=4;ctx.strokeRect(x-4,y-4,98,98)}}}
'''),
'topdown': ('Garden Guardian', 'Collect 12 glowing blooms. Stay away from the wandering shadows.', 'Arrow keys / WASD move · R restart', '''
let player,bloom,enemies,health,invincible;
function newBloom(){bloom={x:rand(50,910),y:rand(100,550)}}
function init(){player={x:480,y:300};newBloom();enemies=[{x:40,y:40},{x:900,y:550},{x:40,y:550}];health=3;invincible=0}
function update(){let dx=(keys.arrowright||keys.d?1:0)-(keys.arrowleft||keys.a?1:0),dy=(keys.arrowdown||keys.s?1:0)-(keys.arrowup||keys.w?1:0),len=Math.hypot(dx,dy)||1;player.x=clamp(player.x+dx/len*4.6*dt,18,942);player.y=clamp(player.y+dy/len*4.6*dt,80,582);if(Math.hypot(player.x-bloom.x,player.y-bloom.y)<30){score++;newBloom()}invincible-=dt;enemies.forEach((e,i)=>{const a=Math.atan2(player.y-e.y,player.x-e.x);e.x+=Math.cos(a)*(1.15+score/25)*dt;e.y+=Math.sin(a)*(1.15+score/25)*dt;if(invincible<=0&&Math.hypot(player.x-e.x,player.y-e.y)<28){health--;invincible=100}});if(health<=0)finish(false);if(score>=12)finish(true)}
function draw(){label('BLOOMS '+score+' / 12',150,44,22,'#8af4cc');label('HEALTH '+'◆'.repeat(Math.max(0,health)),800,44,18,'#bbabff');for(let i=0;i<6;i++)circle(bloom.x+Math.cos(i*Math.PI/3)*11,bloom.y+Math.sin(i*Math.PI/3)*11,9,'#e7bd85');circle(bloom.x,bloom.y,8,'#fff1ca');enemies.forEach(e=>{circle(e.x,e.y,20,'#754668');circle(e.x-6,e.y-3,3,'#e6a5c4');circle(e.x+6,e.y-3,3,'#e6a5c4')});if(invincible<=0||Math.floor(elapsed*12)%2===0){circle(player.x,player.y,17,'#90eac6');circle(player.x+5,player.y-4,4,'#173d37')}}
''')}

if __name__ == '__main__':
    ROOT.mkdir(parents=True, exist_ok=True)
    for slug, (title, objective, controls, js) in GAMES.items():
        html = COMMON.replace('__TITLE__', title).replace('__OBJECTIVE__', objective).replace('__CONTROLS__', controls).replace('__GAME__', js)
        (ROOT / f'{slug}.html').write_text(html, encoding='utf-8')
    print(f'Wrote {len(GAMES)} standalone starter games to {ROOT}')
