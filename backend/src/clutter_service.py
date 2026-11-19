"""杂波筛选的数据库服务：主管标记、留验航次、训练验收、版本启停。"""
from sqlalchemy import select,func
from .models import (Echo,EchoLabel,ClutterFilterVersion,Cruise,Transect,Audit,now)
from .common import get,reject,finish,dump
from . import clutter
from .constants import FilterState
from .algorithm import analyze as dbscan_analyze


def label_echo(db,data,user):
    echo=get(db,Echo,data.echo_id)
    t=get(db,Transect,echo.transect_id)
    c=get(db,Cruise,t.cruise_id,True)
    reject(c.status=='frozen','调查图层已封存，标记不可修改')
    reject(data.kind not in (clutter.KIND_BOTTOM,clutter.KIND_FISH),'标记类型仅支持 bottom（底质）或 fish（鱼群）')
    row=db.scalar(select(EchoLabel).where(EchoLabel.echo_id==echo.id))
    if row:row.kind=data.kind;row.note=data.note
    else:row=EchoLabel(echo_id=echo.id,kind=data.kind,note=data.note);db.add(row)
    db.flush();return finish(db,user,'标注回波为'+('底质' if data.kind==clutter.KIND_BOTTOM else '鱼群'),row)


def unlabel_echo(db,id,user):
    row=db.scalar(select(EchoLabel).where(EchoLabel.echo_id==id))
    reject(row is None,'该回波尚无标记')
    echo=get(db,Echo,id);t=get(db,Transect,echo.transect_id);get(db,Cruise,t.cruise_id,True)
    db.delete(row);db.add(Audit(actor=user.username,action='撤销回波标记',detail=str(id)));db.commit()
    return {'echo_id':id}


def set_holdout(db,id,flag,user):
    c=get(db,Cruise,id,True);reject(c.status=='frozen','封存航次不能更改留验标记')
    c.holdout=bool(flag);return finish(db,user,'留验航次标记' if flag else '取消留验航次标记',c)


def _labeled_points(db,holdout):
    """收集（非）留验航次上带主管标记的回波，附带标记类型。"""
    cruise_ids={c.id for c in db.scalars(select(Cruise).where(Cruise.holdout==holdout))}
    if not cruise_ids:return [],{}
    transect_ids={t.id for t in db.scalars(select(Transect).where(Transect.cruise_id.in_(cruise_ids)))}
    if not transect_ids:return [],{}
    echoes=list(db.scalars(select(Echo).where(Echo.transect_id.in_(transect_ids)).order_by(Echo.id)))
    kinds={l.echo_id:l.kind for l in db.scalars(select(EchoLabel))}
    points=[dump(e)|{'length_m':get(db,Transect,e.transect_id).length_m} for e in echoes if e.id in kinds]
    return points,{p['id']:kinds[p['id']] for p in points}


