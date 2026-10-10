"""Round 7 generator: one markup, many palettes. Writes HTML into docs/design/round7/."""
import os, re, sys
R = "/home/user/job/docs/design/round7/"
ICONS = "/tmp/claude-0/-home-user-job/a6175851-a246-55a6-a0a4-ee0f36f9b543/scratchpad/f7/node_modules/lucide-static/icons/"

def ic(name, size=16, cls="i"):
    s = open(ICONS + name + ".svg").read()
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    head, rest = s.split(">", 1)
    head = re.sub(r'\s(width|height|class|stroke-width)="[^"]*"', "", head)
    s = head + ">" + rest
    return s.replace("<svg", f'<svg class="{cls}" width="{size}" height="{size}" stroke-width="1.5" aria-hidden="true"', 1).strip()

LOGO = open("/home/user/job/docs/brand/kit/applyscout-horizontal.svg").read()
LOGO = re.sub(r"<title>.*?</title>", "", LOGO)
LOGO = LOGO.replace('fill="#4F46E5"', 'fill="var(--mark)"').replace('fill="#F59E0B"', 'fill="var(--dot)"').replace('fill="#111827"', 'fill="var(--ink)"')
LOGO = LOGO.replace('<svg ', '<svg class="logo" ', 1)
SYM = open("/home/user/job/docs/brand/kit/applyscout-symbol.svg").read()
SYM = re.sub(r"<title>.*?</title>", "", SYM).replace('fill="#4F46E5"', 'fill="var(--mark)"').replace('fill="#F59E0B"', 'fill="var(--dot)"').replace("<svg ", '<svg class="sym" ', 1)

# ---------- palettes ----------
BASE = dict(ok="#157A46", oksoft="#E7F4EC", warn="#8A5300", warnsoft="#FCF1DC", err="#B42318", errsoft="#FDECEA")
P = {
 "cobalt": dict(stage="#1F4FE0", name="Cobalt + marigold", bg="#FBFBF9", surf="#FFFFFF", sunk="#F3F3F0", ink="#0C0D10", ink2="#3B3E46", ink3="#62666F", line="#E6E5E0", line2="#D6D5CF",
                pri="#1F4FE0", onpri="#FFFFFF", prih="#1A43C2", mark="#1F4FE0", dot="#F2A51A", acc="#F2A51A", soft="#EDF1FD", softtx="#1A3FB0", link="#1F4FE0", band="#0C0D10", bandink="#F4F4F2", bandmut="#A3A6AD", bandline="#26282D", **BASE),
 "forest": dict(stage="#0F4A33", name="Forest + lime", bg="#F7F7F2", surf="#FFFFFF", sunk="#EFEFE8", ink="#0E1712", ink2="#36403A", ink3="#5D6660", line="#E2E3DB", line2="#D2D4CA",
                pri="#0F4A33", onpri="#FFFFFF", prih="#0B3A28", mark="#0F4A33", dot="#B5E06A", acc="#B5E06A", soft="#E6EFE9", softtx="#0F4A33", link="#0F6A47", band="#0F2A1E", bandink="#F2F5EF", bandmut="#A3B3A8", bandline="#1E3D2F", **BASE),
 "vermilion": dict(stage="#C9361A", name="Ink + vermilion", bg="#FAF8F5", surf="#FFFFFF", sunk="#F3F0EB", ink="#15110F", ink2="#423B37", ink3="#6A625C", line="#E8E3DD", line2="#D9D2CA",
                pri="#C9361A", onpri="#FFFFFF", prih="#AD2D14", mark="#15110F", dot="#E2401F", acc="#E2401F", soft="#FBECE7", softtx="#9E2B13", link="#B3301A", band="#15110F", bandink="#F6F2EE", bandmut="#ABA29B", bandline="#2B2522", **BASE),
 "marigold": dict(stage="#F2A51A", name="Ink + marigold", bg="#FBF9F4", surf="#FFFFFF", sunk="#F4F1E9", ink="#16130E", ink2="#433D33", ink3="#6B6458", line="#E8E3D8", line2="#D9D2C3",
                pri="#16130E", onpri="#FFFFFF", prih="#2E2920", mark="#16130E", dot="#F2A51A", acc="#F2A51A", soft="#FDF1D6", softtx="#7A4B00", link="#8A5A00", band="#16130E", bandink="#F7F3EA", bandmut="#ADA493", bandline="#2C271F", **BASE),
 "wine": dict(stage="#7A1B3A", name="Wine + gold", bg="#FAF8F7", surf="#FFFFFF", sunk="#F3EFEE", ink="#1A1013", ink2="#45393C", ink3="#6C6064", line="#E9E2E2", line2="#DAD0D1",
                pri="#7A1B3A", onpri="#FFFFFF", prih="#64142F", mark="#7A1B3A", dot="#E3B44B", acc="#E3B44B", soft="#F6E9ED", softtx="#6B1733", link="#8A1F42", band="#2A0E18", bandink="#F7EFF1", bandmut="#B9A1A9", bandline="#41202B", **BASE),
 "midnight": dict(stage="#1A1C21", name="Midnight (dark)", bg="#0A0B0D", surf="#121316", sunk="#0E0F11", ink="#ECEDEF", ink2="#B3B6BC", ink3="#8B8F97", line="#22242A", line2="#2D3037",
                pri="#ECEDEF", onpri="#0A0B0D", prih="#FFFFFF", mark="#ECEDEF", dot="#F2A51A", acc="#F2A51A", soft="#1A2131", softtx="#A9C0FF", link="#8FB0FF", band="#121316", bandink="#ECEDEF", bandmut="#8B8F97", bandline="#22242A",
                ok="#4CC38A", oksoft="#10271C", warn="#F0B34A", warnsoft="#2A2010", err="#FF7A70", errsoft="#2E1513"),
}

