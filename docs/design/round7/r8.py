"""Round 8: landing v2. Combines the user's three references with round 7 (ink + marigold, Inter)."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-job/a6175851-a246-55a6-a0a4-ee0f36f9b543/scratchpad/r7")
import r7
from r7 import ic, LOGO, P, page, app_window, co, R

p = dict(P["marigold"])

CSS8 = r"""
html,body{overflow-x:clip}
.top .wrap,.wrap{max-width:1240px}
.h8{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:48px;align-items:center;padding-top:72px}
.h8 h1{font-size:clamp(42px,4.1vw,60px);line-height:.98;letter-spacing:-.05em;font-weight:640;margin:22px 0 24px}
.h8 h1 span{display:block;white-space:nowrap}
.h8 h1 .mu{color:var(--ink3)}
.h8 .lede{text-align:left;margin:0 0 30px;max-width:30em}
.h8 .ctas{justify-content:flex-start}
.h8 .fine{justify-content:flex-start}
.eyb{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3)}
.shot{position:relative;height:620px}
.shot .panel{position:absolute;inset:0 -200px 0 0;background:var(--stage);border-radius:22px}
.shot .frame{position:absolute;top:48px;left:40px;width:1060px;transform-origin:top left;transform:scale(.78)}
.shot .tag8{position:absolute;z-index:2;background:var(--surf);border:1px solid var(--line2);border-radius:10px;padding:10px 12px;font-size:13px;box-shadow:0 12px 30px -12px rgba(0,0,0,.3);display:flex;gap:8px;align-items:center}
.clip{overflow:hidden}
.src8{display:flex;align-items:center;gap:40px;padding:28px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-top:0}
.src8 .eyb{flex:none}
.src8 .srcs{justify-content:space-between;flex:1;gap:24px}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin-top:48px;border-top:1px solid var(--line)}
.step{padding:28px 28px 0 0}
.step .ico{width:44px;height:44px;border-radius:11px;border:1px solid var(--line2);background:var(--surf);display:grid;place-items:center;margin-bottom:18px;box-shadow:0 1px 0 var(--line)}
.step h4{font-size:17px;letter-spacing:-.02em;margin:0 0 6px;font-weight:600;display:flex;gap:8px;align-items:baseline}
.step h4 small{font-size:12px;color:var(--ink3);font-weight:500}
.step p{margin:0;color:var(--ink2);font-size:14.5px;max-width:24ch}
.ba{display:grid;grid-template-columns:1fr 56px 1fr;align-items:center;margin-top:48px}
.doc{background:var(--surf);border:1px solid var(--line2);border-radius:14px;padding:22px 24px;box-shadow:0 20px 50px -30px rgba(20,16,10,.35);font-size:13.5px;height:100%}
.doc .dh8{display:flex;align-items:center;justify-content:space-between;padding-bottom:14px;border-bottom:1px solid var(--line);margin-bottom:14px;font-weight:600}
.doc .k{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);font-weight:600;margin:4px 0 8px}
.doc .role{font-weight:600}.doc .org{color:var(--ink3);margin-bottom:10px}
.doc ul{margin:0;padding:0;list-style:none;display:grid;gap:8px}
.doc li{display:grid;grid-template-columns:16px 1fr;gap:8px;line-height:1.45;color:var(--ink2)}
.doc li .b{width:5px;height:5px;border-radius:9px;background:var(--ink3);margin-top:8px}
.doc.after li{color:var(--ink)}
.doc li .ev{display:flex;gap:6px;margin-top:4px;font-size:11.5px;color:var(--ink3);align-items:center}
.doc li.cut{color:var(--ink3)}
.doc li.cut .x{text-decoration:line-through;text-decoration-color:var(--err)}
.arrow{width:44px;height:44px;border-radius:99px;background:var(--ink);color:var(--onpri);display:grid;place-items:center;margin:0 auto}
.aud{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:48px}
.au{border:1px solid var(--line);background:var(--surf);border-radius:14px;padding:24px;display:flex;flex-direction:column;gap:8px}
.au .ico{width:40px;height:40px;border-radius:10px;background:var(--soft);color:var(--softtx);display:grid;place-items:center}
.au h4{margin:10px 0 0;font-size:17px;letter-spacing:-.02em;font-weight:600}
.au p{margin:0;color:var(--ink2);font-size:14.5px}
.au .eg{margin-top:auto;padding-top:14px;border-top:1px dashed var(--line2);font-size:13px;color:var(--ink3)}
.cta8{margin-top:120px;background:var(--stage);color:var(--ink);padding:96px 0;}
.cta8 h2{font-size:clamp(40px,5vw,68px);line-height:1;letter-spacing:-.05em;font-weight:640;margin:0 0 28px;max-width:14ch}
.cta8 .btn.sec{background:transparent;border-color:rgba(22,19,14,.35)}
.cta8 .fine{justify-content:flex-start;color:#4A3A12}
.cta8 .wrap{display:grid;grid-template-columns:1.2fr 1fr;align-items:end;gap:40px}
.cta8 .mini8{background:var(--surf);border-radius:14px;padding:18px;box-shadow:0 30px 60px -30px rgba(0,0,0,.45);font-size:13.5px}
.mini8 .r{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}
.mini8 .r:last-child{border-bottom:0}
.mini8 .t{flex:1;font-weight:550}
.band{margin-top:120px}
footer{margin-top:0}
@media (max-width:700px){
 .wrap{padding:0 16px}
 .top nav,.top .r .gh{display:none}
 .h8{grid-template-columns:1fr;gap:32px;padding-top:32px}
 .h8 h1{font-size:40px}
 .h8 h1 span{white-space:normal}
 .h8 .lede{font-size:17px}
 .h8 .ctas .btn{flex:1;justify-content:center}
 .shot{height:430px}
 .shot .panel{inset:0 -16px 0 0;border-radius:18px 0 0 18px}
 .shot .frame{left:16px;top:20px;transform:scale(.5)}
 .shot .tag8{display:none}
 .src8{flex-direction:column;align-items:flex-start;gap:14px}
 .src8 .srcs{flex-wrap:wrap;gap:10px 22px;font-size:15px;justify-content:flex-start}
 .sect{padding-top:80px}
 .steps{grid-template-columns:1fr 1fr;gap:0 16px}
 .step{padding:22px 0 0}
 .ba{grid-template-columns:1fr;gap:14px}
 .ba .arrow{transform:rotate(90deg)}
 .ba .doc.before{display:none}
 .ba .arrow{display:none}
 .aud{grid-template-columns:1fr}
 .split{grid-template-columns:1fr!important;gap:32px!important}
 .band{padding:72px 0;margin-top:80px}
 .price{grid-template-columns:1fr}
 .cta8 .wrap{grid-template-columns:1fr}
 .cta8{padding:64px 0;margin-top:80px}
 footer .wrap{flex-direction:column}
 footer .cols{margin-left:0;gap:40px;flex-wrap:wrap}
 .receipt .kv{grid-template-columns:96px 1fr}
}
"""

def landing8():
    L = r7.landing(p)
    # Reuse round 7's trust band, pricing and footer; replace hero, sources and how-it-works.
    band = L[L.index('<section class="band'):L.index('</section>', L.index('<section class="band')) + 10]
    price_start = L.index('<section class="sect"><div class="wrap"><div class="eyebrow">' + ic("indian-rupee", 15))
    price = L[price_start:L.index("</main>")]
    footer = L[L.index("<footer>"):]
    header = L[:L.index("<main")]
    header = header.replace('<a href="#">How it works</a><a href="#">Pricing</a><a href="#">For colleges</a>', '<a href="#">How it works</a><a href="#">Why it\'s safe</a><a href="#">Pricing</a><a href="#">For colleges</a>')
    header = header.replace('<a class="btn pri sm" href="#">Start free</a>', f'<a class="btn pri sm" href="#">Upload resume {ic("arrow-right",14)}</a>')

    hero = f'''<main id="m"><section><div class="wrap h8" data-shot="hero"><div>
<span class="pill"><b>New</b>Truth check on every resume line {ic("arrow-right",13)}</span>
<h1><span>Find the right jobs.</span><span>Tailor every resume.</span><span class="mu">Never send a false line.</span></h1>
<p class="lede">Maggie finds roles that fit you, rewrites your resume for each one using only facts you've confirmed, and waits for your OK before anything is sent.</p>
<div class="ctas"><a class="btn pri lg" href="#">{ic("upload",16)}Upload your resume</a><a class="btn sec lg" href="#">Try with a sample</a></div>
<div class="fine"><span>{ic("check",14)}10 free applications</span><span>{ic("check",14)}No card</span><span>{ic("check",14)}Works on your phone</span></div></div>
<div class="shot"><div class="panel"></div><div class="frame">{app_window()}</div>
<div class="tag8" style="left:-28px;top:360px">{ic("shield-check",16)}<span><b style="font-weight:600">14 of 14 lines</b> backed by your facts</span></div>
<div class="tag8" style="right:24px;bottom:28px">{ic("lock",15)}<span>Nothing is sent until you tap <b style="font-weight:600">Approve</b></span></div></div></div></section>
<section style="margin-top:72px"><div class="wrap"><div class="src8"><span class="eyb">Finds roles on</span><div class="srcs"><span>Greenhouse</span><span>Lever</span><span>Workday</span><span>Ashby</span><span>Company career pages</span><span>LinkedIn hiring posts</span></div></div></div></section>'''

    steps = f'''<section class="sect"><div class="wrap"><div class="eyb">How it works</div><h2 class="h" style="margin-top:14px">From job post to sent application. <em>You approve every step.</em></h2>
<div class="steps">
<div class="step"><div class="ico">{ic("search",20)}</div><h4><small>01</small>Find</h4><p>Roles from 6 sources, ranked by how well your real experience fits.</p></div>
<div class="step"><div class="ico">{ic("file-pen-line",20)}</div><h4><small>02</small>Tailor</h4><p>Your resume rewritten for each job, every line linked to a fact.</p></div>
<div class="step"><div class="ico">{ic("circle-check-big",20)}</div><h4><small>03</small>Approve</h4><p>See exactly what will be sent. One tap to send, or edit first.</p></div>
<div class="step"><div class="ico">{ic("chart-no-axes-column",20)}</div><h4><small>04</small>Track</h4><p>Receipts, replies and follow-up reminders in one list.</p></div>
</div></div></section>'''

    ba = f'''<section class="sect"><div class="wrap"><div class="split" style="grid-template-columns:.8fr 1.2fr;gap:56px;align-items:start">
<div><div class="eyb">Tailoring you can trust</div><h2 class="h" style="margin-top:14px">Tailored for the job. <em>True to you.</em></h2>
<p class="lede" style="text-align:left;margin:0 0 28px">Other tools rewrite your resume and hope it holds up in the interview. Maggie only uses what you've confirmed, shows the proof for each line, and removes anything it can't back up.</p>
<a class="btn pri lg" href="#">See a tailored resume {ic("arrow-right",16)}</a></div>
<div class="ba" style="margin-top:0">
<div class="doc before"><div class="dh8">Your resume<span class="st sent">Original</span></div><div class="k">Experience</div><div class="role">Product Analyst</div><div class="org">OneCard · 2023 – now</div>
<ul><li><span class="b"></span>Worked on merchant offers dashboard</li><li><span class="b"></span>Did A/B tests for onboarding</li><li><span class="b"></span>Helped the team with reports</li></ul>
<div class="k" style="margin-top:18px">Skills</div><div class="reasons"><span class="chip">SQL</span><span class="chip">Excel</span><span class="chip">Mixpanel</span></div></div>
<div class="arrow" aria-hidden="true">{ic("arrow-right",18)}</div>
<div class="doc after"><div class="dh8">For Razorpay · Product Analyst<span class="st ready">{ic("shield-check",13)}Checked</span></div><div class="k">Experience</div><div class="role">Product Analyst</div><div class="org">OneCard · 2023 – now</div>
<ul><li><span style="color:var(--ok)">{ic("check",15)}</span><div>Built SQL dashboards tracking merchant-offer drop-off across 3 payment flows.<div class="ev">Backed by <span class="fact">F2</span><span class="fact">F7</span></div></div></li>
<li><span style="color:var(--ok)">{ic("check",15)}</span><div>Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.<div class="ev">Backed by <span class="fact">F4</span></div></div></li>
<li class="cut"><span style="color:var(--err)">{ic("x",15)}</span><div><span class="x">Led a cross-functional team of 6.</span><div class="ev" style="color:var(--err)">Not in your facts — removed</div></div></li></ul>
<div class="k" style="margin-top:18px">Skills, reordered for this job</div><div class="reasons"><span class="chip">{ic("check",12)}SQL</span><span class="chip">{ic("check",12)}A/B testing</span><span class="chip">{ic("check",12)}Payments</span><span class="chip miss">{ic("minus",12)}Python · ask me</span></div></div>
</div></div></div></section>'''

    aud = f'''<section class="sect"><div class="wrap"><div class="eyb">Built for your stage</div><h2 class="h" style="margin-top:14px">First job or fifth year. <em>Same honest resume.</em></h2>
<div class="aud">
<div class="au"><div class="ico">{ic("graduation-cap",20)}</div><h4>Students and freshers</h4><p>Turns projects, internships and college work into facts recruiters can check.</p><div class="eg">e.g. B.Tech 2026 · internships · campus projects</div></div>
<div class="au"><div class="ico">{ic("briefcase-business",20)}</div><h4>1–6 years' experience</h4><p>Finds the next step up and tailors around results you've actually delivered.</p><div class="eg">e.g. Analyst → Product Analyst · SDE I → SDE II</div></div>
<div class="au"><div class="ico">{ic("shuffle",20)}</div><h4>Switching careers</h4><p>Shows which of your real skills transfer, and what's honestly missing.</p><div class="eg">e.g. Operations → Product · Sales → Customer Success</div></div>
</div></div></section>'''

    cta = f'''<section class="cta8"><div class="wrap"><div><div class="eyb" style="color:#5C4712">Your next application</div><h2 style="margin-top:14px">Apply like you mean every word.</h2>
<div class="ctas" style="justify-content:flex-start;display:flex;gap:10px;flex-wrap:wrap"><a class="btn pri lg" href="#">{ic("upload",16)}Upload your resume</a><a class="btn sec lg" href="#">{ic("play",15)}Watch 1-min demo</a></div>
<div class="fine"><span>{ic("check",14)}No card</span><span>{ic("check",14)}2-minute setup</span><span>{ic("check",14)}Cancel in one tap</span></div></div>
<div class="mini8"><div class="r"><span class="st ready">{ic("circle-check",13)}Ready</span><span class="t">Associate PM · Swiggy</span><span class="num" style="color:var(--ink3)">88</span></div>
<div class="r"><span class="st ready">{ic("circle-check",13)}Ready</span><span class="t">Business Analyst · Zerodha</span><span class="num" style="color:var(--ink3)">84</span></div>
<div class="r"><span class="st sent">{ic("send",13)}Sent</span><span class="t">Growth Analyst · CRED</span><span style="color:var(--ink3);font-size:12px">2h ago</span></div></div></div></section>'''

    return header + hero + steps + ba + aud + band.replace("</main>", "") + price + "</main>" + cta + footer

if __name__ == "__main__":
    html = page(p, landing8(), "ApplyScout — landing v2")
    html = html.replace("</style>", CSS8 + "</style>", 1)
    open(R + "landing-v2.html", "w").write(html)
    print("ok")
