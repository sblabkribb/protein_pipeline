import sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch,Circle
sys.path.insert(0, str(Path(__file__).parent)); import figstyle; figstyle.apply()
OUT="/opt/protein_pipeline-work/docs/figures/fig1_fullflow.png"
INK="#1F2A37"
STAGES=[
 ("MMseqs2 MSA\n+ conservation tiers","30/50/70%","#E8EDF4","#4A6FA5",False),
 ("RFD3·BioEmu\nstructure context","(optional)","#D6EAF0","#2C8C9E",True),
 ("ProteinMPNN\ncandidates","~10,000 / target","#E8EDF4","#4A6FA5",False),
 ("SoluProt filter\n+ ESM-2 embed","cheap, local","#E8EDF4","#4A6FA5",False),
 ("AF2/ColabFold\nseed labels","30 calls","#FBE7CC","#C77F2E",False),
 ("Local surrogate\nmodel","per-run CV","#D8EDDE","#3E8E5E",False),
 ("AF2/ColabFold\nacquisition","Top-20 · 20 calls","#FBE7CC","#C77F2E",False),
 ("Ranked candidates\n+ run record","reproducible","#EAE1F2","#6F4B9A",False),
]
def rounded(ax,x,y,w,h,face,edge,lw=2.0,z=3,dashed=False):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=lw,edgecolor=edge,facecolor=face,zorder=z,
        linestyle=((0,(4,3)) if dashed else "solid")))
n=len(STAGES); pitch,bw,bh,y=2.85,2.3,1.9,1.35
fig,ax=plt.subplots(figsize=(22.5,5.7))
ax.set_xlim(0,n*pitch); ax.set_ylim(-0.1,5.2); ax.axis("off")
xs=[i*pitch+(pitch-bw)/2 for i in range(n)]
def band(i0,i1,face,edge,label,ly):
    x0=xs[i0]-0.16; x1=xs[i1]+bw+0.16
    ax.add_patch(FancyBboxPatch((x0,y-0.5),x1-x0,bh+1.0,boxstyle="round,pad=0.02,rounding_size=0.10",
        linewidth=1.3,edgecolor=edge,facecolor=face,linestyle=(0,(5,3)),zorder=1))
    ax.text((x0+x1)/2,ly,label,ha="center",va="center",fontsize=12,fontweight="bold",color=edge,zorder=2)
band(0,3,"#F5F8FC","#4A6FA5","Candidate generation — no AF2/ColabFold folding",y+bh+0.72)
band(4,6,"#FEF7EC","#C77F2E","AlphaFold2 / ColabFold budget — 50 calls per target",y+bh+0.72)
for i,(title,sub,face,edge,dashed) in enumerate(STAGES):
    x=xs[i]
    rounded(ax,x+0.05,y-0.06,bw,bh,"#0000000F","#0000000F",lw=0,z=2)
    rounded(ax,x,y,bw,bh,face,edge,lw=2.2,z=3,dashed=dashed)
    ax.text(x+bw/2,y+bh*0.60,title,ha="center",va="center",fontsize=11.5,fontweight="bold",color=INK,zorder=4)
    ax.text(x+bw/2,y+bh*0.22,sub,ha="center",va="center",fontsize=9.5,style="italic",color=edge,zorder=4)
    bx,by=x+0.28,y+bh-0.02
    ax.add_patch(Circle((bx,by),0.18,facecolor=edge,edgecolor="white",lw=1.5,zorder=6))
    ax.text(bx,by,str(i+1),ha="center",va="center",fontsize=10,fontweight="bold",color="white",zorder=7)
for i in range(n-1):
    ax.add_patch(FancyArrowPatch((xs[i]+bw+0.02,y+bh/2),(xs[i+1]-0.02,y+bh/2),
        arrowstyle="-|>",mutation_scale=22,linewidth=2.2,color="#4B5563",zorder=5))
cy=0.60
ax.annotate("",xy=(xs[7]+bw/2,cy),xytext=(xs[0]+bw/2,cy),
    arrowprops=dict(arrowstyle="-|>",lw=2.2,color="#9CA3AF"),zorder=2)
ax.text(xs[2]+bw/2,cy-0.30,"~10,000 candidates",ha="center",va="top",fontsize=11,color="#374151",fontweight="bold")
ax.text((xs[4]+xs[6])/2+bw/2,cy-0.30,"50 folded  (~0.5%, 1/200)",ha="center",va="top",fontsize=11,color="#7B241C",fontweight="bold")
ax.text(xs[7]+bw/2,cy-0.30,"20 ranked",ha="center",va="top",fontsize=11,color="#374151",fontweight="bold")
fig.tight_layout()
fig.savefig(OUT,dpi=200,bbox_inches="tight",facecolor="white")
print("wrote",OUT)