def fontfaces():
    out = "@font-face{font-family:'Inter';src:url(fonts/inter-var-opsz.woff2) format('woff2');font-weight:100 900;font-display:block}\n"
    for w in (400, 500):
        out += f"@font-face{{font-family:'Geist Mono';src:url(fonts/geist-mono-latin-{w}-normal.woff2) format('woff2');font-weight:{w};font-display:block}}\n"
    for w in (400, 500, 600):
        out += f"@font-face{{font-family:'Noto Sans Devanagari';src:url(fonts/noto-sans-devanagari-devanagari-{w}-normal.woff2) format('woff2');font-weight:{w};font-display:block}}\n"
    return out

def vars_css(p, sel=":root"):
    return sel + "{" + ";".join(f"--{k}:{v}" for k, v in p.items() if k != "name") + "}"

CSS = r"""
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:400 15px/1.55 Inter,'Noto Sans Devanagari',system-ui,sans-serif;font-optical-sizing:auto;-webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss01"}
a{color:inherit;text-decoration:none}
button{font:inherit;color:inherit}
.i{flex:none;vertical-align:-3px}
.num,.tab{font-variant-numeric:tabular-nums}
.mono{font-family:'Geist Mono',ui-monospace,monospace;font-size:12px;letter-spacing:0}
.wrap{max-width:1200px;margin:0 auto;padding:0 32px}
.skip{position:absolute;left:-999px}.skip:focus{left:16px;top:12px;z-index:9;background:var(--surf);padding:8px 12px;border-radius:6px}
:focus-visible{outline:2px solid var(--link);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 16px;border-radius:8px;border:1px solid transparent;font-weight:500;font-size:14.5px;letter-spacing:-.005em;cursor:pointer;white-space:nowrap;transition:background-color .12s,border-color .12s}
.btn.lg{height:48px;padding:0 20px;font-size:15.5px;border-radius:10px}
.btn.sm{height:34px;padding:0 12px;font-size:13.5px;border-radius:7px}
.btn.pri{background:var(--pri);color:var(--onpri)}.btn.pri:hover{background:var(--prih)}
.btn.sec{background:var(--surf);border-color:var(--line2);color:var(--ink)}.btn.sec:hover{background:var(--sunk)}
.btn.gh{background:transparent;color:var(--ink2)}.btn.gh:hover{background:var(--sunk);color:var(--ink)}
.kbd{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 4px;border:1px solid var(--line2);border-bottom-width:2px;border-radius:4px;font:500 11px/1 Inter;color:var(--ink3);background:var(--surf)}
.btn.pri .kbd{background:transparent;border-color:color-mix(in srgb,var(--onpri) 35%,transparent);color:color-mix(in srgb,var(--onpri) 75%,transparent)}

/* nav */
.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:saturate(1.4) blur(12px);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;height:64px;gap:40px}
.logo{height:30px;width:auto;display:block}
.top nav{display:flex;gap:4px;flex:1}
.top nav a{padding:6px 10px;border-radius:6px;color:var(--ink2);font-size:14.5px;font-weight:450}
.top nav a:hover{color:var(--ink);background:var(--sunk)}
.top .r{display:flex;gap:8px;align-items:center}

/* hero */
.hero{padding:88px 0 0;text-align:center}
.pill{display:inline-flex;align-items:center;gap:8px;height:30px;padding:0 12px 0 6px;border:1px solid var(--line2);border-radius:99px;font-size:13px;color:var(--ink2);background:var(--surf)}
.pill b{font-weight:600;font-size:11.5px;padding:2px 7px;border-radius:99px;background:var(--soft);color:var(--softtx)}
h1.d{font-size:clamp(40px,6.4vw,76px);line-height:1.0;letter-spacing:-.045em;font-weight:620;margin:24px auto 22px;max-width:15ch;text-wrap:balance}
h1.d em{font-style:normal;color:var(--ink3)}
.lede{font-size:clamp(17px,1.5vw,19px);line-height:1.5;color:var(--ink2);max-width:40em;margin:0 auto 32px;text-wrap:pretty;letter-spacing:-.01em}
.ctas{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.fine{margin-top:16px;font-size:13px;color:var(--ink3);display:flex;gap:18px;justify-content:center;flex-wrap:wrap}
.fine span{display:inline-flex;gap:6px;align-items:center}

/* product frame */
.stage{margin:64px auto 0;max-width:1264px;padding:56px 56px 0;position:relative;background:var(--stage);border-radius:20px;overflow:hidden;height:600px}
.stage .frame{box-shadow:0 30px 80px -20px rgba(0,0,0,.45)}
.frame{border:1px solid var(--line2);border-radius:14px;background:var(--surf);overflow:hidden;box-shadow:0 1px 0 var(--line),0 24px 60px -24px rgba(16,18,24,.22),0 8px 20px -12px rgba(16,18,24,.12);text-align:left}
.dark .frame{box-shadow:0 0 0 1px #000,0 30px 80px -20px rgba(0,0,0,.7)}

/* app shell */
.app{display:grid;grid-template-columns:232px 1fr 400px;height:640px;font-size:13.5px}
.app.full{height:760px}
.side{background:var(--sunk);border-right:1px solid var(--line);padding:14px 10px;display:flex;flex-direction:column;gap:2px}
.ws{display:flex;align-items:center;gap:8px;padding:6px 8px 14px;font-weight:600;font-size:14px}
.ws .sym{width:20px;height:20px}
.ws .av{margin-left:auto;width:22px;height:22px;border-radius:99px;background:var(--soft);color:var(--softtx);font-size:10.5px;font-weight:600;display:grid;place-items:center}
.search{white-space:nowrap;display:flex;align-items:center;gap:8px;height:32px;padding:0 8px;border:1px solid var(--line);background:var(--surf);border-radius:7px;color:var(--ink3);margin-bottom:12px}
.search .kbd{margin-left:auto}
.ni{display:flex;align-items:center;gap:10px;height:32px;padding:0 8px;border-radius:7px;color:var(--ink2);font-weight:450}
.ni .c{margin-left:auto;font-size:12px;color:var(--ink3)}
.ni.on{background:var(--surf);color:var(--ink);font-weight:550;box-shadow:0 0 0 1px var(--line)}
.ni.on .c{color:var(--ink2)}
.sh{font-size:11.5px;font-weight:550;color:var(--ink3);padding:16px 8px 6px;letter-spacing:.01em}
.camp{display:flex;align-items:center;gap:10px;height:30px;padding:0 8px;color:var(--ink2);border-radius:7px}
.dotc{width:8px;height:8px;border-radius:99px;flex:none}
.side .foot{margin-top:auto;border-top:1px solid var(--line);padding:12px 8px 2px;font-size:12px;color:var(--ink3)}
.meter{height:4px;border-radius:9px;background:var(--line);margin:8px 0 6px;overflow:hidden}.meter i{display:block;height:100%;width:62%;background:var(--pri)}

.main{display:flex;flex-direction:column;min-width:0;border-right:1px solid var(--line)}
.mh{display:flex;align-items:center;gap:12px;height:52px;padding:0 20px;border-bottom:1px solid var(--line)}
.mh h2{font-size:15px;font-weight:600;margin:0;letter-spacing:-.01em}
.mh .sub{color:var(--ink3)}
.mh .r{margin-left:auto;display:flex;gap:6px}
.tabs{display:flex;gap:2px;padding:10px 16px;border-bottom:1px solid var(--line)}
.tb{display:inline-flex;gap:6px;align-items:center;height:28px;padding:0 10px;border-radius:6px;color:var(--ink2);font-weight:500;font-size:13px}
.tb .c{font-size:12px;color:var(--ink3)}
.tb.on{background:var(--sunk);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line)}
.grp{display:flex;align-items:center;gap:8px;padding:14px 20px 6px;font-size:12px;font-weight:550;color:var(--ink3)}
.row{display:grid;grid-template-columns:28px 1fr auto auto;align-items:center;gap:12px;padding:10px 20px;border-bottom:1px solid var(--line)}
.row.sel{background:var(--soft);box-shadow:inset 2px 0 0 var(--pri)}
.dark .row.sel{box-shadow:inset 2px 0 0 var(--link)}
.co{width:28px;height:28px;border-radius:7px;display:grid;place-items:center;font-weight:650;font-size:12px;color:#fff}
.rt{font-weight:550;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rm{color:var(--ink3);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fit{font-size:12px;font-weight:600;color:var(--ink2);display:inline-flex;align-items:center;gap:6px}
.fitbar{width:36px;height:4px;border-radius:9px;background:var(--line);overflow:hidden}.fitbar i{display:block;height:100%;background:var(--ink2)}
.st{display:inline-flex;align-items:center;gap:6px;height:22px;padding:0 8px;border-radius:6px;font-size:12px;font-weight:550;white-space:nowrap}
.st.need{background:var(--warnsoft);color:var(--warn)}
.st.ready{background:var(--oksoft);color:var(--ok)}
.st.prep{background:var(--sunk);color:var(--ink2);box-shadow:inset 0 0 0 1px var(--line)}
.st.sent{background:transparent;color:var(--ink3);box-shadow:inset 0 0 0 1px var(--line)}
.st.blk{background:var(--errsoft);color:var(--err)}

.det{display:flex;flex-direction:column;min-width:0;background:var(--surf)}
.dh{padding:16px 20px 14px;border-bottom:1px solid var(--line)}
.dh .crumb{font-size:12px;color:var(--ink3);display:flex;gap:6px;align-items:center}
.dh h3{margin:6px 0 2px;font-size:17px;letter-spacing:-.015em;font-weight:600}
.dh .m{color:var(--ink3);font-size:12.5px}
.why{padding:14px 20px;border-bottom:1px solid var(--line)}
.lbl{font-size:11.5px;font-weight:550;color:var(--ink3);margin-bottom:8px;display:flex;align-items:center;gap:6px;letter-spacing:.01em}
.reasons{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;gap:5px;height:24px;padding:0 8px;border-radius:6px;font-size:12px;background:var(--sunk);color:var(--ink2);box-shadow:inset 0 0 0 1px var(--line)}
.chip.miss{background:transparent;color:var(--ink3);box-shadow:inset 0 0 0 1px var(--line2);border:0}
.lines{padding:14px 20px;flex:1;overflow:hidden}
.ln{display:grid;grid-template-columns:18px 1fr;gap:10px;padding:8px 0;border-bottom:1px dashed var(--line)}
.ln:last-child{border-bottom:0}
.ln .t{color:var(--ink);line-height:1.45}
.ln .ev{display:flex;gap:6px;margin-top:5px;align-items:center;font-size:11.5px;color:var(--ink3)}
.fact{font-family:'Geist Mono',monospace;font-size:11px;padding:1px 5px;border-radius:4px;background:var(--soft);color:var(--softtx)}
.ln .ok{color:var(--ok)}.ln .bad{color:var(--err)}
.ln.flag .t{color:var(--ink2);text-decoration:line-through;text-decoration-color:var(--err)}
.ln .fx{display:flex;gap:6px;margin-top:6px}
.q{margin-top:14px;border:1px solid color-mix(in srgb,var(--dot) 55%,var(--line));background:color-mix(in srgb,var(--soft) 60%,var(--surf));border-radius:10px;padding:12px 14px}
.df{border-top:1px solid var(--line);padding:12px 20px;display:flex;align-items:center;gap:8px;background:var(--surf)}
.df .note{font-size:12px;color:var(--ink3);margin-right:auto;display:flex;gap:6px;align-items:center}

/* sections */
.strip{padding:72px 0 8px;text-align:center}
.strip p{font-size:13px;color:var(--ink3);margin:0 0 18px}
.srcs{display:flex;justify-content:center;gap:44px;flex-wrap:wrap;color:var(--ink2);font-weight:600;font-size:17px;letter-spacing:-.02em;opacity:.8}
.sect{padding:120px 0 0}
.eyebrow{font-size:13px;font-weight:550;color:var(--link);margin-bottom:14px;display:flex;align-items:center;gap:8px}
.dark .eyebrow{color:var(--link)}
h2.h{font-size:clamp(30px,3.6vw,46px);line-height:1.05;letter-spacing:-.035em;font-weight:620;margin:0 0 16px;max-width:18ch;text-wrap:balance}
h2.h em{font-style:normal;color:var(--ink3)}
.sect .lede{margin:0;text-align:left;max-width:34em}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:56px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--surf)}
.cell{padding:28px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:6px}
.cell:last-child{border-right:0}
.cell .n{font-size:12px;color:var(--ink3);font-weight:550;display:flex;gap:8px;align-items:center}
.cell h4{margin:8px 0 2px;font-size:18px;letter-spacing:-.02em;font-weight:600}
.cell p{margin:0;color:var(--ink2);font-size:14.5px}
.mini{margin-top:22px;border:1px solid var(--line);border-radius:10px;background:var(--bg);padding:12px;font-size:12.5px;display:flex;flex-direction:column;gap:8px}
.mini .r{display:flex;align-items:center;gap:8px}
.mini .r .t{flex:1;font-weight:500}

.band{background:var(--band);color:var(--bandink);margin-top:120px;padding:110px 0}
.band .eyebrow{color:var(--dot)}
.band h2.h em{color:var(--bandmut)}
.band .lede{color:var(--bandmut)}
.split{display:grid;grid-template-columns:1fr 1fr;gap:72px;align-items:center}
.ticks{list-style:none;padding:0;margin:28px 0 0;display:grid;gap:14px}
.ticks li{display:grid;grid-template-columns:22px 1fr;gap:10px;color:var(--bandink);font-size:15px}
.ticks li span{color:var(--bandmut);display:block;font-size:14px}
.receipt{background:var(--surf);color:var(--ink);border-radius:14px;border:1px solid var(--bandline);padding:22px;box-shadow:0 30px 80px -30px rgba(0,0,0,.5)}
.receipt .hd{display:flex;align-items:center;gap:10px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.receipt .kv{display:grid;grid-template-columns:120px 1fr;gap:8px 12px;padding:14px 0;font-size:13.5px;border-bottom:1px solid var(--line)}
.receipt .kv dt{color:var(--ink3)}.receipt .kv dd{margin:0}
.receipt .ft{display:flex;gap:8px;padding-top:14px;align-items:center}

.price{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:56px}
.plan{border:1px solid var(--line);border-radius:14px;padding:26px;background:var(--surf);display:flex;flex-direction:column;gap:6px}
.plan.hi{border-color:var(--ink);box-shadow:0 0 0 1px var(--ink)}
.plan .pn{font-weight:600;font-size:15px;display:flex;align-items:center;gap:8px}
.plan .pp{font-size:40px;font-weight:620;letter-spacing:-.04em;margin:10px 0 0}
.plan .pp small{font-size:14px;color:var(--ink3);font-weight:450;letter-spacing:0}
.plan ul{list-style:none;padding:0;margin:16px 0 22px;display:grid;gap:9px;font-size:14px;color:var(--ink2)}
.plan li{display:flex;gap:8px;align-items:center}
.plan .btn{margin-top:auto;justify-content:center}
.tag{font-size:11.5px;font-weight:600;padding:2px 8px;border-radius:99px;background:var(--soft);color:var(--softtx)}
footer{margin-top:120px;border-top:1px solid var(--line);padding:40px 0 56px;color:var(--ink3);font-size:13.5px}
footer .wrap{display:flex;gap:40px;align-items:flex-start}
footer .cols{display:flex;gap:64px;margin-left:auto}
footer .cols div{display:grid;gap:8px;align-content:start}
footer b{color:var(--ink);font-weight:550}

/* phone */
.phone{width:390px;min-height:844px;background:var(--bg);position:relative;overflow:hidden;font-size:15px}
.pbar{display:flex;align-items:center;justify-content:space-between;height:56px;padding:0 16px;border-bottom:1px solid var(--line);background:var(--bg)}
.pbar .logo{height:22px}
.ph{padding:20px 16px 8px}
.ph .hi{font-size:13px;color:var(--ink3)}
.ph h2{margin:2px 0 0;font-size:24px;letter-spacing:-.03em;font-weight:620;line-height:1.15}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:12px 16px}
.kpi{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--surf)}
.kpi b{display:block;font-size:22px;letter-spacing:-.03em;font-weight:620}
.kpi span{font-size:12px;color:var(--ink3)}
.kpi.need{border-color:color-mix(in srgb,var(--warn) 40%,var(--line))}
.plist{margin:8px 16px;border:1px solid var(--line);border-radius:14px;background:var(--surf);overflow:hidden}
.pr{display:grid;grid-template-columns:36px 1fr auto;gap:12px;align-items:center;padding:14px;border-bottom:1px solid var(--line);min-height:68px}
.pr:last-child{border-bottom:0}
.pr .co{width:36px;height:36px;border-radius:9px;font-size:14px}
.pr .rt{font-size:15px}.pr .rm{font-size:13px}
.ptabs{position:absolute;left:0;right:0;bottom:0;height:72px;border-top:1px solid var(--line);background:var(--surf);display:grid;grid-template-columns:repeat(4,1fr);padding-bottom:12px}
.pt{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;font-size:11.5px;color:var(--ink3);font-weight:500;position:relative}
.pt.on{color:var(--ink)}
.pt .bd{position:absolute;top:8px;left:calc(50% + 6px);min-width:16px;height:16px;border-radius:99px;background:var(--pri);color:var(--onpri);font-size:10px;font-weight:600;display:grid;place-items:center;padding:0 4px}
.sheet{position:absolute;left:0;right:0;bottom:0;background:var(--surf);border-radius:18px 18px 0 0;border-top:1px solid var(--line2);box-shadow:0 -20px 60px -20px rgba(0,0,0,.25);padding:8px 16px 20px}
.grab{width:36px;height:4px;border-radius:9px;background:var(--line2);margin:0 auto 12px}
.scrim{position:absolute;inset:0;background:rgba(10,10,12,.38)}
.pland{padding:28px 16px 0}
.pland h1.d{font-size:44px;text-align:left;margin:18px 0 16px;letter-spacing:-.045em}
.pland .lede{text-align:left;font-size:17px;margin:0 0 24px}
.pland .btn.lg{width:100%;justify-content:center;height:52px}
"""

