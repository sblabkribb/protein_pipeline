#!/usr/bin/env python3
"""Supplementary Figure S10 — 5 monomer-enzyme three-arm comparison, restyled to the
Figure 3/Figure 4 house style (Wong palette, black jittered points, whitegrid, n= labels).
Data: solu_monomer_threeway/monomer_threeway_per_target.csv
Run: /opt/protein_pipeline/venv/bin/python make_figS10_monomer_matched.py"""
import csv, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
sys.path.insert(0, str(Path(__file__).parent)); import figstyle; figstyle.apply()

ROOT=Path("/opt/protein_pipeline-work")
CSV=next(p for p in [ROOT/"public_data/benchmark/results/solu_monomer_threeway/monomer_threeway_per_target.csv",
                     ROOT/"data/benchmark/results/solu_monomer_threeway/monomer_threeway_per_target.csv"] if p.exists())
OUT=ROOT/"docs/figures/figS10_monomer_matched.png"
COL={"single":"#BDBDBD","pool":"#7FB0D3","surr":"#0072B2"}   # same as restyled Fig4
rows=list(csv.DictReader(open(CSV)))
col=lambda arm,key: np.array([float(r[key]) for r in rows if r["arm"]==arm])

def box_strip(ax,series,labels,colors,title,ylabel):
    pos=np.arange(len(series))
    bp=ax.boxplot(series,positions=pos,widths=0.55,patch_artist=True,showfliers=False,
        showmeans=True,meanprops=dict(marker="D",markerfacecolor="black",markeredgecolor="black",markersize=4),
        medianprops={"color":"#333333","linewidth":1.2},
        whiskerprops={"color":"#555555","linewidth":1.0},
        capprops={"color":"#555555","linewidth":1.0},
        boxprops={"edgecolor":"#444444","linewidth":1.0})
    for patch,c in zip(bp["boxes"],colors): patch.set_facecolor(c); patch.set_alpha(0.65)
    allv=[v for s in series for v in s]; span=max(max(allv)-min(allv),1e-6)
    for i,vals in enumerate(series):
        offs=np.linspace(-0.12,0.12,len(vals)) if len(vals)>1 else [0.0]
        ax.scatter([i+o for o in offs],vals,color="#222222",s=18,alpha=0.85,linewidth=0,zorder=3)
        ax.text(i,max(vals)+0.08*span,f"n={len(vals)}",ha="center",va="bottom",fontsize=7)
    ax.set_ylim(min(allv)-0.15*span,max(allv)+0.28*span)
    ax.set_title(title,fontsize=10,pad=8); ax.set_ylabel(ylabel,fontsize=9)
    ax.set_xticks(pos); ax.set_xticklabels(labels,fontsize=8)
    ax.grid(axis="y",color="#dddddd",linewidth=0.8,alpha=0.8); ax.set_axisbelow(True)
    for sp in ("top","right"): ax.spines[sp].set_visible(False)

arms=["single_surr","ens_pool","ens_surr"]
div=[col(a,"diversity") for a in arms]; so=[col(a,"soluprot_mean") for a in arms]; pl=[col(a,"plddt_mean") for a in arms]
labs=["Single\n+surrogate","RFD3+BioEmu\npool (random)","RFD3+BioEmu\n+surrogate"]
cols=[COL["single"],COL["pool"],COL["surr"]]
fig,ax=plt.subplots(1,3,figsize=(12.5,4.6))
box_strip(ax[0],div,labs,cols,"Top-K sequence diversity","mean pairwise diversity")
box_strip(ax[1],so,labs,cols,"Selected-set SoluProt","mean SoluProt")
box_strip(ax[2],pl,labs,cols,"pLDDT (pool = bootstrap labels)","mean pLDDT")
r=float(np.mean(div[2])/np.mean(div[0]))
fig.suptitle("Structural-context three-arm comparison — 5 solubility-engineering monomer enzymes "
             f"(diversity 5/5 up, ~{r:.1f}×, paired Wilcoxon p=0.0625)",fontsize=11,fontweight="bold")
fig.tight_layout(rect=[0,0,1,0.95])
fig.savefig(OUT,dpi=200,bbox_inches="tight",facecolor="white")
print("wrote",OUT)
