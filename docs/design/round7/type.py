import os
R="/home/user/job/docs/design/round7/"
fonts=[("Inter (Display)","Inter","Linear, Figma, GitHub UI"),("Inter Tight","Inter Tight","dense headline cut"),("Geist","Geist","Vercel"),("Onest","Onest","humanist grotesk"),("Instrument Sans","Instrument Sans","used by Instrument, many startups"),("Manrope","Manrope","geometric, friendly"),("Schibsted Grotesk","Schibsted Grotesk","newsroom grotesk"),("Mona Sans","Mona Sans","GitHub marketing"),("Hanken Grotesk","Hanken Grotesk","neutral grotesk"),("Host Grotesk","Host Grotesk","neutral, compact"),("Funnel Display","Funnel Display","display only, quirky"),("Plus Jakarta Sans","Plus Jakarta Sans","common in Indian startups")]
ff=""
for fn in sorted(os.listdir(R+"fonts")):
    if fn.startswith("inter-var"): ff+="@font-face{font-family:'Inter';src:url(fonts/%s) format('woff2');font-weight:100 900;font-display:block}\n"%fn;continue
    if "devanagari" in fn or "mono" in fn: continue
    base,w,_=fn.rsplit("-",2) if False else (None,None,None)
    parts=fn.replace(".woff2","").split("-")
    w=parts[-2]; name=fn.split("-latin-")[0]
    fam={"inter-tight":"Inter Tight","onest":"Onest","instrument-sans":"Instrument Sans","manrope":"Manrope","schibsted-grotesk":"Schibsted Grotesk","mona-sans":"Mona Sans","hanken-grotesk":"Hanken Grotesk","host-grotesk":"Host Grotesk","funnel-display":"Funnel Display","geist-sans":"Geist","plus-jakarta-sans":"Plus Jakarta Sans"}[name]
    ff+="@font-face{font-family:'%s';src:url(fonts/%s) format('woff2');font-weight:%s;font-display:block}\n"%(fam,fn,w)
cells=""
for i,(label,fam,note) in enumerate(fonts):
    cells+=f"""<div class=c style="font-family:'{fam}'"><div class=lab><b>{i+1:02d}</b> {label} <span>{note}</span></div>
<h1>Apply to the right jobs.<br>Every line true.</h1>
<p>Maggie finds roles that fit, tailors your resume from facts you confirmed, and shows you each application before it goes out.</p>
<div class=row><div><div class=t>Product Analyst</div><div class=m>Razorpay · Bengaluru · ₹14–18 LPA</div></div><span class=fit>92 fit</span><button>Review</button></div>
<div class=nums>1,284 applied · ₹299/mo · 0123456789</div></div>"""
html=f"""<!doctype html><meta charset=utf-8><title>Type candidates</title><style>{ff}
body{{margin:0;background:#F4F4F2;color:#111;font-family:Inter}}
.g{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#DDD;border:1px solid #DDD;margin:32px}}
.c{{background:#fff;padding:28px 28px 24px}}
.lab{{font:500 12px/1 Inter;color:#666;margin-bottom:22px}}.lab b{{color:#111}}.lab span{{color:#999;margin-left:6px}}
h1{{font-size:38px;line-height:1.04;letter-spacing:-.03em;font-weight:600;margin:0 0 14px}}
p{{font-size:15px;line-height:1.5;color:#555;margin:0 0 18px;max-width:42ch}}
.row{{display:flex;align-items:center;gap:12px;border:1px solid #E6E6E3;border-radius:8px;padding:10px 12px}}
.row>div{{flex:1}}.t{{font-weight:600;font-size:14px}}.m{{font-size:13px;color:#666;margin-top:2px}}
.fit{{font-size:12px;font-weight:600;background:#F1F1EE;border-radius:4px;padding:3px 6px;font-variant-numeric:tabular-nums}}
button{{font:inherit;font-size:13px;font-weight:500;background:#111;color:#fff;border:0;border-radius:6px;padding:7px 12px}}
.nums{{margin-top:14px;font-size:13px;color:#777;font-variant-numeric:tabular-nums}}
</style><div class=g>{cells}</div>"""
open(R+"type-candidates.html","w").write(html)