def co(letter, color):
    return f'<span class="co" style="background:{color}" aria-hidden="true">{letter}</span>'

JOBS = [
  ("R", "#2D6CDF", "Product Analyst", "Razorpay · Bengaluru · ₹14–18 LPA", 92, "need", "Answer 1 question"),
  ("S", "#E8590C", "Associate Product Manager", "Swiggy · Bengaluru · Hybrid", 88, "ready", "Ready to send"),
  ("Z", "#7048E8", "Business Analyst", "Zerodha · Bengaluru · On-site", 84, "ready", "Ready to send"),
  ("M", "#0B7285", "Data Analyst", "Meesho · Remote · ₹10–14 LPA", 81, "prep", "Tailoring…"),
  ("P", "#5F3DC4", "Product Analyst II", "PhonePe · Pune · Hybrid", 79, "blk", "Can't send yet"),
  ("C", "#212529", "Growth Analyst", "CRED · Bengaluru · On-site", 77, "sent", "Sent 2h ago"),
  ("F", "#C2255C", "Associate PM, Payments", "Flipkart · Bengaluru", 74, "sent", "Sent yesterday"),
]
STI = {"need": "circle-alert", "ready": "circle-check", "prep": "loader", "blk": "octagon-x", "sent": "send"}

def row(j, sel=False):
    L, c, t, m, f, s, lab = j
    return f'''<div class="row{' sel' if sel else ''}">{co(L,c)}<div style="min-width:0"><div class="rt">{t}</div><div class="rm">{m}</div></div>
<span class="fit num" title="Fit score">{f}<span class="fitbar"><i style="width:{f}%"></i></span></span><span class="st {s}">{ic(STI[s],13)}{lab}</span></div>'''

