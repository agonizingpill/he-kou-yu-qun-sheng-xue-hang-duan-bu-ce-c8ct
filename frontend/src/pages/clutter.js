import {store} from '../stores/workspace.js';
import {transects} from '../components/voyage-context.js';
import {field,input,select,table,badge} from '../components/controls.js';
import {echoMarker,bindEchoMarker} from '../components/echo-marker.js';
import {filterStates,labelKinds} from '../constants/enums.js';
import {esc} from '../utils/format.js';
import {bindForm,request} from '../utils/forms.js';

const role=()=>store.data.session?.role||store.session?.role;

export function render(){
  const d=store.data;
  const ids=transects().map(t=>t.id);
  const echoes=d.echoes.filter(e=>ids.includes(e.transect_id));
  const labels=new Map((d.echo_labels||[]).map(l=>[l.echo_id,l]));
  const cruises=d.cruises;
  const versions=d.clutter_filter_versions||[];
  const enabled=versions.filter(v=>v.status==='enabled');
  const transectById=id=>d.transects.find(t=>t.id===id);
  const echoOptions=echoes.map(e=>`<option value="${e.id}">#${e.id} ${esc(transectById(e.transect_id)?.code||'')} · 沿程${Math.round(e.along_m)}m · 水深${e.depth_m.toFixed(1)}m · ${e.strength_db.toFixed(1)}dB</option>`).join('');
  const labelRows=echoes.filter(e=>labels.has(e.id)).map(e=>{
    const l=labels.get(e.id);
    return [`#${e.id} ${esc(transectById(e.transect_id)?.code||'')}`,`${Math.round(e.along_m)}m / ${e.depth_m.toFixed(1)}m / ${e.strength_db.toFixed(1)}dB`,badge(labelKinds[l.kind]||l.kind,l.kind==='bottom'?'':'ok'),`<button type="button" class="text-button" data-unlabel="${e.id}">撤销</button>`];
  });
  const versionRows=versions.slice().reverse().map(v=>{
    const m=v.metrics||{};
    const acc=`误报底质 ${m.baseline_false_bottom??'—'} → ${m.filter_false_bottom??'—'} ／ 漏鱼 ${m.baseline_missed_fish??'—'} → ${m.filter_missed_fish??'—'}`;
    const actions=v.status==='candidate'
      ? `<button type="button" class="secondary" data-enable="${v.id}">启用</button><button type="button" class="text-button" data-reject="${v.id}">拒绝</button>`
      : (v.status==='superseded'?`<button type="button" class="text-button" data-reject="${v.id}">拒绝</button>`:'—');
    return [esc(v.version),badge(filterStates[v.status]||v.status),`训练${m.training_count??'—'}点（底${m.training_bottom??'—'}/鱼${m.training_fish??'—'}）`,acc,m.passed?'通过':'未过',actions];
  });
  return `<h2>底质杂波筛选</h2>
<p class="intro">底质回波连成串时会被DBSCAN误认成鱼群。主管在复核页对确定的底质与鱼群回波打标，用非留验航次的标记训练；留验航次标记全程只用于验收。验收要求比原识别<b>少误报底质且不多漏鱼</b>，版本才可启用。识别排队时固定筛选版本，重试不换版；筛掉的回波仍留底，封存时存版本与剔除记录。</p>
<div class="two-col">
  <form id="holdout-form">
    <h3>留验航次（标记全程只用于验收）</h3>
    ${table(['航次','用途','留验'],cruises.map(c=>[esc(c.code),esc(c.purpose),`<label class="switch"><input type="checkbox" data-holdout="${c.id}" ${c.holdout?'checked':''} ${role()!=='supervisor'?'disabled':''}><span>${c.holdout?'留验中':'训练池'}</span></label>`]))}
    <p class="hint">勾选后该航次的标记不参与训练，仅在训练时做留验验收比对。</p>
  </form>
  <form id="label-form">
    <h3>主管标注回波</h3>
    ${field('回波',select('echo_id',echoOptions||'<option value="">当前航段暂无回波</option>'))}
    ${field('判定',select('kind','<option value="bottom">确定底质（杂波）</option><option value="fish">确定鱼群</option>'))}
    ${field('备注',input('note','text','经回看探头记录确认'))}
    <button>保存标记（仅主管）</button>
  </form>
</div>
<div class="two-col">
  <form id="train-form">
    <h3>训练并留验验收</h3>
    ${field('版本备注',input('note','text','基于当前全部标记训练'))}
    <p class="hint">非留验航次上底质/鱼群标记各≥8、总数≥16；留验航次上各≥4、总数≥16。训练为确定性逻辑回归，结果先入候选。</p>
    <button>训练候选版本并验收</button>
  </form>
  <section>
    <h3>当前启用版本</h3>
    ${enabled.length?enabled.map(v=>`<p>${badge(filterStates.enabled,'ok')} <b>${esc(v.version)}</b></p><small>启用时间 ${v.enabled_at?new Date(v.enabled_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—'}</small><p class="hint">此后新入队识别固定使用此版本；已入队与重试任务不受影响。</p>`).join(''):'<p class="empty">尚无启用版本，识别按原DBSCAN全量回波进行。</p>'}
  </section>
</div>
<h3>筛选版本与留验验收</h3>
${table(['版本','状态','训练口径','留验验收（原识别 → 筛选）','验收','操作'],versionRows,'尚未训练任何筛选版本。')}
<h3>当前航段回波标记（${labelRows.length}）</h3>
${table(['回波','沿程/水深/强度','判定','操作'],labelRows,'当前航段回波尚未标注，可在下方点图直接标记。')}
${echoMarker()}`;
}

export function bind(renderAll){
  const d=store.data;
  if(role()!=='supervisor')return;
  bindForm('label-form',f=>request('/echo-labels',{echo_id:+f.echo_id,kind:f.kind,note:f.note}),renderAll);
  bindForm('train-form',f=>request('/clutter-filters/train',{note:f.note}),renderAll);
  bindEchoMarker(renderAll);
  document.querySelectorAll('[data-holdout]').forEach(cb=>{
    cb.onchange=async()=>{
      try{await request('/cruises/'+cb.dataset.holdout+'/holdout',{holdout:cb.checked},'PATCH');const {reload}=await import('../stores/workspace.js');await reload();renderAll('留验标记已更新');}
      catch(e){document.getElementById('notice').textContent=e.message;document.getElementById('notice').className='notice error';cb.checked=!cb.checked;}
    };
  });
  document.querySelectorAll('[data-unlabel]').forEach(btn=>{
    btn.onclick=async()=>{
      try{await request('/echo-labels/'+btn.dataset.unlabel,undefined,'DELETE');const {reload}=await import('../stores/workspace.js');await reload();renderAll('标记已撤销');}
      catch(e){document.getElementById('notice').textContent=e.message;document.getElementById('notice').className='notice error';}
    };
  });
  const act=async(path)=>{await request(path,{});const {reload}=await import('../stores/workspace.js');await reload();renderAll('筛选版本已更新');};
  document.querySelectorAll('[data-enable]').forEach(b=>b.onclick=()=>act('/clutter-filters/'+b.dataset.enable+'/enable').catch(e=>{document.getElementById('notice').textContent=e.message;document.getElementById('notice').className='notice error';}));
  document.querySelectorAll('[data-reject]').forEach(b=>b.onclick=()=>act('/clutter-filters/'+b.dataset.reject+'/reject').catch(e=>{document.getElementById('notice').textContent=e.message;document.getElementById('notice').className='notice error';}));
}
