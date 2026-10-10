"""Round 9: round 8 tech direction + live hero demo + fact-link signature + polish. Light and dark."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
import r7, r9
from r7 import ic, LOGO

OUT = "/home/user/job/docs/design/round9/"
os.makedirs(OUT + "shots", exist_ok=True)

FACTS = [
    ("F2", "Built checkout-funnel dashboards in SQL", "OneCard · 2024"),
    ("F7", "Owned reporting for 3 payment flows", "OneCard · 2024–25"),
    ("F4", "Ran 4 onboarding A/B tests, +9% activation", "OneCard · 2025"),
    ("F1", "SQL, Excel, Mixpanel", "Skills you listed"),
]

def demo():
    facts = "".join(f'<li class="fa" id="{k}" data-k="{k}"><span class="fk">{k}</span><span class="ft">{t}<small>{s}</small></span></li>' for k, t, s in FACTS)
    return f'''<div class="demo" id="demo" aria-label="Animated example: ApplyScout tailoring a resume and checking every line">
<div class="dbar"><span class="live"><i></i>Live example</span><span class="m9 dstat" data-s="0">matching…</span><span class="m9 dstat" data-s="1">match · fit 92 · 6 of 8 skills</span><span class="m9 dstat" data-s="2">tailoring · checking each line against your facts</span><span class="m9 dstat" data-s="9">ready · waiting for your approval</span><span class="m9 dstat" data-s="11">sent · receipt AS-24817</span></div>
<div class="dgrid">
<section class="pane facts"><header><span class="lab9">{ic("database",13)}Your facts</span><span class="m9 cnt">18 confirmed</span></header><ul>{facts}</ul>
<div class="ghost m9">+ 14 more · added by you</div></section>
<svg class="links" aria-hidden="true"></svg>
<section class="pane res"><header><div class="job"><span class="co" style="background:#2D6CDF">R</span><div><b>Product Analyst</b><span>Razorpay · Bengaluru · ₹14–18 LPA</span></div></div><span class="fitp m9"><b>92</b> fit</span></header>
<div class="rl" id="L1" data-f="F2 F7" data-s="2"><span class="st8">{ic("check",15)}</span><p>Built SQL dashboards tracking checkout drop-off across 3 payment flows.</p><span class="tags"><span class="fact">F2</span><span class="fact">F7</span></span></div>
<div class="rl" id="L2" data-f="F4" data-s="4"><span class="st8">{ic("check",15)}</span><p>Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.</p><span class="tags"><span class="fact">F4</span></span></div>
<div class="rl bad" id="L3" data-f="" data-s="6"><span class="st8">{ic("x",15)}</span><p>Led a team of 6 analysts.</p><span class="tags"><span class="why">no matching fact · removed</span></span></div>
<div class="rl" id="L4" data-f="F1" data-s="8"><span class="st8">{ic("check",15)}</span><p>Skills: SQL · A/B testing · Payments analytics</p><span class="tags"><span class="fact">F1</span></span></div>
<footer><span class="sum m9"><b>4 of 4</b> lines backed · <span class="rm">1 removed</span></span><button class="btn pri sm ap" tabindex="-1">Approve &amp; send <span class="kbd">⏎</span></button></footer>
<div class="toast">{ic("circle-check",16)}<div><b>Sent from your Gmail</b><span class="m9">receipt AS-24817 · 09:42</span></div></div>
</section></div></div>'''

CSS10 = r"""
/* polish */
html,body{overflow-x:clip}
.h9{padding:104px 48px 0}
.h9 h1{font-size:clamp(40px,6vw,76px);letter-spacing:-.052em;margin:22px auto 22px}
.h9 .lede{font-size:18px;line-height:1.55;max-width:33em}
.sh9{padding:104px 48px 48px}
.sh9 h2{font-size:clamp(30px,3.4vw,44px)}
.n9 b{font-size:36px}
/* demo stage */
.stagewrap{position:relative;margin:64px 0 0;padding:0 40px 56px}
.stagewrap::before{content:"";position:absolute;left:8%;right:8%;top:20px;height:440px;background:radial-gradient(ellipse 45% 60% at 30% 50%,var(--glow1),transparent 70%),radial-gradient(ellipse 40% 55% at 72% 45%,var(--glow2),transparent 70%);filter:blur(40px);pointer-events:none}
.demo{position:relative;border:1px solid var(--line2);border-radius:14px;background:var(--surf);text-align:left;box-shadow:0 30px 80px -40px rgba(0,0,0,.35);overflow:hidden}
.dbar{display:flex;align-items:center;gap:14px;height:44px;padding:0 16px;border-bottom:1px solid var(--line);background:var(--sunk)}
.live{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:500;color:var(--ink)}
.live i{width:7px;height:7px;border-radius:9px;background:var(--err);animation:pulse 1.6s infinite}
@keyframes pulse{50%{opacity:.35}}
.dstat{font-size:12px;color:var(--ink3);display:none}
.dgrid{position:relative;display:grid;grid-template-columns:330px 1fr;gap:120px;padding:28px;align-items:start}
.pane{border:1px solid var(--line2);border-radius:12px;background:var(--bg);position:relative;z-index:1}
.dark .pane{background:#050505}
.pane header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--line)}
.pane .cnt{font-size:11.5px;color:var(--ink3)}
.facts ul{list-style:none;margin:0;padding:8px;display:grid;gap:6px}
.fa{display:grid;grid-template-columns:34px 1fr;gap:10px;align-items:center;padding:10px;border-radius:9px;border:1px solid transparent;transition:border-color .3s,background-color .3s}
.fa .fk{font:500 11.5px 'Geist Mono';height:24px;border-radius:6px;display:grid;place-items:center;background:var(--sunk);color:var(--ink2);border:1px solid var(--line2);transition:all .3s}
.fa .ft{font-size:13px;line-height:1.35;color:var(--ink)}
.fa .ft small{display:block;font-size:11.5px;color:var(--ink3);margin-top:2px}
.fa.hit{border-color:color-mix(in srgb,var(--ok) 45%,var(--line2));background:color-mix(in srgb,var(--ok) 7%,transparent)}
.fa.hit .fk{background:var(--ok);color:var(--bg);border-color:var(--ok)}
.facts.scan .fa{border-color:color-mix(in srgb,var(--err) 30%,transparent)}
.ghost{padding:4px 18px 14px;font-size:11.5px;color:var(--ink3)}
.res .job{display:flex;align-items:center;gap:10px}
.res .job .co{width:30px;height:30px;font-size:13px}
.res .job b{display:block;font-size:14px;font-weight:600}.res .job>div>span{font-size:12px;color:var(--ink3)}
.fitp{font-size:12px;color:var(--ink3);border:1px solid var(--line2);border-radius:6px;padding:3px 8px;opacity:0;transition:opacity .4s}
.fitp b{color:var(--ink);font-weight:500}
.rl{display:grid;grid-template-columns:22px 1fr auto;gap:10px;align-items:start;padding:14px 16px;border-bottom:1px solid var(--line);opacity:0;transform:translateY(6px);transition:opacity .45s,transform .45s}
.rl p{margin:0;font-size:14px;line-height:1.45;color:var(--ink);clip-path:inset(0 100% 0 0);transition:clip-path .9s steps(28)}
.rl .st8{width:22px;height:22px;border-radius:99px;display:grid;place-items:center;border:1px dashed var(--line2);color:transparent;transition:all .3s}
.rl .tags{display:flex;gap:4px;opacity:0;transition:opacity .3s}
.rl .why{font:11.5px 'Geist Mono';color:var(--err)}
.rl.in{opacity:1;transform:none}.rl.in p{clip-path:inset(0 0 0 0)}
.rl.ok .st8{background:var(--ok);border:1px solid var(--ok);color:var(--bg)}
.rl.ok .tags{opacity:1}
.rl.no .st8{background:var(--err);border:1px solid var(--err);color:#fff}
.rl.no p{color:var(--ink3);text-decoration:line-through;text-decoration-color:var(--err)}
.rl.no .tags{opacity:1}
.rl.no{background:var(--errsoft)}
.res footer{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;opacity:.35;transition:opacity .4s}
.res footer.on{opacity:1}
.sum{font-size:12px;color:var(--ink3)}.sum b{color:var(--ok);font-weight:500}.sum .rm{color:var(--err)}
.ap{transition:transform .15s,box-shadow .3s}
.ap.press{transform:scale(.94);box-shadow:0 0 0 4px color-mix(in srgb,var(--ink) 18%,transparent)}
.toast{position:absolute;right:16px;bottom:16px;display:flex;gap:10px;align-items:center;padding:12px 14px;border-radius:10px;background:var(--ink);color:var(--bg);font-size:13px;box-shadow:0 20px 40px -20px rgba(0,0,0,.5);opacity:0;transform:translateY(12px);transition:all .4s;z-index:3}
.toast b{display:block;font-weight:600}.toast span{font-size:11.5px;opacity:.7}
.toast svg{color:var(--ok)}
.toast.on{opacity:1;transform:none}
svg.links{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2;overflow:visible}
svg.links path{fill:none;stroke-width:1.5}
svg.links .ln{stroke:var(--ok)}
svg.links .sc{stroke:var(--err);stroke-dasharray:3 4}
svg.links circle{fill:var(--ok)}
@media (prefers-reduced-motion:reduce){.rl,.rl p,.toast,.fitp,.res footer{transition:none!important}.live i{animation:none}}
/* signature used elsewhere */
.sig{display:grid;grid-template-columns:.8fr 110px 1.4fr;align-items:stretch;margin-top:auto;position:relative}
.sig .fl{display:grid;gap:14px;align-content:start;padding-top:6px}
.sig .fl span{font:500 11.5px 'Geist Mono';padding:6px 8px;border:1px solid var(--line2);border-radius:6px;color:var(--ink2);background:var(--bg)}
.sig .fl span b{color:var(--ok);font-weight:500;margin-right:6px}
.sig .rl{opacity:1;transform:none;padding:9px 12px;border:1px solid var(--line2);border-radius:8px;margin-bottom:8px;background:var(--bg);grid-template-columns:20px 1fr}
.sig .rl p{clip-path:none;font-size:13px}
.sig .rl .st8{width:20px;height:20px}
.sig>svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
.sig>svg path{fill:none;stroke:var(--ok);stroke-width:1.5}
.sig>svg circle{fill:var(--ok)}
@media (max-width:760px){
 .h9{padding:56px 16px 0}.sh9{padding:64px 16px 28px}
 .stagewrap{padding:0 0 40px;margin-top:40px}
 .demo{border-radius:14px}
 .dbar{padding:0 12px}
 .dgrid{grid-template-columns:1fr;gap:14px;padding:14px}
 svg.links{display:none}
 .rl .why{white-space:normal}
 .facts ul{grid-template-columns:1fr 1fr}
 .fa{grid-template-columns:1fr;gap:6px;padding:8px}
 .fa .fk{width:34px}
 .rl .tags{justify-content:flex-start}
 .fa .ft{font-size:12px}.fa .ft small{display:none}
 .ghost{display:none}
 .rl{padding:12px}
 .rl .tags{grid-column:2;grid-row:2}
 .toast{left:12px;right:12px;bottom:12px}
 .res footer{gap:10px}
 .sig{grid-template-columns:1fr;gap:28px}
 .sig .fl{grid-auto-flow:column;grid-template-columns:repeat(3,1fr)}
}
"""

JS = r"""
document.fonts.ready.then(()=>{
(function(){
const root=document.getElementById('demo');if(!root)return;
const svg=root.querySelector('svg.links'),grid=root.querySelector('.dgrid');
const NS='http://www.w3.org/2000/svg';
function pt(el,side){const g=grid.getBoundingClientRect(),r=el.getBoundingClientRect();
 if(side==='r')return[r.right-g.left,r.top+r.height/2-g.top];if(side==='l')return[r.left-g.left,r.top+r.height/2-g.top];
 if(side==='b')return[r.left+r.width/2-g.left,r.bottom-g.top];return[r.left+r.width/2-g.left,r.top-g.top];}
function curve(a,b){const vertical=Math.abs(b[1]-a[1])>Math.abs(b[0]-a[0]);
 if(vertical){const my=(a[1]+b[1])/2;return`M${a[0]},${a[1]} C${a[0]},${my} ${b[0]},${my} ${b[0]},${b[1]}`}
 const mx=(a[0]+b[0])/2;return`M${a[0]},${a[1]} C${mx},${a[1]} ${mx},${b[1]} ${b[0]},${b[1]}`}
function ends(fact,line){const f=fact.getBoundingClientRect(),l=line.getBoundingClientRect();
 if(f.right<l.left)return[pt(fact,'r'),pt(line,'l')];return[pt(fact,'b'),pt(line,'t')];}
function draw(fid,lid,cls,animate){const f=document.getElementById(fid),l=document.getElementById(lid);if(!f||!l)return;
 const [a,b]=ends(f,l);const p=document.createElementNS(NS,'path');p.setAttribute('d',curve(a,b));p.setAttribute('class',cls);p.dataset.f=fid;p.dataset.l=lid;svg.appendChild(p);
 if(cls==='ln'){for(const q of [a,b]){const c=document.createElementNS(NS,'circle');c.setAttribute('cx',q[0]);c.setAttribute('cy',q[1]);c.setAttribute('r',2.5);c.dataset.f=fid;c.dataset.l=lid;svg.appendChild(c)}}
 if(animate){const L=p.getTotalLength();p.style.strokeDasharray=cls==='ln'?L:'3 4';if(cls==='ln'){p.style.strokeDashoffset=L;p.getBoundingClientRect();p.style.transition='stroke-dashoffset .8s ease';p.style.strokeDashoffset=0;}}}
function redraw(){const keep=[...svg.querySelectorAll('path')].map(p=>[p.dataset.f,p.dataset.l,p.getAttribute('class')]);svg.innerHTML='';keep.forEach(k=>draw(k[0],k[1],k[2],false));}
const lines=[...root.querySelectorAll('.rl')];
const S=[
 s=>{svg.innerHTML='';lines.forEach(l=>l.className='rl'+(l.id==='L3'?' bad':''));root.querySelectorAll('.fa').forEach(f=>f.classList.remove('hit'));root.querySelector('.facts').classList.remove('scan');root.querySelector('.fitp').style.opacity=0;root.querySelector('.res footer').classList.remove('on');root.querySelector('.toast').classList.remove('on');root.querySelector('.ap').classList.remove('press')},
 s=>{root.querySelector('.fitp').style.opacity=1},
 s=>{L('L1').classList.add('in')},
 s=>{L('L1').classList.add('ok');hit('F2');hit('F7');draw('F2','L1','ln',s.anim);draw('F7','L1','ln',s.anim)},
 s=>{L('L2').classList.add('in')},
 s=>{L('L2').classList.add('ok');hit('F4');draw('F4','L2','ln',s.anim)},
 s=>{L('L3').classList.add('in')},
 s=>{root.querySelector('.facts').classList.add('scan');['F1','F2','F4','F7'].forEach(f=>draw(f,'L3','sc',s.anim))},
 s=>{root.querySelector('.facts').classList.remove('scan');svg.querySelectorAll('.sc').forEach(p=>p.remove());L('L3').classList.add('no');L('L4').classList.add('in')},
 s=>{L('L4').classList.add('ok');hit('F1');draw('F1','L4','ln',s.anim);root.querySelector('.res footer').classList.add('on')},
 s=>{root.querySelector('.ap').classList.add('press')},
 s=>{root.querySelector('.ap').classList.remove('press');root.querySelector('.toast').classList.add('on')},
];
const STAT=[0,1,2,2,2,2,2,2,2,9,9,11];
function L(id){return document.getElementById(id)}function hit(id){L(id).classList.add('hit')}
function status(i){root.querySelectorAll('.dstat').forEach(e=>e.style.display=(+e.dataset.s===STAT[i])?'inline':'none')}
function goTo(n,anim){S[0]({});for(let i=1;i<=n;i++)S[i]({anim:anim&&i===n});status(n)}
window.__step=n=>{root.querySelectorAll('*').forEach(e=>e.style.transition='none');goTo(n,false)};
const q=new URLSearchParams(location.search);
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
if(q.has('step')){window.__step(+q.get('step'));return}
if(reduce){goTo(S.length-1,false);return}
const T=[900,900,1000,1000,900,1000,1000,1200,900,1100,500,2800];
let i=0;function tick(){if(i===0){S[0]({});status(0)}else{S[i]({anim:true});status(i)}const d=T[i];i=(i+1)%S.length;setTimeout(tick,d)}
tick();addEventListener('resize',redraw);
})();
// static signature diagrams
document.querySelectorAll('.sig').forEach(sig=>{const svg=sig.querySelector(':scope>svg');const g=sig.getBoundingClientRect();
 sig.querySelectorAll('[data-to]').forEach(f=>{f.dataset.to.split(' ').forEach(id=>{const t=sig.querySelector('#'+id);if(!t)return;const a=f.getBoundingClientRect(),b=t.getBoundingClientRect();
  let p1,p2,d;if(a.right<b.left){p1=[a.right-g.left,a.top+a.height/2-g.top];p2=[b.left-g.left,b.top+b.height/2-g.top];const mx=(p1[0]+p2[0])/2;d=`M${p1} C${mx},${p1[1]} ${mx},${p2[1]} ${p2}`}
  else{p1=[a.left+a.width/2-g.left,a.bottom-g.top];p2=[b.left+20-g.left,b.top-g.top];const my=(p1[1]+p2[1])/2;d=`M${p1} C${p1[0]},${my} ${p2[0]},${my} ${p2}`}
  const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',d);svg.appendChild(p);
  for(const q of [p1,p2]){const c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',q[0]);c.setAttribute('cy',q[1]);c.setAttribute('r',2.5);svg.appendChild(c)}})})});
});
"""

SIG = f'''<div class="sig"><div class="fl"><span id="sa" data-to="s1"><b>F2</b>SQL dashboards</span><span id="sb" data-to="s1 s2"><b>F7</b>3 payment flows</span><span id="sc" data-to="s2"><b>F4</b>4 A/B tests</span></div><span></span>
<div><div class="rl ok" id="s1"><span class="st8">{ic("check",13)}</span><p>Built SQL dashboards tracking checkout drop-off across 3 payment flows.</p></div>
<div class="rl ok" id="s2"><span class="st8">{ic("check",13)}</span><p>Owned reporting for 3 payment flows; ran 4 A/B tests.</p></div>
<div class="rl no" id="s3" style="margin-bottom:0"><span class="st8">{ic("x",13)}</span><p>Led a team of 6 analysts.</p></div></div><svg aria-hidden="true"></svg></div>'''

def body():
    b = r9.body()
    # hero: replace product frame + phone with the live demo
    s = b.index('<div class="prod">'); e = b.rindex('</section>', 0, b.index('<div class="hr" style="position:relative">'))
    b = b[:s] + f'<div class="stagewrap">{demo()}</div>' + b[e:]
    # copy polish
    b = b.replace('Truth check is live for every resume line', 'New: every resume line linked to a fact')
    b = b.replace('ApplyScout finds roles that fit, tailors your resume using only facts you\'ve confirmed, and sends nothing until you approve.',
                  'ApplyScout finds jobs that fit, rewrites your resume for each one using only facts you\'ve confirmed, and sends nothing until you approve.')
    # bento truth-check cell: use the signature diagram
    s = b.index('<div class="card9" style="margin-top:auto">'); e = b.index('</div></div></div>', s) + len('</div></div>')
    b = b[:s] + SIG + b[e:]
    return b

def page(theme, p):
    html = r9.page(theme, p).replace(r9.body(), body())
    html = html.replace("</style>", CSS10 + "</style>", 1).replace("</body>", f"<script>{JS}</script></body>")
    return html.replace("tech direction", "round 9")

if __name__ == "__main__":
    for t, p in (("dark", r9.DARK), ("light", r9.LIGHT)):
        h = page(t, p).replace("../round7/fonts/", "../round7/fonts/")
        open(OUT + f"landing-{t}.html", "w").write(h)
    print("ok")
