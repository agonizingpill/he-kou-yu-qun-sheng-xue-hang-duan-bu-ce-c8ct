import logging,time,json,os
from pathlib import Path
from sqlalchemy import select
from .database import Session
from .models import SchoolAnalysis,Transect,Echo,ClutterFilterVersion
from .school_service import queue
from .algorithm import analyze
from . import clutter
from .common import dump
logging.basicConfig(level=logging.INFO)

def run_analysis(db,row):
    """处理单个识别任务，按入队时固定的筛选版本剔除底质后聚类。"""
    t=db.get(Transect,row.transect_id)
    if row.data_version!=t.data_version:raise ValueError('回波已更新，请重新提交最新版本')
    all_points=[dump(p)|{'length_m':t.length_m} for p in db.scalars(select(Echo).where(Echo.transect_id==t.id).order_by(Echo.id))]
    removed=[];filter_version=None
    # 仅按入队时固定的筛选版本剔除；版本后续启停不影响在途/重试任务。
    if row.filter_version_id:
        filter_version=db.get(ClutterFilterVersion,row.filter_version_id)
        if not filter_version:raise ValueError('固定的杂波筛选版本不存在')
        removed=clutter.filter_echo_ids(filter_version.model,all_points)
        used=[p for p in all_points if p['id'] not in removed]
    else:
        used=all_points
    if len(used)<8:raise ValueError('筛选后回波不足8个，无法识别群落；请补充回波或调整筛选标记')
    row.filtered_echo_ids=removed;row.filtered_count=len(removed)
    row.assignments,row.metrics=analyze(used,row.eps,row.min_samples)
    row.metrics['filter_version_id']=filter_version.id if filter_version else None
    row.metrics['filter_version']=filter_version.version if filter_version else None
    row.metrics['filtered_count']=len(removed)
    row.metrics['total_echo_count']=len(all_points)
    row.status='done'
    artifacts=Path(os.getenv('ARTIFACTS_DIR','/artifacts'));artifacts.mkdir(exist_ok=True);(artifacts/f'school-{row.id}.json').write_text(json.dumps(row.metrics,ensure_ascii=False))

def main():
    while True:
        Path('/tmp/worker-heartbeat').touch()
        try:
            item=queue.blpop('estuary:schools',timeout=2)
            if not item:continue
            with Session() as db:
                row=db.get(SchoolAnalysis,int(item[1]))
                if not row or row.status!='queued':continue
                row.status='running';db.commit()
                try:run_analysis(db,row)
                except Exception as e:row.status='failed';row.error=str(e)[:200]
                db.commit()
        except Exception:logging.exception('echo worker');time.sleep(1)

if __name__=='__main__':main()