def sidebar():
    nav = [("sun", "Today", "3", True), ("sparkles", "Matches", "24", False), ("send", "Applications", "41", False), ("file-check-2", "Resume facts", "18", False), ("settings-2", "Settings", "", False)]
    items = "".join(f'<a class="ni{" on" if on else ""}" href="#">{ic(i,16)}{t}<span class="c num">{c}</span></a>' for i, t, c, on in nav)
    return f'''<aside class="side"><div class="ws">{SYM}ApplyScout<span class="av">PS</span></div>
<div class="search">{ic("search",14)}Search<span class="kbd">/</span></div>{items}
<div class="sh">Campaigns</div>
<a class="camp" href="#"><span class="dotc" style="background:var(--pri)"></span>Product Analyst · BLR<span class="c num" style="margin-left:auto;color:var(--ink3);font-size:12px">12</span></a>
<a class="camp" href="#"><span class="dotc" style="background:var(--dot)"></span>APM · Remote<span class="c num" style="margin-left:auto;color:var(--ink3);font-size:12px">7</span></a>
<a class="camp" href="#" style="color:var(--ink3)">{ic("plus",14)}New campaign</a>
<div class="foot"><div style="display:flex;justify-content:space-between"><span>Today's limit</span><span class="num">13 of 20</span></div><div class="meter"><i></i></div>Resets at midnight</div></aside>'''

