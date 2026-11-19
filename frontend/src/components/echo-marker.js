import {store} from '../stores/workspace.js';
import {transects} from './voyage-context.js';
import {field,input,select} from './controls.js';
import {bindForm,request} from '../utils/forms.js';

// 主管在回波散点上直接点选，标记确定的底质/鱼群，供杂波筛选训练。
export function echoMarker(){
  const d=store.data;
  const ts=transects();
  if(!ts.length)return '';
  const ids=ts.map(t=>t.id);
  const echoes=d.echoes.filter(e=>ids.includes(e.transect_id));
  if(!echoes.length)return '<p class="empty">当前航段暂无回波，先在声学航段页导入或录入。</p>';
  const labels=new Map((d.echo_labels||[]).map(l=>[l.echo_id,l.kind]));
  const maxLen=Math.max(...ts.map(t=>t.length_m));
  const x=e=>45+e.along_m/maxLen*610,y=e=>25+e.depth_m/35*155;
  const cls=e=>labels.get(e.id)==='bottom'?'mark-bottom':(labels.get(e.id)==='fish'?'mark-fish':'mark-none');
  return `<section class="mark-panel">
    <h3>主管回波标记（点击圆点选择，再判定底质/鱼群）</h3>
    <p class="hint"><span class="dot mark-bottom"></span>确定底质<span class="dot mark-fish"></span>确定鱼群<span class="dot mark-none"></span>未标记 · 当前选中：<b id="mark-selected">未选择</b></p>
    <svg id="mark-svg" viewBox="0 0 700 220" role="img" aria-label="回波沿程与水深散点，点击可标记">
      <path d="M40 20V185H665" class="axis"/>
      ${echoes.map(e=>`<circle data-echo="${e.id}" cx="${x(e)}" cy="${y(e)}" r="4" class="mark-dot ${cls(e)}"><title>#${e.id} 沿程${Math.round(e.along_m)}m 水深${e.depth_m.toFixed(1)}m</title></circle>`).join('')}
      <text x="4" y="35">0m</text><text x="4" y="180">35m</text><text x="45" y="210">起点</text><text x="620" y="210">终点</text>
    </svg>
    <form id="mark-quick" class="row-form">
      <input type="hidden" name="echo_id" id="mark-echo-id" required>
      ${field('判定',select('kind','<option value="bottom">确定底质（杂波）</option><option value="fish">确定鱼群</option>'))}
      ${field('备注',input('note','text','点图标记'))}
      <button>标记选中回波</button>
    </form>
  </section>`;
}

export function bindEchoMarker(renderAll){
  const form=document.getElementById('mark-quick');
  if(form)bindForm('mark-quick',f=>request('/echo-labels',{echo_id:+f.echo_id,kind:f.kind,note:f.note}),renderAll);
  document.querySelectorAll('#mark-svg [data-echo]').forEach(c=>{
    c.onclick=()=>{
      document.getElementById('mark-echo-id').value=c.dataset.echo;
      document.getElementById('mark-selected').textContent='#'+c.dataset.echo;
      document.querySelectorAll('#mark-svg .mark-dot').forEach(o=>o.classList.remove('mark-picked'));
      c.classList.add('mark-picked');
    };
  });
}
