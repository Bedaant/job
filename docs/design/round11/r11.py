"""Round 11: job-portal landing, studied from the Dribbble references. One markup, two colourways (?t=sky | sunrise)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from r7 import ic, LOGO

OUT = "/home/user/job/docs/design/round11/"

FONTS = """
@font-face{font-family:'Plus Jakarta Sans';src:url(fonts/plus-jakarta-sans-latin-400-normal.woff2) format('woff2');font-weight:400;font-display:block}
@font-face{font-family:'Plus Jakarta Sans';src:url(fonts/plus-jakarta-sans-latin-500-normal.woff2) format('woff2');font-weight:500;font-display:block}
@font-face{font-family:'Plus Jakarta Sans';src:url(fonts/plus-jakarta-sans-latin-600-normal.woff2) format('woff2');font-weight:600;font-display:block}
@font-face{font-family:'Plus Jakarta Sans';src:url(fonts/plus-jakarta-sans-latin-700-normal.woff2) format('woff2');font-weight:700 800;font-display:block}
@font-face{font-family:'Source Serif 4';src:url(fonts/source-serif-4-latin-400-italic.woff2) format('woff2');font-weight:400;font-style:italic;font-display:block}
@font-face{font-family:'Noto Sans Devanagari';src:url(fonts/noto-sans-devanagari-devanagari-600-normal.woff2) format('woff2');font-weight:600;font-display:block}
@font-face{font-family:'Geist Mono';src:url(fonts/geist-mono-latin-500-normal.woff2) format('woff2');font-weight:500;font-display:block}
"""

CSS = r"""
:root{--ink:#0B1020;--ink2:#3B4363;--ink3:#69718C;--line:#E2E7F3;--surf:#fff;--ok:#12805C;--oksoft:#E3F5EE;--err:#C7372F;--errsoft:#FDECEA;--r:18px;
--bg1:#E8F0FF;--bg2:#F4EFFF;--page:#F8FAFF;--acc:#2457F5;--accsoft:#E6EDFF;--acctx:#1B3FBF;--btn:#0B1020;--onbtn:#fff;
--c1:#E5D9FF;--c2:#FFE0CF;--c3:#D3F3E4;--c4:#D6E8FF}
[data-theme=sunrise]{--bg1:#FFEFD9;--bg2:#FFE3EA;--page:#FFFAF4;--acc:#E8541F;--accsoft:#FFE9DE;--acctx:#B23A0E;--line:#F1E4D8;--ink:#1D1210;--ink2:#4D3A34;--ink3:#7A645C;--btn:#1D1210;
--c1:#FFE1B8;--c2:#FFD1D9;--c3:#DDF2C9;--c4:#D8E6FF}
*{box-sizing:border-box}html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:400 16px/1.55 'Plus Jakarta Sans',Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased;overflow-x:clip}
a{color:inherit;text-decoration:none}button{font:inherit;color:inherit}
.i{flex:none;vertical-align:-3px}.mono{font-family:'Geist Mono',monospace}
.wrap{max-width:1180px;margin:0 auto;padding:0 28px}
:focus-visible{outline:2px solid var(--acc);outline-offset:3px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
.btn{display:inline-flex;align-items:center;gap:9px;height:46px;padding:0 22px;border-radius:99px;border:1px solid transparent;font-weight:600;font-size:15px;cursor:pointer;white-space:nowrap;transition:transform .15s,box-shadow .15s}
.btn:hover{transform:translateY(-1px)}
.btn.dark{background:var(--btn);color:var(--onbtn)}.btn.acc{background:var(--acc);color:#fff}
.btn.ghost{background:var(--surf);border-color:var(--line);color:var(--ink)}.btn.sm{height:38px;padding:0 16px;font-size:14px}.btn.lg{height:54px;padding:0 28px;font-size:16px}
/* nav */
.navw{position:sticky;top:14px;z-index:20;padding:0 20px}
.nav{max-width:1120px;margin:14px auto 0;height:62px;display:flex;align-items:center;gap:28px;padding:0 10px 0 22px;background:rgba(255,255,255,.78);backdrop-filter:blur(14px) saturate(1.4);border:1px solid rgba(255,255,255,.9);border-radius:99px;box-shadow:0 8px 30px -12px rgba(30,40,90,.25)}
.logo{height:26px;width:auto;display:block}.nav nav{display:flex;gap:6px;flex:1}
.nav nav a{padding:8px 14px;border-radius:99px;font-size:14.5px;font-weight:500;color:var(--ink2)}.nav nav a:hover{background:var(--accsoft);color:var(--acctx)}
.lang{display:inline-flex;gap:2px;padding:3px;border-radius:99px;background:var(--accsoft);font-size:13px;font-weight:600}
.lang span{padding:5px 11px;border-radius:99px;color:var(--acctx)}.lang span.on{background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}
/* hero */
.hero{position:relative;margin-top:-76px;padding:140px 0 0;background:radial-gradient(900px 500px at 15% 10%,var(--bg1),transparent 70%),radial-gradient(800px 500px at 90% 0%,var(--bg2),transparent 70%),var(--page);text-align:center;overflow:hidden}
.hero::after{content:"";position:absolute;left:0;right:0;bottom:0;height:120px;background:linear-gradient(transparent,var(--page));pointer-events:none;z-index:4}
.eyebrow{display:inline-flex;align-items:center;gap:8px;height:34px;padding:0 14px 0 6px;border-radius:99px;background:#fff;border:1px solid var(--line);font-size:13.5px;font-weight:500;color:var(--ink2);box-shadow:0 2px 8px -4px rgba(30,40,90,.2)}
.eyebrow b{background:var(--acc);color:#fff;border-radius:99px;font-size:11.5px;padding:3px 9px;font-weight:700}
h1.hd{font-size:clamp(40px,6.3vw,78px);line-height:1.02;letter-spacing:-.045em;font-weight:800;margin:24px auto 20px;max-width:15ch;text-wrap:balance}
h1.hd em{font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-weight:400;letter-spacing:-.02em;color:var(--acc);padding-right:.04em}
.sub{font-size:clamp(17px,1.5vw,20px);color:var(--ink2);max-width:36em;margin:0 auto 34px;text-wrap:pretty}
.prompt{max-width:780px;margin:0 auto;display:flex;align-items:center;gap:12px;padding:8px 8px 8px 24px;background:#fff;border:1px solid var(--line);border-radius:99px;box-shadow:0 18px 50px -18px rgba(36,60,160,.35);text-align:left}
.prompt .q{flex:1;color:var(--ink);font-size:16.5px;font-weight:500;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.prompt .q i{display:inline-block;width:2px;height:20px;background:var(--acc);vertical-align:-4px;margin-left:2px;animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.prompt .ph{color:var(--acc)}
.pop{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;max-width:900px;margin:22px auto 0}
.pop small{font-size:13px;color:var(--ink3);font-weight:600;margin-right:4px}
.chip{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 15px;border-radius:99px;background:rgba(255,255,255,.8);border:1px solid var(--line);font-size:13.5px;font-weight:500;color:var(--ink2)}
.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
.fine{margin-top:20px;display:flex;gap:22px;justify-content:center;flex-wrap:wrap;font-size:13.5px;color:var(--ink3)}
.fine span{display:inline-flex;gap:7px;align-items:center}
/* stage */
.stage{position:relative;height:540px;margin-top:40px;max-width:1180px;margin-left:auto;margin-right:auto}
.fan{position:absolute;width:262px;z-index:1;padding:18px;border-radius:24px;text-align:left;box-shadow:0 20px 40px -22px rgba(20,30,80,.4);border:1px solid rgba(255,255,255,.7)}
.fan .top{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:600;color:var(--ink2)}
.fan .lg{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;color:#fff;font-weight:700;font-size:13px}
.fan .sal{margin-left:auto;font-size:12.5px;font-weight:700;color:var(--ink)}
.fan h4{margin:16px 0 4px;font-size:21px;line-height:1.1;letter-spacing:-.03em;font-weight:700}
.fan p{margin:0;font-size:13px;color:var(--ink2)}.fan .tg{display:flex;gap:6px;margin:14px 0 16px;flex-wrap:wrap}
.fan .tg span{font-size:11.5px;font-weight:600;padding:3px 9px;border-radius:99px;background:rgba(255,255,255,.65)}
.fan .ap{display:flex;align-items:center;justify-content:center;height:36px;border-radius:99px;background:var(--ink);color:#fff;font-size:13px;font-weight:600}
.f1{left:calc(50% - 650px);top:250px;transform:rotate(-11deg);background:var(--c1)}.f2{left:calc(50% - 480px);top:170px;transform:rotate(-5deg);background:var(--c2)}
.f3{left:calc(50% + 218px);top:170px;transform:rotate(5deg);background:var(--c3)}.f4{left:calc(50% + 388px);top:250px;transform:rotate(11deg);background:var(--c4)}
.core{position:absolute;left:50%;top:0;transform:translateX(-50%);width:480px;background:#fff;border-radius:26px;border:1px solid var(--line);box-shadow:0 40px 80px -30px rgba(26,40,120,.45);text-align:left;z-index:3;overflow:hidden}
.core .hd2{display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--line)}
.core .hd2 .lg{width:34px;height:34px;border-radius:10px;background:#2D6CDF;color:#fff;display:grid;place-items:center;font-weight:700}
.core .hd2 b{display:block;font-size:15px}.core .hd2 span{font-size:12.5px;color:var(--ink3)}
.fit{margin-left:auto;font-weight:700;font-size:13px;background:var(--accsoft);color:var(--acctx);border-radius:99px;padding:5px 12px}
.ln{display:grid;grid-template-columns:24px 1fr auto;gap:12px;align-items:start;padding:14px 20px;border-bottom:1px solid var(--line);font-size:14px;line-height:1.45}
.ln .st{width:22px;height:22px;border-radius:99px;display:grid;place-items:center;margin-top:1px}
.ln.ok .st{background:var(--ok);color:#fff}.ln.no .st{background:var(--err);color:#fff}.ln.no p{color:var(--ink3);text-decoration:line-through;text-decoration-color:var(--err)}
.ln p{margin:0}.tag{font:500 11px 'Geist Mono',monospace;background:var(--accsoft);color:var(--acctx);border-radius:6px;padding:2px 6px;white-space:nowrap}
.ln .why{font-size:11.5px;font-weight:600;color:var(--err)}
.core .ft{display:flex;align-items:center;gap:10px;padding:14px 20px;background:#FAFBFF}.core .ft small{flex:1;font-size:12.5px;color:var(--ink3)}
.float{position:absolute;z-index:5;display:inline-flex;align-items:center;gap:9px;padding:10px 14px 10px 10px;border-radius:16px;background:#fff;border:1px solid var(--line);box-shadow:0 14px 34px -16px rgba(20,30,90,.4);font-size:13px;font-weight:600;white-space:nowrap}
.float .b{width:28px;height:28px;border-radius:9px;display:grid;place-items:center}
.float.g .b{background:var(--oksoft);color:var(--ok)}.float.a .b{background:var(--accsoft);color:var(--acctx)}.float.r .b{background:var(--errsoft);color:var(--err)}
.float small{display:block;font-weight:500;color:var(--ink3);font-size:11.5px;margin-top:-1px}
.fl1{left:calc(50% - 560px);top:40px}.fl2{left:calc(50% + 300px);top:60px}.fl4{left:50%;transform:translateX(-50%);top:384px}
/* sections */
.sec{padding:110px 0 0}.kick{display:inline-flex;align-items:center;gap:8px;font-size:13.5px;font-weight:700;color:var(--acctx);background:var(--accsoft);border-radius:99px;padding:6px 14px}
h2.t{font-size:clamp(30px,4vw,50px);line-height:1.05;letter-spacing:-.04em;font-weight:800;margin:18px 0 14px;max-width:18ch;text-wrap:balance}
h2.t em{font-family:'Source Serif 4',serif;font-style:italic;font-weight:400;color:var(--acc)}
.lead{font-size:18px;color:var(--ink2);max-width:36em;margin:0}.center{text-align:center}.center h2.t,.center .lead{margin-left:auto;margin-right:auto}
.srcs{display:flex;flex-wrap:wrap;justify-content:center;gap:14px 38px;margin-top:70px;color:var(--ink3);font-weight:700;font-size:17px;letter-spacing:-.02em}
.srcs small{width:100%;text-align:center;font-size:13px;font-weight:600;letter-spacing:0;margin-bottom:-4px}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-top:52px;position:relative}
.step{background:#fff;border:1px solid var(--line);border-radius:26px;padding:26px;position:relative;text-align:left}
.step .ico{width:56px;height:56px;border-radius:18px;display:grid;place-items:center;margin-bottom:22px}
.step .n{position:absolute;right:22px;top:22px;font:600 13px 'Geist Mono',monospace;color:var(--ink3)}
.step h3{margin:0 0 8px;font-size:20px;letter-spacing:-.03em}.step p{margin:0;color:var(--ink2);font-size:15px}
.step:not(:last-child)::after{content:"";position:absolute;right:-18px;top:52px;width:18px;border-top:2px dashed #C5CEE8}
.proof{display:grid;grid-template-columns:.9fr 1.1fr;gap:56px;align-items:center}
.ba{display:grid;grid-template-columns:1fr 44px 1.15fr;align-items:center;gap:0}
.doc{background:#fff;border:1px solid var(--line);border-radius:22px;padding:22px;box-shadow:0 24px 50px -30px rgba(30,40,120,.35);font-size:13.5px}
.doc .k{font-size:11px;font-weight:700;letter-spacing:.08em;color:var(--ink3);text-transform:uppercase;margin:0 0 10px}
.doc ul{list-style:none;margin:0;padding:0;display:grid;gap:11px}.doc li{display:grid;grid-template-columns:18px 1fr;gap:9px;line-height:1.45;color:var(--ink2)}
.doc li .d{width:5px;height:5px;border-radius:9px;background:#B6BED6;margin:8px 0 0 6px}
.doc.after li{color:var(--ink)}.arr{width:40px;height:40px;border-radius:99px;background:var(--acc);color:#fff;display:grid;place-items:center;margin:0 auto;box-shadow:0 8px 18px -8px var(--acc)}
.jobs{margin-top:46px;display:grid;grid-template-columns:1fr 1fr;gap:16px}
.job{display:grid;grid-template-columns:48px 1fr auto;gap:16px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:22px;padding:18px}
.job .lg{width:48px;height:48px;border-radius:14px;display:grid;place-items:center;color:#fff;font-weight:700;font-size:18px}
.job h4{margin:0;font-size:17px;letter-spacing:-.025em}.job .m{font-size:13.5px;color:var(--ink3);margin:2px 0 8px}
.job .tags{display:flex;gap:6px;flex-wrap:wrap}.job .tags span{font-size:12px;font-weight:600;padding:3px 10px;border-radius:99px;background:var(--accsoft);color:var(--acctx)}
.job .tags span.g{background:var(--oksoft);color:var(--ok)}
.job .side{text-align:right}.job .side b{display:block;font-size:15px}.job .side small{display:block;color:var(--ink3);font-size:12px;margin:2px 0 10px}
.note{margin-top:14px;text-align:center;font-size:13px;color:var(--ink3)}
.chat{display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center}
.chatbox{position:relative;background:#fff;border:1px solid var(--line);border-radius:30px;padding:26px;box-shadow:0 30px 70px -34px rgba(30,40,120,.4)}
.msg{max-width:88%;padding:12px 16px;border-radius:18px;font-size:14.5px;line-height:1.5;margin-bottom:12px}
.msg.u{margin-left:auto;background:var(--acc);color:#fff;border-bottom-right-radius:6px}.msg.m{background:#F1F4FC;border-bottom-left-radius:6px}
.who{display:flex;align-items:center;gap:10px;padding-bottom:16px;margin-bottom:16px;border-bottom:1px solid var(--line);font-weight:700}
.who .av{width:36px;height:36px;border-radius:12px;background:var(--accsoft);display:grid;place-items:center}
.sugg{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.sugg .chip{background:#fff;font-size:13px}
.msg .mini{margin-top:8px;display:grid;gap:6px}.msg .mini div{display:flex;gap:8px;align-items:center;font-size:13px}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:48px}
.cmpc{border-radius:30px;padding:34px;border:1px solid var(--line);background:#fff}
.cmpc.good{background:linear-gradient(160deg,var(--accsoft),#fff 70%);border-color:transparent;box-shadow:0 30px 60px -36px rgba(36,60,160,.5)}
.cmpc h3{margin:0 0 20px;font-size:22px;letter-spacing:-.03em;display:flex;align-items:center;gap:10px}
.cmpc ul{list-style:none;margin:0;padding:0;display:grid;gap:15px}.cmpc li{display:grid;grid-template-columns:26px 1fr;gap:10px;color:var(--ink2)}
.cmpc li .x,.cmpc li .v{width:24px;height:24px;border-radius:99px;display:grid;place-items:center}
.cmpc li .x{background:var(--errsoft);color:var(--err)}.cmpc li .v{background:var(--oksoft);color:var(--ok)}
.aud{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:46px}
.aud div{border-radius:28px;padding:28px}.aud .ico{width:52px;height:52px;border-radius:16px;background:rgba(255,255,255,.75);display:grid;place-items:center;margin-bottom:20px}
.aud h3{margin:0 0 8px;font-size:22px;letter-spacing:-.03em}.aud p{margin:0 0 16px;color:var(--ink2);font-size:15px}.aud small{font-weight:600;font-size:12.5px;background:rgba(255,255,255,.7);border-radius:99px;padding:5px 12px;display:inline-block}
.price{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:46px}
.plan{background:#fff;border:1px solid var(--line);border-radius:28px;padding:30px;display:flex;flex-direction:column;gap:8px}
.plan.hi{background:var(--btn);color:#fff;border-color:transparent;box-shadow:0 36px 70px -34px rgba(10,16,40,.7)}
.plan .pn{font-weight:700;display:flex;gap:10px;align-items:center}.plan .tg2{font-size:11.5px;background:var(--acc);color:#fff;border-radius:99px;padding:3px 10px}
.plan .pp{font-size:50px;font-weight:800;letter-spacing:-.05em;line-height:1;margin:14px 0 4px}.plan .pp small{font-size:15px;font-weight:500;opacity:.65;letter-spacing:0}
.plan ul{list-style:none;margin:16px 0 24px;padding:0;display:grid;gap:11px;font-size:15px}.plan li{display:flex;gap:10px;align-items:center}.plan li svg{color:var(--ok)}.plan.hi li svg{color:#8DE3BE}
.plan .btn{margin-top:auto;justify-content:center}.plan.hi .btn{background:#fff;color:var(--ink)}
.cta{margin:110px 28px 0;border-radius:44px;background:radial-gradient(700px 360px at 20% 0%,var(--bg1),transparent 70%),radial-gradient(700px 360px at 100% 100%,var(--bg2),transparent 70%),#fff;border:1px solid var(--line);padding:84px 28px;text-align:center}
.cta h2{font-size:clamp(34px,5vw,62px);line-height:1.02;letter-spacing:-.045em;font-weight:800;margin:0 auto 26px;max-width:15ch}
.cta h2 em{font-family:'Source Serif 4',serif;font-style:italic;font-weight:400;color:var(--acc)}
.sub2{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
footer{margin-top:90px;padding:44px 0 60px;border-top:1px solid var(--line);font-size:14px;color:var(--ink3)}
footer .wrap{display:flex;gap:40px;align-items:flex-start}footer .cols{display:flex;gap:70px;margin-left:auto}footer .cols div{display:grid;gap:9px;align-content:start}footer b{color:var(--ink)}
@media (max-width:860px){
 .wrap{padding:0 18px}.navw{padding:0 12px}.nav{padding:0 8px 0 16px;gap:10px}.nav nav,.nav .lang{display:none}.nav .sp{flex:1}
 .hero{padding-top:112px}.hero::after{display:none}.prompt{flex-direction:column;align-items:stretch;border-radius:28px;padding:16px;gap:12px}.prompt .q{white-space:normal}.prompt .btn{justify-content:center}
 .pop{justify-content:flex-start;flex-wrap:nowrap;overflow-x:auto;padding:0 18px 4px;margin-left:-18px;margin-right:-18px;scrollbar-width:none}.pop::-webkit-scrollbar{display:none}.pop .chip{flex:none}
 .stage{height:auto;margin-top:36px;padding-bottom:20px}.core{position:relative;left:auto;top:auto;transform:none;width:auto;margin:0 4px}.fan,.float{display:none}
 .stage .mfl{display:flex!important;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:16px}
 .sec{padding-top:76px}.steps{grid-template-columns:1fr 1fr}.step:not(:last-child)::after{display:none}.proof,.chat{grid-template-columns:1fr;gap:34px}.ba{grid-template-columns:1fr}.ba .doc:first-child{display:none}.ba .arr{display:none}
 .jobs,.cmp,.aud,.price{grid-template-columns:1fr}.job{grid-template-columns:44px 1fr}.job .side{grid-column:1/-1;display:flex;align-items:center;gap:12px;text-align:left}.job .side small{margin:0;flex:1}.job .side .btn{margin:0}
 .cta{margin:76px 12px 0;border-radius:32px;padding:56px 18px}footer .wrap{flex-direction:column}footer .cols{margin-left:0;gap:36px;flex-wrap:wrap}
}
.mfl{display:none}
"""

def logo_small(c, t): return f'<span class="lg" style="background:{c}">{t}</span>'

def page():
    nav = f'''<div class="navw"><header class="nav"><a href="#" aria-label="ApplyScout home">{LOGO}</a>
<nav aria-label="Main"><a href="#how">How it works</a><a href="#proof">Why it's safe</a><a href="#jobs">Jobs</a><a href="#pricing">Pricing</a></nav><span class="sp"></span>
<span class="lang" aria-label="Language"><span class="on">EN</span><span style="font-family:'Noto Sans Devanagari'">हिन्दी</span></span>
<a class="btn dark sm" href="#">Upload resume</a></header></div>'''

    fans = f'''
<div class="fan f1"><div class="top">{logo_small("#E8590C","S")}Swiggy<span class="sal">₹12–16 LPA</span></div><h4>Associate Product Manager</h4><p>Bengaluru · Hybrid</p><div class="tg"><span>0–2 yrs</span><span>Full-time</span></div><div class="ap">Review application</div></div>
<div class="fan f2"><div class="top">{logo_small("#7048E8","Z")}Zerodha<span class="sal">₹10–14 LPA</span></div><h4>Business Analyst</h4><p>Bengaluru · On-site</p><div class="tg"><span>1–3 yrs</span><span>SQL</span></div><div class="ap">Review application</div></div>
<div class="fan f3"><div class="top">{logo_small("#0B7285","M")}Meesho<span class="sal">₹9–13 LPA</span></div><h4>Data Analyst</h4><p>Remote · India</p><div class="tg"><span>Fresher ok</span><span>Python</span></div><div class="ap">Review application</div></div>
<div class="fan f4"><div class="top">{logo_small("#C2255C","F")}Flipkart<span class="sal">₹14–19 LPA</span></div><h4>Product Analyst II</h4><p>Bengaluru · Hybrid</p><div class="tg"><span>3–5 yrs</span><span>A/B tests</span></div><div class="ap">Review application</div></div>'''

    floats = f'''
<div class="float g fl1"><span class="b">{ic("shield-check",16)}</span><span>14 of 14 lines backed<small>by facts you confirmed</small></span></div>
<div class="float a fl2"><span class="b">{ic("lock",16)}</span><span>Nothing sent until you approve<small>one tap, from your phone</small></span></div>
<div class="float a fl4"><span class="b">{ic("receipt-text",16)}</span><span>Receipt AS-24817<small>time, employer, file sent</small></span></div>'''
    mfl = f'''<div class="mfl"><span class="chip">{ic("shield-check",14)}14 of 14 lines backed</span><span class="chip">{ic("lock",14)}Nothing sent until you approve</span><span class="chip">{ic("receipt-text",14)}Receipt for every send</span></div>'''

    core = f'''<div class="core"><div class="hd2"><span class="lg">R</span><div><b>Product Analyst</b><span>Razorpay · Bengaluru · ₹14–18 LPA</span></div><span class="fit">92% fit</span></div>
<div class="ln ok"><span class="st">{ic("check",13)}</span><p>Built SQL dashboards tracking checkout drop-off across 3 payment flows.</p><span class="tag">F2 F7</span></div>
<div class="ln ok"><span class="st">{ic("check",13)}</span><p>Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.</p><span class="tag">F4</span></div>
<div class="ln no"><span class="st">{ic("x",13)}</span><div><p>Led a team of 6 analysts.</p><span class="why">No matching fact · removed</span></div><span></span></div>
<div class="ft"><small>3 lines checked · 1 removed</small><span class="btn dark sm">Approve &amp; send</span></div></div>'''

    hero = f'''<section class="hero" id="top"><div class="wrap"><span class="eyebrow"><b>New</b>Every resume line linked to a fact {ic("arrow-right",13)}</span>
<h1 class="hd">Find jobs that fit. Apply with every line <em>true.</em></h1>
<p class="sub">ApplyScout finds roles for you, tailors your resume using only facts you've confirmed, and waits for your approval before anything is sent.</p>
<div class="prompt"><span class="ph">{ic("sparkles",22)}</span><span class="q">Product analyst jobs in Bengaluru, ₹10–18 LPA<i></i></span><a class="btn dark lg" href="#">{ic("upload",18)}Upload resume</a></div>
<div class="pop"><small>Popular searches</small><span class="chip">Data Analyst</span><span class="chip on">Product Analyst</span><span class="chip">Business Analyst</span><span class="chip">Associate PM</span><span class="chip">SDE I</span><span class="chip">Marketing</span></div>
<div class="fine"><span>{ic("check",14)}10 free applications</span><span>{ic("check",14)}No card needed</span><span>{ic("check",14)}Pay in ₹ with UPI</span></div></div>
<div class="stage" aria-label="Example of a tailored resume with fact checks">{fans}{core}{floats}{mfl}</div></section>'''

    srcs = '''<div class="wrap"><div class="srcs"><small>Finds roles on</small><span>Greenhouse</span><span>Lever</span><span>Workday</span><span>Ashby</span><span>Company career pages</span><span>LinkedIn hiring posts</span></div></div>'''

    def step(n, h, d, icn, col): return f'<div class="step"><span class="n">0{n}</span><div class="ico" style="background:{col}">{ic(icn,26)}</div><h3>{h}</h3><p>{d}</p></div>'
    how = f'''<section class="sec" id="how"><div class="wrap center"><span class="kick">{ic("route",15)}How it works</span><h2 class="t">From search to sent, <em>you stay in charge</em></h2><p class="lead">Four steps. You approve the one that matters.</p>
<div class="steps">{step(1,"Find","Roles from six sources, ranked by how well your real experience fits.","search","var(--c1)")}{step(2,"Tailor","Your resume rewritten for each job. Each line is linked to a fact you confirmed.","file-pen-line","var(--c2)")}{step(3,"Approve","See exactly what will be sent. One tap to send, or edit first.","circle-check-big","var(--c3)")}{step(4,"Track","A receipt for every send, plus replies and reminders in one place.","chart-no-axes-column","var(--c4)")}</div></div></section>'''

    proof = f'''<section class="sec" id="proof"><div class="wrap proof"><div><span class="kick">{ic("shield-check",15)}Built for trust</span><h2 class="t">Tailored for the job. <em>True to you.</em></h2>
<p class="lead">Other tools rewrite your resume and hope it holds up in the interview. Maggie only uses what you've confirmed, shows the proof for each line, and removes anything she can't back up.</p><p style="margin-top:26px"><a class="btn acc lg" href="#">See a tailored resume {ic("arrow-right",17)}</a></p></div>
<div class="ba"><div class="doc"><p class="k">Your resume</p><ul><li><span class="d"></span>Worked on merchant offers dashboard</li><li><span class="d"></span>Did A/B tests for onboarding</li><li><span class="d"></span>Helped the team with reports</li></ul></div>
<div class="arr">{ic("arrow-right",18)}</div><div class="doc after"><p class="k">For Razorpay · Product Analyst</p><ul>
<li><span style="color:var(--ok)">{ic("check",16)}</span><span>Built SQL dashboards tracking checkout drop-off across 3 payment flows. <span class="tag">F2</span></span></li>
<li><span style="color:var(--ok)">{ic("check",16)}</span><span>Ran 4 A/B tests on onboarding copy; one lifted activation by 9%. <span class="tag">F4</span></span></li>
<li><span style="color:var(--err)">{ic("x",16)}</span><span style="color:var(--ink3);text-decoration:line-through;text-decoration-color:var(--err)">Led a cross-functional team of 6.</span></li></ul></div></div></div></section>'''

    def job(l, c, t, co, m, tg, sal, fit): return f'''<div class="job">{logo_small(c, l).replace('class="lg"','class="lg"')}<div><h4>{t}</h4><div class="m">{co} · {m}</div><div class="tags">{"".join(f"<span>{x}</span>" for x in tg)}<span class="g">{fit}% fit</span></div></div><div class="side"><b>{sal}</b><small>per year</small><a class="btn dark sm" href="#">Review</a></div></div>'''
    jobs = f'''<section class="sec" id="jobs"><div class="wrap"><div class="center"><span class="kick">{ic("briefcase-business",15)}Matches</span><h2 class="t">Jobs that actually <em>fit you</em></h2><p class="lead">Each match says why: the skills you have and the ones you don't.</p></div>
<div class="jobs">{job("R","#2D6CDF","Product Analyst","Razorpay","Bengaluru",["0–3 yrs","SQL","6 of 8 skills"],"₹14–18 LPA",92)}{job("S","#E8590C","Associate Product Manager","Swiggy","Bengaluru · Hybrid",["Fresher ok","Analytics","5 of 7 skills"],"₹12–16 LPA",88)}{job("Z","#7048E8","Business Analyst","Zerodha","Bengaluru",["1–3 yrs","Excel","7 of 9 skills"],"₹10–14 LPA",84)}{job("M","#0B7285","Data Analyst","Meesho","Remote · India",["Fresher ok","Python","4 of 6 skills"],"₹9–13 LPA",81)}</div>
<p class="note">Example data for this design.</p></div></section>'''

    chat = f'''<section class="sec"><div class="wrap chat"><div><span class="kick">{ic("sparkles",15)}Ask Maggie</span><h2 class="t">Your personal agent, <em>honest by design</em></h2><p class="lead">Ask in plain words. Maggie finds roles, explains the fit, and shows exactly what she would send, never anything you haven't confirmed.</p>
<div class="sugg" style="margin-top:26px"><span class="chip">{ic("search",14)}Find remote data analyst jobs</span><span class="chip">{ic("target",14)}Which skills am I missing?</span><span class="chip">{ic("eye",14)}Show what you'll send to Swiggy</span><span class="chip">{ic("circle-help",14)}Why did you remove a line?</span></div></div>
<div class="chatbox"><div class="who"><span class="av">{ic("sparkles",18)}</span><span>Maggie<br><small style="font-weight:500;color:var(--ink3)">Your application agent</small></span></div>
<div class="msg u">Which skills am I missing for the Razorpay role?</div>
<div class="msg m">You match 6 of 8 skills. Two aren't in your facts yet:<div class="mini"><div><span style="color:var(--ok)">{ic("check",15)}</span>SQL, A/B testing, payments, reporting</div><div><span style="color:var(--err)">{ic("minus",15)}</span>Python, dbt. Add them only if they're true.</div></div></div>
<div class="msg u">Show what you'll send</div><div class="msg m">14 lines, all backed by your facts. One removed: "Led a team of 6". <span class="tag">receipt after you approve</span></div></div></div></section>'''

    cmp = f'''<section class="sec"><div class="wrap"><div class="center"><span class="kick">{ic("git-compare",15)}Why it's different</span><h2 class="t">Most auto-apply tools write what sounds good. <em>We write what's true.</em></h2></div>
<div class="cmp"><div class="cmpc"><h3>Typical auto-apply</h3><ul><li><span class="x">{ic("x",14)}</span>Invents skills and titles to match keywords</li><li><span class="x">{ic("x",14)}</span>Sends hundreds of applications in the background</li><li><span class="x">{ic("x",14)}</span>No record of what was sent</li><li><span class="x">{ic("x",14)}</span>Dollar billing, hard to cancel</li></ul></div>
<div class="cmpc good"><h3>ApplyScout</h3><ul><li><span class="v">{ic("check",14)}</span>Only your confirmed facts, with the proof shown</li><li><span class="v">{ic("check",14)}</span>Fewer, better applications, each approved by you</li><li><span class="v">{ic("check",14)}</span>A receipt for every send</li><li><span class="v">{ic("check",14)}</span>Priced in ₹, GST included, cancel in one tap</li></ul></div></div></div></section>'''

    aud = f'''<section class="sec"><div class="wrap"><div class="center"><span class="kick">{ic("users",15)}Built for your stage</span><h2 class="t">First job or fifth year. <em>Same honest resume.</em></h2></div><div class="aud">
<div style="background:var(--c1)"><span class="ico">{ic("graduation-cap",24)}</span><h3>Freshers</h3><p>Turn projects, internships and college work into facts recruiters can check.</p><small>B.Tech 2026 · first job</small></div>
<div style="background:var(--c2)"><span class="ico">{ic("briefcase-business",24)}</span><h3>1–6 years</h3><p>Find the next step up, tailored around results you really delivered.</p><small>Analyst → Product Analyst</small></div>
<div style="background:var(--c3)"><span class="ico">{ic("shuffle",24)}</span><h3>Switching careers</h3><p>See which of your real skills transfer, and what's honestly missing.</p><small>Ops → Product</small></div></div></div></section>'''

    pricing = f'''<section class="sec" id="pricing"><div class="wrap"><div class="center"><span class="kick">{ic("indian-rupee",15)}Pricing</span><h2 class="t">Priced for a first job, <em>not a corporate card</em></h2><p class="lead">Prices include GST. Cancel in one tap. Example prices for this design.</p></div><div class="price">
<div class="plan"><span class="pn">Free</span><div class="pp">₹0</div><ul><li>{ic("check",17)}10 applications</li><li>{ic("check",17)}Truth-checked resumes</li><li>{ic("check",17)}Receipts</li></ul><a class="btn ghost" href="#">Upload resume</a></div>
<div class="plan hi"><span class="pn">Pro <span class="tg2">Recommended</span></span><div class="pp">₹299<small> / month</small></div><ul><li>{ic("check",17)}Up to 20 applications a day</li><li>{ic("check",17)}2 campaigns</li><li>{ic("check",17)}Send from your Gmail</li></ul><a class="btn" href="#">Start Pro</a></div>
<div class="plan"><span class="pn">Max</span><div class="pp">₹799<small> / month</small></div><ul><li>{ic("check",17)}Up to 50 a day</li><li>{ic("check",17)}Referral finder</li><li>{ic("check",17)}Priority tailoring</li></ul><a class="btn ghost" href="#">Start Max</a></div></div></div></section>'''

    cta = f'''<section class="cta"><span class="kick">{ic("send",15)}Your next application</span><h2 style="margin-top:20px">Apply like you mean <em>every word</em></h2><div class="sub2"><a class="btn dark lg" href="#">{ic("upload",18)}Upload your resume</a><a class="btn ghost lg" href="#">{ic("play",16)}Watch the 1-min demo</a></div><div class="fine"><span>{ic("check",14)}No card</span><span>{ic("check",14)}2-minute setup</span><span>{ic("check",14)}Cancel in one tap</span></div></section>'''
    foot = f'''<footer><div class="wrap"><div>{LOGO}<p style="margin-top:14px">Made in Bengaluru.</p></div><div class="cols"><div><b>Product</b><a href="#how">How it works</a><a href="#pricing">Pricing</a><a href="#">Changelog</a></div><div><b>Trust</b><a href="#">Privacy</a><a href="#">Security</a><a href="#">Report a scam</a></div><div><b>Company</b><a href="#">About</a><a href="#">Contact</a></div></div></div></footer>'''

    return f'''<!doctype html><html lang="en" data-theme="sky"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ApplyScout: job-portal landing (round 11)</title>
<style>{FONTS}{CSS}</style><script>try{{var t=new URLSearchParams(location.search).get('t');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<body>{nav}<main>{hero}{srcs}{how}{proof}{jobs}{chat}{cmp}{aud}{pricing}{cta}</main>{foot}</body></html>'''

if __name__ == "__main__":
    h = page()
    # LOGO uses fill vars: set them for both themes
    h = h.replace("</style>", ":root{--mark:var(--acc);--dot:#F59E0B}</style>", 1)
    open(OUT + "landing.html", "w").write(h)
    print("ok", len(h))