def detail():
    return f'''<section class="det" aria-label="Application detail"><div class="dh"><div class="crumb">{co("R","#2D6CDF").replace('class="co"','class="co" style="width:18px;height:18px;font-size:10px;border-radius:5px;background:#2D6CDF"')} Razorpay {ic("chevron-right",12)} Tailored resume</div>
<h3>Product Analyst</h3><div class="m">Bengaluru · ₹14–18 LPA · Posted 2 days ago · via Greenhouse</div></div>
<div class="why"><div class="lbl">{ic("target",13)}Why it fits · 6 of 8 skills</div><div class="reasons">
<span class="chip">{ic("check",12)}SQL</span><span class="chip">{ic("check",12)}A/B testing</span><span class="chip">{ic("check",12)}Payments domain</span><span class="chip">{ic("check",12)}Stakeholder reports</span><span class="chip miss">{ic("minus",12)}Python (not in your facts)</span></div></div>
<div class="lines"><div class="lbl">{ic("shield-check",13)}Every line checked against your facts</div>
<div class="ln"><span class="ok">{ic("check",16)}</span><div><div class="t">Built SQL dashboards tracking checkout drop-off across 3 payment flows.</div><div class="ev">Backed by <span class="fact">F2</span><span class="fact">F7</span></div></div></div>
<div class="ln"><span class="ok">{ic("check",16)}</span><div><div class="t">Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.</div><div class="ev">Backed by <span class="fact">F4</span></div></div></div>
<div class="ln flag"><span class="bad">{ic("x",16)}</span><div><div class="t">Led a team of 6 analysts.</div><div class="ev" style="color:var(--err)">Not in your facts — removed before sending</div></div></div><div class="q"><div class="lbl" style="color:var(--softtx)">{ic("message-circle-question",13)}Maggie needs one answer</div><div style="font-weight:550;margin-bottom:10px">Have you used Python at work? The job lists it as a must-have.</div><div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sec sm">Yes, add as a fact</button><button class="btn sec sm">No</button><button class="btn gh sm">Skip this job</button></div></div></div>
<div class="df"><span class="note">{ic("lock",13)}Nothing is sent without you</span><button class="btn sec sm">Edit</button><button class="btn pri sm">Approve &amp; send <span class="kbd">⏎</span></button></div></section>'''

