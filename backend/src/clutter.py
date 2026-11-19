"""底质杂波筛选：主管标记监督训练，留验航次仅用于验收。

特征与训练全部确定性执行，不依赖随机过程；模型用标准化特征上的
批量梯度下降逻辑回归，参数随版本序列化入库，识别排队时固定版本。
"""
import math,hashlib
import numpy as np

KIND_BOTTOM='bottom'   # 主管确定的底质回波（杂波）
KIND_FISH='fish'       # 主管确定的鱼群回波
EVAL_EPS=1.2           # 留验验收与原识别对比使用的固定DBSCAN参数
EVAL_MIN_SAMPLES=4
SCALE_SPATIAL=60.0
SCALE_DEPTH=3.0
SCALE_STRENGTH=8.0
LR_ITERS=2000
LR_RATE=0.05


def _matrix(points):
    """与 algorithm.py 同口径的米制缩放特征（去掉沿程占位维度前的原始量）。"""
    lon0=points[0]['lon'];lat0=points[0]['lat']
    rows=[]
    for p in points:
        x=math.radians(p['lon']-lon0)*6371000*math.cos(math.radians(lat0))
        y=math.radians(p['lat']-lat0)*6371000
        rows.append([x/SCALE_SPATIAL,y/SCALE_SPATIAL,p['depth_m']/SCALE_DEPTH,p['strength_db']/SCALE_STRENGTH])
    return np.array(rows,dtype=float)


def features(points):
    """逐回波特征：水深、强度、相对沿程位置、最近邻距离与局部密度。

    底质回波常沿水深方向连成串、彼此邻近且强度偏高，最近邻距离和
    局部密度刻画“连成串”的结构，水深与强度刻画个体差异。
    """
    base=_matrix(points)
    n=len(points)
    out=[]
    for i,p in enumerate(points):
        diffs=base-base[i]
        dist=np.sqrt((diffs**2).sum(axis=1))
        nearest=np.partition(dist,1)[1] if n>1 else 0.0
        density=float(np.sum(dist<=EVAL_EPS))-1
        out.append([
            p['depth_m'],
            p['strength_db'],
            p['along_m']/max(p.get('length_m',1.0),1e-9),
            float(nearest),
            density,
        ])
    return np.array(out,dtype=float)


def _sigmoid(z):return 1.0/(1.0+np.exp(-np.clip(z,-30,30)))


def fit(X,y):
    """确定性批量梯度下降逻辑回归，返回可JSON序列化的模型参数。"""
    mu=X.mean(axis=0);sd=X.std(axis=0);sd[sd==0]=1.0
    Z=(X-mu)/sd
    Zb=np.hstack([np.ones((Z.shape[0],1)),Z])
    w=np.zeros(Zb.shape[1])
    for _ in range(LR_ITERS):
        grad=Zb.T@(_sigmoid(Zb@w)-y)/Zb.shape[0]
        # L2 轻微收缩，抑制小样本下系数发散
        reg=np.r_[0.0,w[1:]]*1e-3
        w-=LR_RATE*(grad+reg)
    return {'mu':mu.tolist(),'sd':sd.tolist(),'w':w.tolist(),'iterations':LR_ITERS,'learning_rate':LR_RATE}


def predict_proba(model,X):
    mu=np.array(model['mu']);sd=np.array(model['sd']);w=np.array(model['w'])
    Z=(X-mu)/sd
    Zb=np.hstack([np.ones((Z.shape[0],1)),Z])
    return _sigmoid(Zb@w)


def train(points,label_kind_by_echo):
    """用主管标记训练，返回模型参数、训练摘要与输入校验和。"""
    labeled=[(p,k) for p in points if (k:=label_kind_by_echo.get(p['id'])) in (KIND_BOTTOM,KIND_FISH)]
    bottom=sum(1 for _,k in labeled if k==KIND_BOTTOM);fish=len(labeled)-bottom
    if len(labeled)<16 or bottom<8 or fish<8:
        raise ValueError('训练标记不足：底质与鱼群标记各至少8个、总数至少16个')
    X=features([p for p,_ in labeled])
    y=np.array([1.0 if k==KIND_BOTTOM else 0.0 for _,k in labeled])
    model=fit(X,y)
    sha=hashlib.sha256(np.hstack([X,y.reshape(-1,1)]).tobytes()).hexdigest()
    return model,{'training_count':len(labeled),'training_bottom':bottom,'training_fish':fish},sha


def filter_echo_ids(model,points):
    """返回模型判为底质杂波、应在识别前剔除的回波id列表。"""
    if not points:return []
    proba=predict_proba(model,features(points))
    return [p['id'] for p,pr in zip(points,proba) if pr>=0.5]
