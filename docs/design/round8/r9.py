"""Round 8: tech direction (Vercel / Linear grammar). Dark and light from one markup."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import r7
from r7 import ic, LOGO, SYM, app_window, co

OUT = "/home/user/job/docs/design/round8/"
os.makedirs(OUT + "shots", exist_ok=True)

FF = ""
for w in (400, 500, 600, 700):
    FF += f"@font-face{{font-family:'Geist';src:url(../round7/fonts/geist-sans-latin-{w}-normal.woff2) format('woff2');font-weight:{w};font-display:block}}\n"
for w in (400, 500):
    FF += f"@font-face{{font-family:'Geist Mono';src:url(../round7/fonts/geist-mono-latin-{w}-normal.woff2) format('woff2');font-weight:{w};font-display:block}}\n"

COMMON = dict(dot="#F5A524", acc="#F5A524")
DARK = dict(bg="#000000", surf="#0A0A0A", sunk="#060606", ink="#EDEDED", ink2="#A1A1A1", ink3="#8F8F8F", line="#1C1C1C", line2="#2A2A2A",
            pri="#EDEDED", onpri="#0A0A0A", prih="#FFFFFF", mark="#EDEDED", soft="#14181F", softtx="#9EC1FF", link="#52A8FF",
            band="#0A0A0A", bandink="#EDEDED", bandmut="#A1A1A1", bandline="#1C1C1C", stage="#0A0A0A",
            ok="#3FCF8E", oksoft="#0B2117", warn="#F5A524", warnsoft="#2A1E08", err="#FF6166", errsoft="#2B0F11",
            grid="rgba(255,255,255,.06)", glow1="rgba(245,165,36,.20)", glow2="rgba(255,97,102,.12)", **COMMON)
LIGHT = dict(bg="#FFFFFF", surf="#FFFFFF", sunk="#FAFAFA", ink="#0A0A0A", ink2="#4D4D4D", ink3="#6E6E6E", line="#EBEBEB", line2="#DEDEDE",
             pri="#0A0A0A", onpri="#FFFFFF", prih="#2A2A2A", mark="#0A0A0A", soft="#EEF4FF", softtx="#0B5CD5", link="#0B6BDB",
             band="#0A0A0A", bandink="#EDEDED", bandmut="#A1A1A1", bandline="#1C1C1C", stage="#FAFAFA",
             ok="#107A42", oksoft="#E9F7EF", warn="#8A5300", warnsoft="#FDF3DC", err="#C42B2B", errsoft="#FDECEC",
             grid="rgba(0,0,0,.05)", glow1="rgba(245,165,36,.22)", glow2="rgba(255,97,102,.10)", **COMMON)

CSS = r"""
body{font-family:Geist,Inter,system-ui,sans-serif;font-feature-settings:normal;letter-spacing:-.005em}
.mono,.m9{font-family:'Geist Mono',ui-monospace,monospace}
.wrap{max-width:1180px;padding:0 24px}
.top{background:color-mix(in srgb,var(--bg) 80%,transparent)}
.top .wrap{height:60px}
.logo{height:28px}
.top nav a{font-size:14px}
.btn{border-radius:6px;font-weight:500}
.btn.lg{height:44px;border-radius:8px;font-size:15px}
/* frame of grid lines */
.rail{max-width:1180px;margin:0 auto;border-left:1px solid var(--line);border-right:1px solid var(--line);position:relative}
.cross{position:absolute;width:13px;height:13px;color:var(--ink3);z-index:2}
.cross::before,.cross::after{content:"";position:absolute;background:currentColor}
.cross::before{left:6px;top:0;width:1px;height:13px}.cross::after{top:6px;left:0;height:1px;width:13px}
.tl{left:-7px;top:-7px}.tr{right:-7px;top:-7px}.bl{left:-7px;bottom:-7px}.br{right:-7px;bottom:-7px}
.hr{border-top:1px solid var(--line)}
/* hero */
.h9{position:relative;padding:96px 48px 0;text-align:center;overflow:hidden}
.h9::before{content:"";position:absolute;inset:0;background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);background-size:56px 56px;background-position:-1px -1px;mask-image:radial-gradient(ellipse 70% 60% at 50% 0%,#000 30%,transparent 75%);-webkit-mask-image:radial-gradient(ellipse 70% 60% at 50% 0%,#000 30%,transparent 75%);pointer-events:none}
.h9>*{position:relative}
.badge9{display:inline-flex;align-items:center;gap:8px;height:28px;padding:0 10px;border:1px solid var(--line2);border-radius:99px;font-size:12.5px;color:var(--ink2);background:var(--surf)}
.badge9 i{width:6px;height:6px;border-radius:9px;background:var(--ok);box-shadow:0 0 0 3px color-mix(in srgb,var(--ok) 25%,transparent)}
.h9 h1{font-size:clamp(40px,6.2vw,80px);line-height:1;letter-spacing:-.055em;font-weight:600;margin:24px auto 20px;max-width:13ch}
.h9 h1 .g{background:linear-gradient(180deg,var(--ink) 30%,color-mix(in srgb,var(--ink) 45%,var(--bg)));-webkit-background-clip:text;background-clip:text;color:transparent}
.h9 .lede{font-size:18px;color:var(--ink2);max-width:34em;margin:0 auto 32px;letter-spacing:-.01em}
.cmd{display:inline-flex;align-items:center;gap:10px;margin-top:22px;font:13px 'Geist Mono';color:var(--ink3)}
.cmd b{color:var(--ink);font-weight:500}
.cmd .sep{width:1px;height:12px;background:var(--line2)}
.prod{position:relative;margin:64px -1px 0;padding:0 24px}
.prod::before{content:"";position:absolute;left:10%;right:10%;top:40px;height:420px;background:radial-gradient(ellipse 50% 60% at 35% 50%,var(--glow1),transparent 70%),radial-gradient(ellipse 45% 55% at 70% 45%,var(--glow2),transparent 70%);filter:blur(30px)}
.prod .frame{position:relative;border-radius:12px 12px 0 0;border-bottom:0;box-shadow:0 0 0 1px var(--line2),0 -20px 80px -40px rgba(0,0,0,.4)}
.prod .app{height:560px;grid-template-columns:200px 1fr 360px}
/* numbers row */
.nums9{display:grid;grid-template-columns:repeat(4,1fr)}
.n9{padding:32px 28px;border-right:1px solid var(--line)}
.n9:last-child{border-right:0}
.n9 b{display:block;font:500 40px/1 'Geist Mono';letter-spacing:-.04em;color:var(--ink)}
.n9 span{display:block;margin-top:10px;font-size:14px;color:var(--ink2)}
.lab9{font:500 12px 'Geist Mono';color:var(--ink3);text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:center;gap:8px}
/* section head */
.sh9{padding:96px 48px 48px;display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:end}
.sh9 h2{font-size:clamp(32px,3.6vw,48px);line-height:1.02;letter-spacing:-.045em;font-weight:600;margin:14px 0 0}
.sh9 h2 em{font-style:normal;color:var(--ink3)}
.sh9 p{margin:0;color:var(--ink2);font-size:16px;max-width:30em}
/* pipeline */
.pipe{display:grid;grid-template-columns:repeat(5,1fr);border-top:1px solid var(--line)}
.node{padding:24px;border-right:1px solid var(--line);position:relative}
.node:last-child{border-right:0}
.node .k{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}
.node .ico9{width:36px;height:36px;border:1px solid var(--line2);border-radius:8px;display:grid;place-items:center;background:var(--surf);color:var(--ink)}
.node h4{margin:0 0 6px;font-size:16px;font-weight:600;letter-spacing:-.02em}
.node p{margin:0;font-size:14px;color:var(--ink2)}
.node .t{font:12px 'Geist Mono';color:var(--ink3)}
.node::after{content:"";position:absolute;right:-5px;top:42px;width:9px;height:9px;border-top:1px solid var(--ink3);border-right:1px solid var(--ink3);transform:rotate(45deg);background:var(--bg);z-index:1}
.node:last-child::after{display:none}
.prodm{display:none}
.log{border-top:1px solid var(--line);padding:20px 24px;font:12.5px/1.9 'Geist Mono';color:var(--ink3);background:var(--sunk)}
.log b{color:var(--ink);font-weight:500}.log .ok{color:var(--ok)}.log .w{color:var(--warn)}.log .e{color:var(--err)}
/* bento */
.bento{display:grid;grid-template-columns:repeat(6,1fr);border-top:1px solid var(--line)}
.bx{border-right:1px solid var(--line);border-bottom:1px solid var(--line);padding:28px;display:flex;flex-direction:column;gap:6px;min-height:300px;overflow:hidden;position:relative}
.bx.c4{grid-column:span 4}.bx.c2{grid-column:span 2}.bx.c3{grid-column:span 3}
.bx.end{border-right:0}
.bx h4{margin:0;font-size:17px;font-weight:600;letter-spacing:-.02em;display:flex;gap:8px;align-items:center}
.bx>p{margin:0 0 18px;color:var(--ink2);font-size:14.5px;max-width:34em}
.card9{border:1px solid var(--line2);border-radius:10px;background:var(--surf);padding:14px 16px;font-size:13.5px}
.vline{display:grid;grid-template-columns:18px 1fr auto;gap:10px;align-items:start;padding:10px 0;border-bottom:1px solid var(--line)}
.vline:last-child{border-bottom:0}
.vline .t{line-height:1.45}
.vline .fx{display:flex;gap:4px}
.vline.cut .t{color:var(--ink3);text-decoration:line-through;text-decoration-color:var(--err)}
.meter9{display:flex;gap:3px;margin-top:6px}.meter9 i{height:6px;flex:1;border-radius:2px;background:var(--ok)}.meter9 i.off{background:var(--line2)}
.phone9{width:220px;height:300px;border:1px solid var(--line2);border-radius:28px 28px 0 0;border-bottom:0;margin:auto auto -28px;background:var(--surf);padding:16px 12px;display:flex;flex-direction:column;gap:8px;font-size:12px}
.phone9 .big{margin-top:auto;height:40px;border-radius:9px;background:var(--pri);color:var(--onpri);display:grid;place-items:center;font-weight:600;font-size:13px}
.kv9{display:grid;grid-template-columns:90px 1fr;gap:6px 10px;font-size:13px}
.kv9 dt{color:var(--ink3);font-family:'Geist Mono';font-size:12px}.kv9 dd{margin:0}
.warn9{display:flex;gap:10px;align-items:flex-start;border:1px solid color-mix(in srgb,var(--err) 40%,var(--line2));background:var(--errsoft);border-radius:10px;padding:12px 14px;font-size:13px}
/* compare */
.cmp{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--line)}
.cmp>div{padding:32px 40px}
.cmp>div:first-child{border-right:1px solid var(--line)}
.cmp ul{list-style:none;margin:18px 0 0;padding:0;display:grid;gap:12px;font-size:14.5px}
.cmp li{display:grid;grid-template-columns:20px 1fr;gap:10px;color:var(--ink2)}
/* pricing */
.pr9{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line)}
.pc{padding:32px 28px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:6px}
.pc:last-child{border-right:0}
.pc.hi{background:var(--sunk)}
.pc .pp{font:500 44px/1 'Geist Mono';letter-spacing:-.05em;margin:18px 0 2px}
.pc .pp small{font:400 14px Geist;color:var(--ink3);letter-spacing:0}
.pc ul{list-style:none;padding:0;margin:20px 0 28px;display:grid;gap:10px;font-size:14px;color:var(--ink2)}
.pc li{display:flex;gap:8px;align-items:center}
.pc .btn{margin-top:auto;justify-content:center}
/* final */
.fin{position:relative;padding:120px 48px;text-align:center;overflow:hidden}
.fin::before{content:"";position:absolute;inset:0;background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);background-size:56px 56px;mask-image:radial-gradient(ellipse 60% 70% at 50% 50%,#000 20%,transparent 70%);-webkit-mask-image:radial-gradient(ellipse 60% 70% at 50% 50%,#000 20%,transparent 70%)}
.fin>*{position:relative}
.fin h2{font-size:clamp(36px,5vw,64px);letter-spacing:-.055em;line-height:1;font-weight:600;margin:0 auto 28px;max-width:14ch}
.f9{display:flex;justify-content:space-between;align-items:flex-start;padding:40px 48px 56px;font-size:13.5px;color:var(--ink3)}
.f9 .cols{display:flex;gap:64px}.f9 .cols div{display:grid;gap:8px;align-content:start}.f9 b{color:var(--ink);font-weight:500}
.status9{display:inline-flex;gap:8px;align-items:center;margin-top:14px;font:12px 'Geist Mono'}.status9 i{width:7px;height:7px;border-radius:9px;background:var(--ok)}
@media (max-width:760px){
 .wrap{padding:0 16px}.top nav,.top .r .gh{display:none}
 .rail{border:0}.cross{display:none}
 .h9{padding:56px 16px 0;text-align:left}.h9 h1{font-size:44px;margin-left:0}.h9 .lede{margin-left:0;font-size:17px}
 .h9 .ctas{justify-content:stretch;flex-direction:column}.h9 .ctas .btn{justify-content:center}
 .cmd{flex-wrap:wrap;gap:6px 10px}
 .prod{display:none}.prodm{display:block;margin:40px 0 0;border:1px solid var(--line2);border-bottom:0;border-radius:24px 24px 0 0;overflow:hidden;height:600px}.prodm .phone{width:100%;min-height:600px}
 .f9 .cols{margin-left:0!important}
 .nums9{grid-template-columns:1fr 1fr}.n9{border-bottom:1px solid var(--line);padding:22px 16px}.n9:nth-child(2n){border-right:0}.n9 b{font-size:30px}
 .sh9{grid-template-columns:1fr;padding:64px 16px 28px;gap:14px}
 .pipe{grid-template-columns:1fr}.node{border-right:0;border-bottom:1px solid var(--line);padding:20px 16px}.node::after{display:none}.node .k{margin-bottom:14px}
 .log{padding:16px;font-size:11.5px;overflow:hidden;white-space:nowrap}
 .bento{grid-template-columns:1fr}.bx.c4,.bx.c2,.bx.c3{grid-column:auto}.bx{border-right:0;padding:22px 16px;min-height:0}
 .phone9{margin-bottom:-22px}
 .cmp,.pr9{grid-template-columns:1fr}.cmp>div{padding:24px 16px}.cmp>div:first-child{border-right:0;border-bottom:1px solid var(--line)}.pc{border-right:0;border-bottom:1px solid var(--line);padding:24px 16px}
 .fin{padding:80px 16px}.f9{flex-direction:column;gap:32px;padding:32px 16px}.f9 .cols{gap:36px;flex-wrap:wrap}
}
"""

def x4():
    return '<span class="cross tl"></span><span class="cross tr"></span><span class="cross bl"></span><span class="cross br"></span>'

def body():
    nav = f'''<a class="skip" href="#m">Skip to content</a><header class="top"><div class="wrap"><a href="#" aria-label="ApplyScout home">{LOGO}</a>
<nav aria-label="Main"><a href="#">Product</a><a href="#">How it works</a><a href="#">Security</a><a href="#">Pricing</a><a href="#">Changelog</a></nav>
<div class="r"><a class="btn gh sm" href="#">Log in</a><a class="btn pri sm" href="#">Upload resume</a></div></div></header>'''

    hero = f'''<main id="m"><div class="rail">
<section class="h9" data-shot="hero"><span class="badge9"><i></i>Truth check is live for every resume line {ic("arrow-right",13)}</span>
<h1><span class="g">Apply to the right jobs. Every line true.</span></h1>
<p class="lede">ApplyScout finds roles that fit, tailors your resume using only facts you've confirmed, and sends nothing until you approve.</p>
<div class="ctas"><a class="btn pri lg" href="#">{ic("upload",16)}Upload your resume</a><a class="btn sec lg" href="#">Try with a sample resume</a></div>
<div class="cmd"><span><b>10</b> free applications</span><span class="sep"></span><span>no card</span><span class="sep"></span><span>pay in <b>₹</b> with UPI</span></div>
<div class="prod"><div class="frame">{app_window()}</div></div><div class="prodm">{r7.phone_today()}</div></section>
<div class="hr" style="position:relative">{x4()}<div class="nums9">
<div class="n9"><b>6</b><span>job sources searched every hour</span></div>
<div class="n9"><b>100%</b><span>of resume lines linked to a fact you confirmed</span></div>
<div class="n9"><b>0</b><span>applications sent without your approval</span></div>
<div class="n9"><b>₹0</b><span>to start. Pro from ₹299 a month</span></div></div></div>

<section><div class="sh9"><div><span class="lab9">{ic("workflow",14)}How it works</span><h2>A pipeline you can inspect. <em>Not a black box.</em></h2></div><p>Every application goes through the same five steps. You can see what happened at each one, and nothing reaches an employer until step 4.</p></div>
<div class="pipe">
<div class="node"><div class="k"><span class="ico9">{ic("radar",18)}</span><span class="t">hourly</span></div><h4>1 · Find</h4><p>Searches Greenhouse, Lever, Workday, Ashby and career pages.</p></div>
<div class="node"><div class="k"><span class="ico9">{ic("target",18)}</span><span class="t">~2s</span></div><h4>2 · Match</h4><p>Scores each role against your real skills and explains why.</p></div>
<div class="node"><div class="k"><span class="ico9">{ic("shield-check",18)}</span><span class="t">~40s</span></div><h4>3 · Tailor + verify</h4><p>Rewrites your resume and checks every line against your facts.</p></div>
<div class="node"><div class="k"><span class="ico9">{ic("circle-check-big",18)}</span><span class="t">you</span></div><h4>4 · Approve</h4><p>You see the exact file and message. One tap to send.</p></div>
<div class="node"><div class="k"><span class="ico9">{ic("receipt-text",18)}</span><span class="t">instant</span></div><h4>5 · Send + receipt</h4><p>Sent from your Gmail, with a receipt you can check later.</p></div></div>
<div class="log" aria-label="Example activity log">
<div>09:40:12 &nbsp;<b>match</b> &nbsp;Product Analyst · Razorpay &nbsp;fit=<b>92</b> &nbsp;skills 6/8</div>
<div>09:40:51 &nbsp;<b>verify</b> &nbsp;14 lines &nbsp;<span class="ok">13 backed</span> &nbsp;<span class="e">1 removed: "Led a team of 6"</span></div>
<div>09:40:52 &nbsp;<b>ask</b> &nbsp;&nbsp;&nbsp;<span class="w">"Have you used Python at work?"</span> &nbsp;waiting for you</div>
<div>09:42:03 &nbsp;<b>send</b> &nbsp;&nbsp;Associate PM · Swiggy &nbsp;approved by you &nbsp;<span class="ok">receipt AS-24817</span></div></div></section>

<section><div class="sh9 hr" style="position:relative">{x4()}<div><span class="lab9">{ic("layout-grid",14)}Product</span><h2>Everything a job search needs. <em>Nothing that fakes it.</em></h2></div><p>Built for freshers and people with up to six years' experience, on the phone you already have.</p></div>
<div class="bento">
<div class="bx c4"><h4>{ic("shield-check",18)}Truth check on every line</h4><p>Each tailored line links to a fact you confirmed. Anything that can't be backed is removed before you see it.</p>
<div class="card9" style="margin-top:auto"><div class="vline"><span style="color:var(--ok)">{ic("check",16)}</span><span class="t">Built SQL dashboards tracking checkout drop-off across 3 payment flows.</span><span class="fx"><span class="fact">F2</span><span class="fact">F7</span></span></div>
<div class="vline"><span style="color:var(--ok)">{ic("check",16)}</span><span class="t">Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.</span><span class="fx"><span class="fact">F4</span></span></div>
<div class="vline cut"><span style="color:var(--err)">{ic("x",16)}</span><span class="t">Led a team of 6 analysts.</span><span class="st blk">Removed</span></div></div></div>
<div class="bx c2 end"><h4>{ic("smartphone",18)}Approve from your phone</h4><p>One thumb, ten seconds.</p>
<div class="phone9"><span class="m9" style="color:var(--ink3);font-size:11px">RAZORPAY · PRODUCT ANALYST</span><b style="font-size:14px">Ready to send</b><span style="color:var(--ink2)">14 of 14 lines backed</span><div class="meter9"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><span class="big">Approve &amp; send</span></div></div>
<div class="bx c2"><h4>{ic("target",18)}Fit, explained</h4><p>Not a magic score. The skills you have and the ones you don't.</p>
<div class="reasons" style="margin-top:auto"><span class="chip">{ic("check",12)}SQL</span><span class="chip">{ic("check",12)}A/B testing</span><span class="chip">{ic("check",12)}Payments</span><span class="chip">{ic("check",12)}Reporting</span><span class="chip miss">{ic("minus",12)}Python</span><span class="chip miss">{ic("minus",12)}dbt</span></div></div>
<div class="bx c2"><h4>{ic("receipt-text",18)}A receipt for every send</h4><p>Proof of what went where, and when.</p>
<dl class="kv9" style="margin-top:auto"><dt>id</dt><dd class="m9">AS-24817</dd><dt>to</dt><dd>Swiggy · careers@…</dd><dt>sent</dt><dd class="num">10 Oct, 09:42</dd><dt>file</dt><dd class="m9" style="font-size:12px">priya-apm-swiggy.pdf</dd></dl></div>
<div class="bx c2 end"><h4>{ic("shield-alert",18)}Scam guard</h4><p>Listings that ask for fees or deposits are flagged and never applied to.</p>
<div class="warn9" style="margin-top:auto"><span style="color:var(--err)">{ic("triangle-alert",16)}</span><div><b style="font-weight:600">"Pay ₹2,000 registration fee"</b><div style="color:var(--ink2);margin-top:2px">Blocked. Real employers don't charge you.</div></div></div></div>
</div></section>

<section><div class="sh9" style="position:relative">{x4()}<div><span class="lab9">{ic("git-compare",14)}Why it's different</span><h2>Most AI tools write what sounds good. <em>We write what's true.</em></h2></div><p></p></div>
<div class="cmp"><div><span class="lab9">Typical AI auto-apply</span><ul>
<li><span style="color:var(--err)">{ic("x",16)}</span>Invents skills and titles to match keywords</li><li><span style="color:var(--err)">{ic("x",16)}</span>Sends hundreds of applications in the background</li><li><span style="color:var(--err)">{ic("x",16)}</span>No record of what was sent</li><li><span style="color:var(--err)">{ic("x",16)}</span>Charged in dollars, hard to cancel</li></ul></div>
<div><span class="lab9" style="color:var(--ink)">ApplyScout</span><ul>
<li><span style="color:var(--ok)">{ic("check",16)}</span>Only uses facts you've confirmed, and shows the proof</li><li><span style="color:var(--ok)">{ic("check",16)}</span>Fewer, better applications, each approved by you</li><li><span style="color:var(--ok)">{ic("check",16)}</span>A receipt for every send</li><li><span style="color:var(--ok)">{ic("check",16)}</span>Priced in ₹, GST included, cancel in one tap</li></ul></div></div></section>

<section><div class="sh9 hr" style="position:relative">{x4()}<div><span class="lab9">{ic("indian-rupee",14)}Pricing</span><h2>Priced for a first job. <em>Not a corporate card.</em></h2></div><p>Example prices for this design. Includes GST.</p></div>
<div class="pr9">
<div class="pc"><span class="lab9">Free</span><div class="pp">₹0</div><ul><li>{ic("check",15)}10 applications</li><li>{ic("check",15)}Truth check</li><li>{ic("check",15)}Receipts</li></ul><a class="btn sec" href="#">Upload resume</a></div>
<div class="pc hi"><span class="lab9" style="color:var(--ink)">Pro <span class="tag">Recommended</span></span><div class="pp">₹299<small> / month</small></div><ul><li>{ic("check",15)}Up to 20 applications a day</li><li>{ic("check",15)}2 campaigns</li><li>{ic("check",15)}Send from your Gmail</li></ul><a class="btn pri" href="#">Start Pro</a></div>
<div class="pc"><span class="lab9">Max</span><div class="pp">₹799<small> / month</small></div><ul><li>{ic("check",15)}Up to 50 a day</li><li>{ic("check",15)}Referral finder</li><li>{ic("check",15)}Priority tailoring</li></ul><a class="btn sec" href="#">Start Max</a></div></div></section>

<section class="fin hr"><h2>Your next application, done right.</h2><div class="ctas"><a class="btn pri lg" href="#">{ic("upload",16)}Upload your resume</a><a class="btn sec lg" href="#">Talk to us</a></div>
<div class="cmd" style="justify-content:center"><span>2-minute setup</span><span class="sep"></span><span>no card</span><span class="sep"></span><span>cancel in one tap</span></div></section>
<footer class="hr" style="margin:0;padding:0;border-top:1px solid var(--line)"><div class="f9"><div>{LOGO}<div class="status9"><i></i>All systems normal</div></div>
<div class="cols"><div><b>Product</b><a href="#">How it works</a><a href="#">Pricing</a><a href="#">Changelog</a></div><div><b>Trust</b><a href="#">Security</a><a href="#">Privacy</a><a href="#">Report a scam</a></div><div><b>Company</b><a href="#">About</a><a href="#">Contact</a></div></div></div></footer>
</div></main>'''
    return nav + hero

def page(theme, p):
    cls = ' class="dark"' if theme == "dark" else ""
    v = ":root{" + ";".join(f"--{k}:{val}" for k, val in p.items()) + "}"
    return f'<!doctype html><html lang="en"{cls}><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ApplyScout — tech direction ({theme})</title><style>{r7.fontfaces().replace("url(fonts/","url(../round7/fonts/")}{FF}{v}{r7.CSS}{CSS}</style><body>{body()}</body></html>'

if __name__ == "__main__":
    for t, p in (("dark", DARK), ("light", LIGHT)):
        open(OUT + f"landing-{t}.html", "w").write(page(t, p))
    print("ok")