def app_window(full=False):
    rows = row(JOBS[0], True) + "".join(row(j) for j in JOBS[1:5])
    sent = "".join(row(j) for j in JOBS[5:])
    return f'''<div class="app{' full' if full else ''}">{sidebar()}<section class="main" aria-label="Today"><div class="mh"><h2>Today</h2><span class="sub">Fri, 10 Oct</span>
<div class="r"><button class="btn gh sm">{ic("list-filter",14)}Filter</button><button class="btn sec sm">{ic("refresh-cw",14)}Find more</button></div></div>
<div class="tabs"><span class="tb on">Needs you <span class="c num">1</span></span><span class="tb">Ready <span class="c num">2</span></span><span class="tb">In progress <span class="c num">2</span></span><span class="tb">Sent <span class="c num">24</span></span></div>
<div class="grp">{ic("inbox",13)}Up next</div>{rows}<div class="grp">{ic("send",13)}Sent this week</div>{sent}</section>{detail()}</div>'''

def landing(p, frame=True):
    dark = " dark" if p.get("bg", "#fff").startswith("#0") else ""
    return f'''<a class="skip" href="#m">Skip to content</a>
<header class="top"><div class="wrap"><a href="#" aria-label="ApplyScout home">{LOGO}</a>
<nav aria-label="Main"><a href="#">Product</a><a href="#">How it works</a><a href="#">Pricing</a><a href="#">For colleges</a></nav>
<div class="r"><a class="btn gh sm" href="#">Log in</a><a class="btn pri sm" href="#">Start free</a></div></div></header>
<main id="m"><section class="hero" data-shot="hero"><div class="wrap"><span class="pill"><b>New</b>Truth check on every resume line {ic("arrow-right",13)}</span>
<h1 class="d">Apply to the right jobs. <em>Every line true.</em></h1>
<p class="lede">Maggie finds roles that fit you, tailors your resume using only facts you've confirmed, and shows you every application before it goes out.</p>
<div class="ctas"><a class="btn pri lg" href="#">Start free {ic("arrow-right",16)}</a><a class="btn sec lg" href="#">{ic("play",15)}See a 2-min demo</a></div>
<div class="fine"><span>{ic("check",14)}10 free applications</span><span>{ic("check",14)}No card needed</span><span>{ic("check",14)}Pay in ₹ with UPI</span></div></div>
<div class="stage"><div class="frame">{app_window()}</div></div></section>
<section class="strip"><div class="wrap"><p>Searches roles posted on</p><div class="srcs"><span>Greenhouse</span><span>Lever</span><span>Workday</span><span>Ashby</span><span>Company career pages</span><span>LinkedIn hiring posts</span></div></div></section>
<section class="sect"><div class="wrap"><div class="eyebrow">{ic("route",15)}How it works</div><h2 class="h">Three steps. <em>You stay in charge of each one.</em></h2>
<p class="lede">No spray-and-pray. Maggie applies to fewer, better roles, and tells you why each one fits.</p>
<div class="grid3">
<div class="cell"><span class="n">01 {ic("sparkles",14)}</span><h4>Find</h4><p>Matches from 6 sources, ranked by how well your real experience fits.</p>
<div class="mini"><div class="r">{co("S","#E8590C").replace('class="co"','class="co" style="width:22px;height:22px;font-size:10px;background:#E8590C"')}<span class="t">APM · Swiggy</span><span class="num" style="color:var(--ink3)">88</span></div><div class="reasons"><span class="chip">{ic("check",12)}SQL</span><span class="chip">{ic("check",12)}Consumer apps</span><span class="chip miss">{ic("minus",12)}Figma</span></div></div></div>
<div class="cell"><span class="n">02 {ic("shield-check",14)}</span><h4>Tailor, truthfully</h4><p>Each resume line is linked to a fact you confirmed. Anything unsupported is removed.</p>
<div class="mini"><div class="r"><span class="ok" style="color:var(--ok)">{ic("check",14)}</span><span class="t">Built SQL dashboards…</span><span class="fact">F2</span></div><div class="r"><span style="color:var(--err)">{ic("x",14)}</span><span class="t" style="text-decoration:line-through;color:var(--ink3)">Led a team of 6</span><span class="st blk" style="height:20px">Removed</span></div></div></div>
<div class="cell"><span class="n">03 {ic("send",14)}</span><h4>You approve, then it's sent</h4><p>Review on your phone in seconds. Every send gets a receipt you can check later.</p>
<div class="mini"><div class="r"><span class="st ready">{ic("circle-check",13)}Ready</span><span class="t">2 applications</span><span class="btn pri sm" style="height:28px">Review</span></div></div></div>
</div></div></section>
<section class="band{dark}" data-shot="band"><div class="wrap split"><div><div class="eyebrow">{ic("lock",15)}Built for trust</div><h2 class="h">Nothing goes out without you. <em>Ever.</em></h2>
<p class="lede">Job scams are everywhere. ApplyScout never asks for fees, never invents experience and never sends in secret.</p>
<ul class="ticks"><li>{ic("eye",18)}<div>You see the exact resume and message<span>The preview is what gets sent, byte for byte.</span></div></li>
<li>{ic("receipt-text",18)}<div>A receipt for every application<span>Time, employer, channel and the file that was sent.</span></div></li>
<li>{ic("shield-alert",18)}<div>Scam and fee warnings<span>Listings that ask for money are flagged and never applied to.</span></div></li></ul></div>
<div class="receipt"><div class="hd">{ic("receipt-text",18)}<b style="font-weight:600">Application receipt</b><span class="st sent" style="margin-left:auto">{ic("check",13)}Delivered</span></div>
<dl class="kv"><dt>Role</dt><dd>Associate Product Manager</dd><dt>Company</dt><dd>Swiggy</dd><dt>Sent</dt><dd class="num">10 Oct 2026, 09:42</dd><dt>Channel</dt><dd>Your Gmail · careers@…</dd><dt>Resume</dt><dd><span class="mono">priya-apm-swiggy.pdf</span></dd><dt>Truth check</dt><dd style="color:var(--ok)">14 of 14 lines backed</dd></dl>
<div class="ft"><span style="color:var(--ink3);font-size:12.5px;margin-right:auto" class="mono">ID AS-24817</span><button class="btn sec sm">{ic("download",14)}PDF</button><button class="btn sec sm">View email</button></div></div></div></section>
<section class="sect"><div class="wrap"><div class="eyebrow">{ic("indian-rupee",15)}Pricing</div><h2 class="h">Priced for a first job, <em>not a corporate card.</em></h2>
<div class="price">
<div class="plan"><span class="pn">Free</span><div class="pp num">₹0</div><ul><li>{ic("check",15)}10 applications</li><li>{ic("check",15)}Truth-checked resumes</li><li>{ic("check",15)}Receipts</li></ul><a class="btn sec" href="#">Start free</a></div>
<div class="plan hi"><span class="pn">Pro <span class="tag">Recommended</span></span><div class="pp num">₹299<small> / month</small></div><ul><li>{ic("check",15)}Up to 20 applications a day</li><li>{ic("check",15)}2 campaigns</li><li>{ic("check",15)}Send from your Gmail</li></ul><a class="btn pri" href="#">Start Pro</a></div>
<div class="plan"><span class="pn">Max</span><div class="pp num">₹799<small> / month</small></div><ul><li>{ic("check",15)}Up to 50 a day</li><li>{ic("check",15)}Referral finder</li><li>{ic("check",15)}Priority tailoring</li></ul><a class="btn sec" href="#">Start Max</a></div>
</div><p style="margin-top:16px;font-size:13px;color:var(--ink3)">Prices include GST. Cancel in one tap. Example prices for this design only.</p></div></section></main>
<footer><div class="wrap"><div>{LOGO}<p style="margin-top:14px">Made in Bengaluru.</p></div><div class="cols"><div><b>Product</b><a href="#">How it works</a><a href="#">Pricing</a><a href="#">Changelog</a></div><div><b>Trust</b><a href="#">Privacy</a><a href="#">Report a scam</a><a href="#">Status</a></div><div><b>Company</b><a href="#">About</a><a href="#">Contact</a></div></div></div></footer>'''

