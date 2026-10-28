import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
root=Path(__file__).resolve().parents[1];j=json.loads((root/'data/llm-summary.json').read_text())
font=FontProperties(fname=str(root/'assets/plex-sans-400.ttf'))
plt.rcParams.update({'svg.fonttype':'none','font.family':'IBM Plex Sans','axes.spines.right':False,'axes.spines.top':False,'axes.spines.left':False,'axes.spines.bottom':False,'axes.edgecolor':'#e8e8e0','text.color':'#171916','xtick.color':'#62645b','ytick.color':'#171916'})
fig,axs=plt.subplots(1,2,figsize=(10,4.7),layout='constrained',gridspec_kw={'width_ratios':[1.15,1]})
labels=['IPvX · R1','IP · напрямую','IP · R1'];colors=['#9f8700','#171916','#62645b']
for ax,key,title,unit,limit in [(axs[0],'echo_p50_ms','Короткий обмен','мс',45),(axs[1],'inference_p50_ms','Один вызов модели','с',13)]:
 vals=[m[key]/(1000 if unit=='с' else 1) for m in j['modes']]
 bars=ax.barh(labels,vals,color=colors,height=.48);ax.invert_yaxis();ax.set_xlim(0,limit);ax.set_title(title,fontproperties=font,fontsize=16,loc='left',pad=24);ax.set_xlabel('Медиана, '+unit,fontproperties=font,fontsize=12,loc='left',labelpad=16)
 ax.tick_params(axis='both',length=0,labelsize=12,pad=10)
 for t in ax.get_yticklabels()+ax.get_xticklabels():t.set_fontproperties(font)
 for b,v in zip(bars,vals):ax.text(v+.4,b.get_y()+b.get_height()/2,f'{v:.2f} {unit}',va='center',fontproperties=font,fontsize=12)
 ax.grid(axis='x',color='#e8e8e0',linewidth=.6);ax.set_axisbelow(True)
fig.suptitle('Сеть и вычисление — разные масштабы времени',fontproperties=font,fontsize=19,x=.02,ha='left')
fig.savefig(root/'assets/llm-comparison.svg',facecolor='white');fig.savefig(root/'../../outputs/ipvx-llm-comparison.png',dpi=160,facecolor='white')
# Separate readable mobile figure; do not shrink desktop labels to phone size.
fig,axs=plt.subplots(2,1,figsize=(4.2,8.2),layout='constrained')
for ax,key,title,unit,limit in [(axs[0],'echo_p50_ms','Короткий обмен','мс',48),(axs[1],'inference_p50_ms','Один вызов модели','с',14)]:
 vals=[m[key]/(1000 if unit=='с' else 1) for m in j['modes']]
 bars=ax.barh(labels,vals,color=colors,height=.5);ax.invert_yaxis();ax.set_xlim(0,limit);ax.set_title(title,fontproperties=font,fontsize=17,loc='left',pad=18);ax.set_xlabel('Медиана, '+unit,fontproperties=font,fontsize=13,loc='left',labelpad=12)
 ax.tick_params(axis='both',length=0,pad=8)
 for t in ax.get_yticklabels()+ax.get_xticklabels():t.set_fontproperties(font);t.set_fontsize(12)
 for b,v in zip(bars,vals):ax.text(v+.5,b.get_y()+b.get_height()/2,f'{v:.2f}',va='center',fontproperties=font,fontsize=13)
 ax.grid(axis='x',color='#e8e8e0',linewidth=.6);ax.set_axisbelow(True)
fig.savefig(root/'assets/llm-comparison-mobile.svg',facecolor='white')

# Give translated and fallback-font tick labels room at the right edge.
mobile = root/'assets/llm-comparison-mobile.svg'
svg = mobile.read_text()
svg = svg.replace('width="302.4pt"', 'width="312.4pt"', 1).replace('viewBox="0 0 302.4 590.4"', 'viewBox="0 0 312.4 590.4"', 1)
mobile.write_text(svg)
