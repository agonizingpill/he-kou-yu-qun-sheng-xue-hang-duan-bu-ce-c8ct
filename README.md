# 河口鱼群声学航段与补测

潮汐渔研站的河口调查记录，把航窗、声学回波、群落复核、网具生物样和缺测补航连接到同一份冻结图层。

渔研站有2艘调查船和7位调查员。以往用船上记录簿保存探头参数，回港后再拼接回波表、网具校验单和生物样Excel，容易误把缺测当成低密度、给过期网具关联样本、在噪点尚未解释前交出图层。本应用承接调查计划与探头记录，替代从现场分段到资源调查组收件的拼接核验环节。它不涉及港口燃油放行或航运经营。

## 六个模块

1. 航次与禁航：具名调查船、带时区航窗、潮汐禁航。开航重新检查冲突；同船同期只能一航次；未开航可改时间恢复。
2. 声学航段与探头：地理端点、米制长度、38/120/200kHz探头、增益；回波点含沿程距离、经纬度、水深和强度，范围与偏航100米约束。
3. 群落与噪点：worker实际DBSCAN，复核针对当前回波版本与最新识别ID；有噪点必须解释。同版本重跑识别后，旧复核不会继续放行。主管可对确定的底质/鱼群回波打标，训练底质杂波筛选：留验航次标记全程只用于验收，验收需比原识别少误报底质且不多漏鱼才可启用；识别排队时固定筛选版本，重试不改版本，筛除回波仍留底。
4. 网具与生物样：标称网目、实测尺度、证书和有效期；误差≤10%合格，最新校验须覆盖上海时区完整返航日期。样本引用已复核分析和实际校验记录，不可关联噪点。
5. 缺测补航：原航段沿程区间不得重叠，主管按区间自动推导补航地理端点；补航回波、噪点复核和生物样齐全后才能接续。空补航可撤销重排。
6. 图层封存：缺测全部覆盖后结束现场；逐航段最新分析、噪点复核和对应样本齐全后冻结。JSON快照包含回波、聚类、复核、样本、网具与校验，附原始canonical_json及其UTF-8字节SHA256；航次冻结后拒绝业务变更。