def _acceptance(model,points,kinds):
    """在留验航次上与原DBSCAN识别对比，返回验收指标。

    误报底质：主管标 bottom 却被识别赋予鱼群簇标签(>=0)的回波——底质串被认成鱼。
      筛选后这些回波被正确剔除即不再计入误报；要求严格少于原识别。
    漏鱼：主管标 fish 却未进入鱼群结果的回波——原识别中为噪点(-1)，
      筛选后为被剔除或仍为噪点（剔除底质邻居也可能拆散鱼群，故按最终结果计）；
      要求不多于原识别。逐航段独立聚类后合并计数。
    """
    by_t={}
    for p in points:by_t.setdefault(p['transect_id'],[]).append(p)
    base_false_bottom=base_missed=0;fil_false_bottom=fil_missed=0
    bottom_total=fish_total=0;removed_bottom=removed_fish=0
    for _,ps in by_t.items():
        assignments,_=dbscan_analyze(ps,clutter.EVAL_EPS,clutter.EVAL_MIN_SAMPLES)
        base_label={a['echo_id']:a['label'] for a in assignments}
        removed=set(clutter.filter_echo_ids(model,ps))
        kept=[p for p in ps if p['id'] not in removed]
        kept_labels={}
        if kept:
            kept_assign,_=dbscan_analyze(kept,clutter.EVAL_EPS,clutter.EVAL_MIN_SAMPLES)
            kept_labels={a['echo_id']:a['label'] for a in kept_assign}
        for p in ps:
            kind=kinds[p['id']]
            if kind==clutter.KIND_BOTTOM:bottom_total+=1
            else:fish_total+=1
            if p['id'] in removed:
                if kind==clutter.KIND_BOTTOM:removed_bottom+=1
                else:removed_fish+=1
            if kind==clutter.KIND_BOTTOM:
                if base_label[p['id']]>=0:base_false_bottom+=1
                if p['id'] not in removed and kept_labels.get(p['id'],-1)>=0:fil_false_bottom+=1
            else:
                if base_label[p['id']]==-1:base_missed+=1
                if p['id'] in removed or kept_labels.get(p['id'],-1)==-1:fil_missed+=1
    return {
        'holdout_point_count':len(points),'holdout_bottom_count':bottom_total,'holdout_fish_count':fish_total,
        'baseline_false_bottom':base_false_bottom,'filter_false_bottom':fil_false_bottom,
        'baseline_missed_fish':base_missed,'filter_missed_fish':fil_missed,
        'removed_bottom':removed_bottom,'removed_fish':removed_fish,
        'eval_eps':clutter.EVAL_EPS,'eval_min_samples':clutter.EVAL_MIN_SAMPLES,
    }


def train_filter(db,data,user):
    points,kinds=_labeled_points(db,False)
    bottom=sum(1 for k in kinds.values() if k==clutter.KIND_BOTTOM);fish=len(kinds)-bottom
    reject(len(points)<16 or bottom<8 or fish<8,'训练标记不足：非留验航次上底质与鱼群标记各至少8个、总数至少16个')
    holdout_points,holdout_kinds=_labeled_points(db,True)
    hb=sum(1 for k in holdout_kinds.values() if k==clutter.KIND_BOTTOM);hf=len(holdout_kinds)-hb
    reject(len(holdout_points)<16 or hb<4 or hf<4,'留验验收标记不足：留验航次上底质与鱼群标记各至少4个、总数至少16个')
    model,summary,sha=clutter.train(points,kinds)
    metrics=_acceptance(model,holdout_points,holdout_kinds)
    reject(metrics['filter_false_bottom']>=metrics['baseline_false_bottom'],'验收未通过：留验误报底质未少于原识别')
    reject(metrics['filter_missed_fish']>metrics['baseline_missed_fish'],'验收未通过：留验漏鱼多于原识别')
    metrics['passed']=True;metrics.update(summary);metrics['training_sha256']=sha
    seq=(db.scalar(select(func.count()).select_from(ClutterFilterVersion)) or 0)+1
    row=ClutterFilterVersion(version=f'CF-{seq:03d}',status=FilterState.candidate.value,model=model,metrics=metrics,training_sha256=sha,note=data.note[:240])
    db.add(row);db.flush();return finish(db,user,'训练杂波筛选候选版本',row)


def enable_filter(db,id,user):
    row=get(db,ClutterFilterVersion,id,True)
    reject(row.status==FilterState.enabled.value,'该版本已启用')
    reject(row.status!=FilterState.candidate.value,'仅候选版本可启用；已拒绝或已停用版本不可启用')
    reject(not row.metrics.get('passed'),'该版本未通过留验验收，不能启用')
    for old in db.scalars(select(ClutterFilterVersion).where(ClutterFilterVersion.status==FilterState.enabled.value)):
        old.status=FilterState.superseded.value
    row.status=FilterState.enabled.value
    row.enabled_at=now()
    return finish(db,user,'启用杂波筛选版本',row)


def reject_filter(db,id,user):
    row=get(db,ClutterFilterVersion,id,True)
    reject(row.status==FilterState.enabled.value,'已启用版本请先由新版本替代，不能直接拒绝')
    row.status=FilterState.rejected.value
    return finish(db,user,'拒绝杂波筛选候选版本',row)


def enabled_version(db):
    return db.scalar(select(ClutterFilterVersion).where(ClutterFilterVersion.status==FilterState.enabled.value).order_by(ClutterFilterVersion.id.desc()))