def page(p, body, title="ApplyScout"):
    dark = ' class="dark"' if p["bg"].startswith("#0") else ""
    return f'<!doctype html><html lang="en"{dark}><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{fontfaces()}{vars_css(p)}{CSS}</style><body>{body}</body></html>'

def phone_today():
    rows = ""
    for L, c, t, m, f, s, lab in JOBS[:5]:
        rows += f'<div class="pr">{co(L,c)}<div style="min-width:0"><div class="rt">{t}</div><div class="rm">{m.split(" · ")[0]} · {f} fit</div></div><span class="st {s}">{ic(STI[s],13)}{lab.replace("Answer 1 question","1 question").replace("Ready to send","Ready").replace("Can\'t send yet","Blocked")}</span></div>'
    return f'''<div class="phone"><div class="pbar">{LOGO}<button class="btn gh sm" aria-label="Search">{ic("search",18)}</button></div>
<div class="ph"><div class="hi">Good morning, Priya</div><h2>3 applications are waiting on you</h2></div>
<div class="kpis"><div class="kpi need"><b class="num">1</b><span>Needs you</span></div><div class="kpi"><b class="num">2</b><span>Ready</span></div><div class="kpi"><b class="num">24</b><span>Sent this week</span></div></div>
<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px 0"><b style="font-size:14px;font-weight:600">Up next</b><a href="#" style="font-size:13px;color:var(--link);font-weight:500">See all</a></div>
<div class="plist">{rows}</div>
<nav class="ptabs" aria-label="App"><a class="pt on" href="#">{ic("sun",22)}Today<span class="bd">3</span></a><a class="pt" href="#">{ic("sparkles",22)}Matches</a><a class="pt" href="#">{ic("send",22)}Sent</a><a class="pt" href="#">{ic("user-round",22)}Me</a></nav></div>'''