## 启动和账户

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec backend python -m src.seed
```

访问前端 http://localhost:18236 ，后端 http://localhost:19236 ，文档 http://localhost:19236/docs 。PostgreSQL映射17736，Redis内部开放。五服务frontend/backend/worker/db/redis均有healthcheck，数据库、Redis和共享产物使用命名卷。默认子网10.221.37.0/24。

| 账号 / 角色 | 密码 | 工作职责 |
|---|---|---|
| operator 调查员 | Estuary@2026 | 申请航次、调整未开航时间、规划航段、回波、识别排队、生物样、缺测标记 |
| supervisor 调查主管 | Estuary@2026 | 全部调查员动作，另含禁航、开返航、群落复核、网具校验、补航审批/完成/撤销、封存、审计 |
| viewer 观察员 | Estuary@2026 | 读取调查资料，全部写接口拒绝 |

JWT有效8小时，角色按服务端当前账户核验。演示凭据仅用于独立本地调查演示。

## 一天的操作剧本

1. 08:30 打开CY031，潮研一号、E1/E2航段，原11:00–13:00航窗与11月18日12:00–14:00潮汐禁航重叠，开航拒绝。
2. 09:00 改为14:15–17:00，主管核准；查看E1已登记300–600米探头断续缺测。
3. 14:20 在“声学航段”选择E1，导入标注为合成来源的80点探头数据；E2同样导入。实际现场可提交JSON回波数组。
4. 14:40 “群落复核”按eps1.2/min_samples4排队，刷新查看真实DBSCAN结果与参数敏感性，主管解释孤立回波的底质干扰并签署。
5. 15:00 N31初校11.6mm相对10mm超差，生物样关联被拒绝；主管复校10.2mm、证书`N31-复校-20261118`、有效期2026-12-31，调查员关联群落0的12尾模拟鲻鱼、平均125mm。
6. 15:20 主管为300米缺测生成E1-S1补航，尚无数据时确认接续被拒绝；到航段页导入补航回波，复核群落并关联生物样后，再确认覆盖。
7. 16:30 主航段和补航齐全后主管结束现场调查。若重跑最新识别，需新复核与新样本关联，旧复核不能继续用。
8. 17:00 交给“潮汐渔研站资源调查组”，冻结图层，下载`CY031-survey-layer.json`，对导出字段canonical_json原文的UTF-8字节计算SHA256，与sha256比较，并检查json.loads(canonical_json)等于snapshot后收件。不要对浏览器重新序列化的snapshot计算原始校验和。此后该航次业务记录只读。

种子时间固定在2026-11-18，全部航窗规则比较记录本身，不依赖当前系统时间，因此以后仍能演示。上海日期用于网具有效期，数据库时间存UTC。

## 聚类与评价口径

`backend/src/algorithm.py` 用局部投影 `x=R*cos(lat0)*Δlon`、`y=R*Δlat`把经纬度转米制，再按60m空间、3m水深、8dB回波强度缩放四维特征，DBSCAN按用户eps与min_samples识别聚集和-1噪点。输入校验和是实际缩放数组SHA256。

参数敏感性分别计算eps0.8/1.2/1.6下实际点的群落数、噪点数。独立合成参照以seed37生成3簇及噪点共120点，按合成标签分层留出36点、其余84点为参照开发集，固定参数下在留出子集独立聚类，计算ARI。DBSCAN是无监督方法，不进行监督训练或把ARI称作真实鱼类准确率。留出参照仅内部检查尺度和稳定性；真实生态效度需要独立实测标签。

worker从Redis队列领取任务，保存assignments、metrics、失败原因，并写共享artifacts卷。回波版本变化使在途旧版本任务失败或无法复核；队列发送失败标failed返回503，可恢复后重新提交。页面展示真实点绘成的航迹和深度剖面，不用假图。

## 底质杂波筛选与留验

底质回波连成串时同样会被DBSCAN聚成“鱼群”。主管在群落复核页（或杂波筛选页）对回波点逐点标记 `bottom`（确定底质）或 `fish`（确定鱼群），每回波至多一个标记、可撤销。

- **留验隔离**：航次可由主管标为留验（`Cruise.holdout`）。训练只读取非留验航次上的标记；留验航次的标记全程不参与训练，仅在训练时做一次性验收比对，避免监督信息泄漏。
- **训练**：`clutter.py` 在与聚类同口径的米制缩放坐标上构造水深、强度、相对沿程位置、最近邻距离与局部密度五维特征，用固定2000轮、学习率0.05的确定性批量梯度下降逻辑回归拟合，模型参数与训练输入SHA256随版本入库。非留验标记底/鱼各≥8且总数≥16，留验标记底/鱼各≥4且总数≥16才可训练。
- **验收口径**：在留验航次上以固定 eps1.2/min_samples4 分别跑“原识别（全量）”与“筛选后（先剔除再聚类）”。误报底质=主管标底质却被赋予鱼群簇标签的点数；漏鱼=主管标鱼群却未进入鱼群（噪点或被剔除）的点数。仅当筛选后误报底质**严格少于**原识别、且漏鱼**不多于**原识别，版本才标记验收通过。未通过的候选版本不可启用。
- **版本生命周期**：训练产物为 `candidate` 候选；主管启用时旧启用版本转 `superseded`，全局至多一个 `enabled`；候选可拒绝（`rejected`），已启用版本须先被新版本替代。
- **排队即固定**：提交识别时把当时的启用版本写入 `SchoolAnalysis.filter_version_id`。worker 仅按该固定版本剔除底质后再聚类，并记录 `filtered_echo_ids/filtered_count`；版本后续启停不影响在途任务。失败重试（`/schools/{id}/retry`）沿用原固定版本，不切换到当前启用版本；回波已更新则拒绝重试，须按新版本重新提交。
- **留底与封存**：被剔除回波不从 `echoes` 删除，照常出现在封存快照的 `layers[].echoes`；每层另存 `clutter_filter`（当次版本号、剔除计数与逐点ID），快照顶层附全部 `clutter_filter_versions` 历史与留验指标。

## 代码与事务

| 路径 | 职责 |
|---|---|
| backend/src/models.py、schemas.py | Cruise/NavigationClosure、Transect/Echo、SchoolAnalysis/Review、Net/Calibration/BioSample、MissingInterval/Resurvey、SurveyRelease关系模型与输入契约 |
| navigation_service.py | 航窗、潮汐冲突、同船占用与开返航 |
| transect_service.py、school_service.py、algorithm.py、worker.py | 航段长度、探头范围、版本化回波、实际聚类和噪点复核 |
| clutter.py、clutter_service.py | 底质/鱼群标记、确定性逻辑回归训练、留验验收口径与筛选版本启停 |
| biology_service.py、resurvey_service.py、release_service.py | 网具、生物样、补测地理接续与JSON冻结 |
| common.py、auth.py、middlewares.py | 根锁、三角色JWT、动作审计、请求追踪和突发限流 |
| frontend/src/pages | 六个业务页加杂波筛选页（原生ES modules） |
| frontend/src/components | voyage-context跨页航次/航段、survey-map真实航迹剖面、echo-marker点图标记、controls表单表格 |
| frontend/src/api、stores、utils | 请求与会话、航次上下文、格式与保存反馈 |

航船调度按Station→Boat→Cruise锁序；现场业务先锁Cruise根再锁Transect/子记录，补航并发规划在同一根锁下保证一缺测一在途。冻结与现场修改共用Cruise根，防止一边写回波一边交付快照。

后端`constants.py` Role/CruiseState/AnalysisState在seed与模型引用，对应前端`constants/enums.js`roles/cruiseStates/analysisStates用于外壳与页面。航次planned/sailing/surveyed/frozen；分析queued/running/done/reviewed/failed。状态转换由服务端统一校验。

## 开发和范围

Python3.12、FastAPI、SQLAlchemy、PostgreSQL16、Redis7、NumPy、scikit-learn；前端Nginx+原生HTML/CSS/JS，无框架或Node构建。字体Noto Sans SC与IBM Plex Mono；Google Fonts不可用时分别回退sans-serif/monospace。

`.env.example`提供COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、COMPOSE_SUBNET、JWT_SECRET、SEED_DEMO；`.env`忽略提交。SEED_DEMO=true自动插入缺失自然键，不覆盖修改或重复增加记录。后端开发在Python3.12虚拟环境安装backend/requirements.txt，设置DATABASE_URL和REDIS_URL，在backend目录运行`uvicorn src.app:app --reload`。

`docker compose logs -f backend worker`观察运行；`docker compose down -v --remove-orphans`停止并删除本项目演示数据。工作区`test-artifacts/gb-1037/`保存脚本、JSON证据与截图，与源码分离。

已知范围：局部河口短航段近似投影适用于本题演示，非全球航海导航；只演示固定seed模拟探头与人工JSON现场输入，没有真实声呐设备协议、物种自动识别、外部生态标签或安全航行保证；补测为原航段直线区间接续；网具硬件证书由主管人工核对；数据库使用首次create_all，无历史迁移链。

MIT License，见LICENSE。