def phone_review():
    return f'''<div class="phone"><div class="pbar"><button class="btn gh sm" aria-label="Back">{ic("arrow-left",18)}</button><b style="font-size:15px;font-weight:600">Review</b><span style="width:34px"></span></div>
<div class="ph" style="padding-bottom:0"><div class="hi">Razorpay · Bengaluru</div><h2>Product Analyst</h2></div>
<div style="padding:14px 16px 0"><div class="lbl">{ic("target",13)}Why it fits · 6 of 8 skills</div><div class="reasons"><span class="chip">{ic("check",12)}SQL</span><span class="chip">{ic("check",12)}A/B testing</span><span class="chip">{ic("check",12)}Payments</span><span class="chip miss">{ic("minus",12)}Python</span></div></div>
<div class="lines" style="padding:16px"><div class="lbl">{ic("shield-check",13)}Every line checked</div>
<div class="ln"><span class="ok">{ic("check",16)}</span><div><div class="t">Built SQL dashboards tracking checkout drop-off across 3 payment flows.</div><div class="ev">Backed by <span class="fact">F2</span><span class="fact">F7</span></div></div></div>
<div class="ln"><span class="ok">{ic("check",16)}</span><div><div class="t">Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.</div><div class="ev">Backed by <span class="fact">F4</span></div></div></div>
<div class="ln flag"><span class="bad">{ic("x",16)}</span><div><div class="t">Led a team of 6 analysts.</div><div class="ev" style="color:var(--err)">Not in your facts — removed</div></div></div><div class="q" style="margin-top:12px"><div class="lbl" style="color:var(--softtx)">{ic("message-circle-question",13)}Maggie needs one answer</div><div style="font-weight:550;margin-bottom:10px">Have you used Python at work?</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><button class="btn sec" style="justify-content:center;height:44px">Yes, add fact</button><button class="btn sec" style="justify-content:center;height:44px">No</button></div></div></div>
<div class="sheet" style="border-radius:0;box-shadow:none;padding-top:14px"><div style="display:flex;gap:8px;font-size:12.5px;color:var(--ink3);margin-bottom:10px;align-items:center">{ic("lock",13)}Sent from your Gmail only after you tap</div>
<div style="display:grid;grid-template-columns:auto 1fr;gap:8px"><button class="btn sec lg" style="height:52px">Edit</button><button class="btn pri lg" style="height:52px;justify-content:center">Approve &amp; send</button></div></div></div>'''

def phone_landing():
    return f'''<div class="phone"><div class="pbar">{LOGO}<button class="btn gh sm" aria-label="Menu">{ic("menu",20)}</button></div>
<div class="pland"><span class="pill"><b>New</b>Truth check on every line</span><h1 class="d">Apply to the right jobs. <em>Every line true.</em></h1>
<p class="lede">Maggie finds roles that fit, tailors your resume from facts you've confirmed, and shows you every application before it goes out.</p>
<a class="btn pri lg" href="#">Start free {ic("arrow-right",16)}</a><div class="fine" style="justify-content:flex-start;gap:14px"><span>{ic("check",14)}10 free</span><span>{ic("check",14)}No card</span><span>{ic("check",14)}UPI</span></div></div>
<div style="margin:28px 16px 0;border:1px solid var(--line2);border-radius:16px;overflow:hidden;background:var(--surf)"><div class="plist" style="margin:0;border:0;border-radius:0">
{''.join(f'<div class="pr">{co(L,c)}<div style="min-width:0"><div class="rt">{t}</div><div class="rm">{m.split(" · ")[0]} · {f} fit</div></div><span class="st {s}">{ic(STI[s],13)}{ {"need":"1 question","ready":"Ready","prep":"Tailoring"}[s]}</span></div>' for L,c,t,m,f,s,lab in JOBS[:3])}</div></div></div>'''

def phones():
    return f'<div style="display:flex;gap:32px;padding:40px;background:var(--sunk);width:max-content">{phone_landing()}{phone_today()}{phone_review()}</div>'

if __name__ == "__main__":
    for k, p in P.items():
        open(R + f"p-{k}.html", "w").write(page(p, landing(p)))
        open(R + f"p-{k}-app.html", "w").write(page(p, f'<div style="padding:40px;background:var(--sunk)"><div class="frame" style="max-width:1360px">{app_window(True)}</div></div>'))
        open(R + f"p-{k}-phone.html", "w").write(page(p, phones()))
    print("ok")

def board():
    cells=""
    for k,p in P.items():
        sw="".join(f'<i style="background:{p[x]}" title="{x}"></i>' for x in ("bg","ink","pri","dot","soft","band"))
        cells+=f'<figure><img src="shots/hero-{k}.png" alt=""><img src="shots/band-{k}.png" alt=""><figcaption><b>{p["name"]}</b><span class=sw>{sw}</span><span class=hx>primary {p["pri"]} · accent {p["dot"]}</span></figcaption></figure>'
    html=f"""<!doctype html><meta charset=utf-8><title>Colour exploration</title><style>{fontfaces()}body{{margin:0;background:#EDEDEA;font:14px Inter;color:#111;padding:32px}}h1{{font-size:22px;letter-spacing:-.02em;margin:0 0 20px;font-weight:600}}
.g{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}}figure{{margin:0;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #D9D9D4}}img{{width:100%;display:block;border-bottom:1px solid #E3E3DF}}
figcaption{{display:flex;align-items:center;gap:12px;padding:12px 14px}}.sw{{display:flex}}.sw i{{width:18px;height:18px;border-radius:99px;margin-left:-4px;box-shadow:0 0 0 2px #fff}}.hx{{margin-left:auto;color:#777;font-size:12px}}</style>
<h1>Round 7 · one layout, six palettes</h1><div class=g>{cells}</div>"""
    open(R+"palettes.html","w").write(html)
board()
