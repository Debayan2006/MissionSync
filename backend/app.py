"""MissionSync local synthetic API. Run: uvicorn backend.app:app --host 127.0.0.1."""
import asyncio
import hashlib
import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from fastapi import BackgroundTasks, Body, Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException
from . import models
from .service import Service, SCENARIOS, fail
from .store import now

RANK={'viewer':0,'analyst':1,'commander':2,'administrator':3}

def create_app(database_path=None):
    @asynccontextmanager
    async def lifespan(application):
        application.state.service=Service(database_path or os.environ.get('MISSION_SYNC_DB',str(Path(__file__).resolve().parents[1]/'.local'/'missionsync.db')))
        application.state.rate_limits=defaultdict(deque)
        async def generator():
            elapsed=0
            while True:
                await asyncio.sleep(1)
                elapsed+=1
                svc=application.state.service
                with svc.store.transaction() as db:
                    interval=svc.store.meta(db,'settings')['event_interval_seconds']
                    paused=svc.simulation(db)['paused']
                if paused:
                    elapsed=0
                elif elapsed>=interval:
                    try:
                        await asyncio.to_thread(svc.tick)
                    except Exception:
                        # Agent/provider failure is visible, never silently discarded.
                        with svc.store.transaction() as db:
                            simulation=svc.simulation(db)
                            simulation['paused']=True
                            svc.store.set_meta(db,'simulation',simulation)
                            svc.store.event(db,'simulation.error',{'message':'Scheduled coordination failed; simulator paused. Retry analysis or inspect server diagnostics.'})
                    elapsed=0
        task=asyncio.create_task(generator())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    application=FastAPI(title='MissionSync synthetic coordination API',version='1.0.0',lifespan=lifespan)
    application.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:4173','http://localhost:4173'],allow_methods=['GET','POST','PATCH'],allow_headers=['Authorization','Content-Type','Idempotency-Key','Last-Event-ID'])

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail=exc.detail if isinstance(exc.detail,dict) else {'code':'request_failed','message':str(exc.detail)}
        return JSONResponse({'error':detail,'detail':detail.get('message')},status_code=exc.status_code,headers=exc.headers)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Validation messages do not echo user bodies or secret values.
        details=[{'field':'.'.join(str(part) for part in e['loc']),'message':e['msg']} for e in exc.errors()]
        return JSONResponse({'error':{'code':'validation_error','message':'Request validation failed','fields':details},'detail':'Request validation failed'},status_code=422)

    @application.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse({'error':{'code':'internal_error','message':'The request could not complete. Retry or inspect local server diagnostics.'},'detail':'The request could not complete.'},status_code=500)

    def service(request:Request):
        return request.app.state.service

    def permission(minimum):
        def check(request:Request, authorization:Annotated[str|None,Header()]=None):
            environment=os.environ.get('MISSION_SYNC_ENV','development').lower()
            enabled=os.environ.get('MISSION_SYNC_DEMO_AUTH','true').lower() in ['true','1','yes']
            if environment in ['production','prod'] or not enabled:
                fail(401,'demo_sessions_disabled','Local demo sessions are disabled. Configure deployment authentication separately.')
            if not authorization or not authorization.startswith('Bearer '):
                fail(401,'authentication_required','Use a local demo role session before changing synthetic data.')
            token_hash=hashlib.sha256(authorization[7:].encode()).hexdigest()
            svc=service(request)
            with svc.store.transaction() as db:
                session=db.execute('SELECT role,expires_at FROM sessions WHERE token_hash=?',(token_hash,)).fetchone()
            if not session or session['expires_at']<time.time():
                fail(401,'invalid_session','Demo session is missing or expired. Choose your role again.')
            if RANK[session['role']]<RANK[minimum]:
                fail(403,'forbidden',f'This action requires the {minimum} role.')
            key=token_hash
            limits=request.app.state.rate_limits[key]
            stamp=time.monotonic()
            while limits and limits[0]<stamp-60:
                limits.popleft()
            if len(limits)>=120:
                fail(429,'rate_limit','Too many mutation requests. Retry in a minute.')
            limits.append(stamp)
            return f'demo:{session["role"]}:{token_hash[:8]}'
        return check

    analyst=Depends(permission('analyst'))
    commander=Depends(permission('commander'))
    admin=Depends(permission('administrator'))

    def mutation(request, actor, payload, operation):
        svc=service(request)
        key=request.headers.get('Idempotency-Key')
        if key and (len(key)>160 or len(key)<3):
            fail(422,'invalid_idempotency_key','Idempotency key must contain 3 to 160 characters.')
        fingerprint=hashlib.sha256(json.dumps({'method':request.method,'path':request.url.path,'actor':actor,'payload':payload},sort_keys=True).encode()).hexdigest()
        with svc.store.transaction() as db:
            if key:
                row=db.execute('SELECT response FROM idempotency WHERE key=?',(key,)).fetchone()
                if row:
                    cached=json.loads(row['response'])
                    if cached['fingerprint']!=fingerprint:
                        fail(409,'idempotency_conflict','This event ID has already been used with a different request.')
                    return cached['result']
            result=operation(svc,db)
            if key:
                db.execute('INSERT INTO idempotency(key,response) VALUES(?,?)',(key,json.dumps({'fingerprint':fingerprint,'result':result})))
            return result

    def paginate(items, request, search_fields=None, filters=True):
        query=request.query_params
        search=(query.get('search') or query.get('q') or '').strip().lower()
        if search:
            fields=search_fields or ['title','name','description','action','entity_id','reason','agent_id']
            items=[item for item in items if any(search in str(item.get(field,'')).lower() for field in fields)]
        if filters:
            for key in ['category','status','priority_band','type','agent_id','incident_id','entity_type','actor_id']:
                value=query.get(key)
                if key=='priority_band':
                    value=value or query.get('priority')
                if value and value!='all':
                    items=[item for item in items if str(item.get(key))==value or (key=='incident_id' and value in item.get('entity_ids',[]))]
        sort=query.get('sort') or query.get('sort_by')
        if sort:
            descending=sort.startswith('-') or query.get('order')=='desc'
            sort=sort.lstrip('-')
            if sort not in ['priority_score','reported_at','updated_at','created_at','timestamp','name','title','proposal_version','started_at','queued_at','capacity']:
                fail(400,'invalid_sort','Unsupported sort field')
            items=sorted(items,key=lambda i:(i.get(sort) is not None,i.get(sort) or ''),reverse=descending)
        try:
            page=int(query.get('page','1'));page_size=int(query.get('page_size','50'))
        except ValueError:
            fail(422,'invalid_pagination','Pagination values must be integers')
        if page<1 or page_size<1 or page_size>200:
            fail(422,'invalid_pagination','page must be >= 1 and page_size between 1 and 200')
        return {'items':items[(page-1)*page_size:page*page_size],'total':len(items),'page':page,'page_size':page_size}

    @application.get('/api/v1/health')
    def health():
        return {'status':'ok','service':'MissionSync','synthetic':True,'dispatch_enabled':False}

    @application.get('/api/v1/ready')
    def ready(request:Request):
        svc=service(request)
        try:
            with svc.store.transaction() as db:
                db.execute('SELECT 1').fetchone()
        except Exception:
            fail(503,'database_unavailable','The local database is unavailable.')
        return {'status':'ready','database':'sqlite','optional_providers_required':False}

    @application.post('/api/v1/auth/demo')
    def demo_login(body:models.Login,request:Request):
        environment=os.environ.get('MISSION_SYNC_ENV','development').lower()
        enabled=os.environ.get('MISSION_SYNC_DEMO_AUTH','true').lower() in ['true','1','yes']
        if environment in ['production','prod'] or not enabled:
            fail(403,'demo_auth_disabled','Local demo login is disabled. Configure deployment authentication separately.')
        token=secrets.token_urlsafe(32)
        with service(request).store.transaction() as db:
            db.execute('INSERT INTO sessions(token_hash,role,expires_at) VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),body.role,time.time()+43200))
        return {'token':token,'role':body.role,'expires_in':43200,'authentication_mode':'local_demo_only'}

    @application.get('/api/v1/state')
    def state(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return svc.snapshot(db)

    @application.get('/api/v1/dashboard/summary')
    def summary(request:Request,time_range:str='24h'):
        if time_range not in ['1h','6h','24h','7d']:
            fail(422,'invalid_time_range','Supported ranges: 1h, 6h, 24h, 7d')
        svc=service(request)
        duration={'1h':1,'6h':6,'24h':24,'7d':168}[time_range]
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=duration)).isoformat().replace('+00:00','Z')
        with svc.store.transaction() as db:
            result=svc.summary(db,time_range)
            result['recent_incidents']=sum(i['reported_at']>=cutoff for i in svc.entities(db,'incident'))
            result['recent_actions']=sum(i['timestamp']>=cutoff for i in svc.store.audits(db))
            return result

    @application.get('/api/v1/dashboard/activity')
    def activity(request:Request,time_range:str='24h'):
        if time_range not in ['1h','6h','24h','7d']:
            fail(422,'invalid_time_range','Supported ranges: 1h, 6h, 24h, 7d')
        cutoff=(datetime.now(timezone.utc)-timedelta(hours={'1h':1,'6h':6,'24h':24,'7d':168}[time_range])).isoformat().replace('+00:00','Z')
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate([a for a in svc.store.audits(db) if a['timestamp']>=cutoff],request)

    @application.get('/api/v1/events/stream')
    async def event_stream(request:Request,once:bool=False,since:int=0):
        header=request.headers.get('Last-Event-ID')
        try:
            sequence=int(header) if header else since
        except ValueError:
            fail(422,'invalid_event_id','Last-Event-ID must be an integer')
        if sequence<0:
            fail(422,'invalid_event_id','Event sequence cannot be negative')
        svc=service(request)
        async def stream():
            cursor=sequence;heartbeats=0
            yield 'retry: 2000\n\n'
            while True:
                # DB reads see committed rows; nothing is broadcast inside a transaction.
                events=await asyncio.to_thread(svc.store.events_after,cursor)
                for event in events:
                    cursor=int(event['id'])
                    yield f'id: {event["id"]}\nevent: {event["type"]}\ndata: {json.dumps(event)}\n\n'
                if once:
                    if len(events)==200:
                        continue
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(.5)
                heartbeats+=1
                if heartbeats>=30:
                    yield ': heartbeat\n\n'
                    heartbeats=0
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    @application.get('/api/v1/incidents')
    def incidents(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate(sorted(svc.entities(db,'incident'),key=lambda i:i.get('priority_score',0),reverse=True),request)

    @application.post('/api/v1/incidents',status_code=201)
    def incident_create(body:models.IncidentCreate,request:Request,actor=analyst):
        data=body.model_dump()
        return mutation(request,actor,data,lambda svc,db:svc.create_incident(db,data,actor))

    @application.get('/api/v1/incidents/{incident_id}')
    def incident_get(incident_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            item=svc.require(db,'incident',incident_id)
            item['assignments']=[a for a in svc.assignments(db) if a['incident_id']==incident_id]
            item['related_proposals']=[m['id'] for m in svc.entities(db,'mission') if incident_id in m['incident_ids']]
            return item

    @application.patch('/api/v1/incidents/{incident_id}')
    def incident_patch(incident_id:str,body:models.IncidentPatch,request:Request,actor=analyst):
        data=body.model_dump(exclude_unset=True)
        return mutation(request,actor,data,lambda svc,db:svc.patch_incident(db,incident_id,data.copy(),actor))

    @application.post('/api/v1/incidents/{incident_id}/analyze',status_code=202)
    def incident_analyze(incident_id:str,request:Request,background:BackgroundTasks,body:models.Empty|None=Body(default=None),actor=analyst):
        def operation(svc,db):
            svc.require(db,'incident',incident_id)
            return {'runs':svc.enqueue_analysis(db,actor,[incident_id]),'mission':None,'status':'queued'}
        result=mutation(request,actor,{},operation)
        background.add_task(service(request).execute_analysis,result['runs'],actor,[incident_id])
        return result

    @application.get('/api/v1/incidents/{incident_id}/evidence')
    def incident_evidence(incident_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate(svc.require(db,'incident',incident_id)['evidence'],request,filters=False)

    @application.get('/api/v1/incidents/{incident_id}/history')
    def incident_history(incident_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            svc.require(db,'incident',incident_id)
            return paginate(svc.store.audits(db,incident_id),request)

    @application.get('/api/v1/agents')
    def agents(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate(svc.registry(db),request)

    @application.get('/api/v1/agents/runs')
    def agent_runs(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate(sorted(svc.entities(db,'run'),key=lambda r:r['queued_at'],reverse=True),request)

    @application.post('/api/v1/agents/runs',status_code=202)
    def run_create(body:models.Analyze,request:Request,background:BackgroundTasks,actor=analyst):
        data=body.model_dump()
        def operation(svc,db):
            if body.incident_id:
                svc.require(db,'incident',body.incident_id)
            runs=svc.enqueue_analysis(db,actor,[body.incident_id] if body.incident_id else None,body.agent_id)
            return {'run':runs[0],'runs':runs}
        result=mutation(request,actor,data,operation)
        background.add_task(service(request).execute_analysis,result['runs'],actor,[body.incident_id] if body.incident_id else None,body.agent_id)
        return result['run']

    @application.get('/api/v1/agents/runs/{run_id}')
    def run_get(run_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return svc.require(db,'run',run_id)

    @application.post('/api/v1/agents/runs/{run_id}/retry',status_code=202)
    def run_retry(run_id:str,request:Request,background:BackgroundTasks,body:models.Empty|None=Body(default=None),actor=analyst):
        def operation(svc,db):
            previous=svc.require(db,'run',run_id)
            if previous['status']!='failed':
                fail(409,'run_not_retryable','Only failed agent runs can be retried.')
            return svc.enqueue_analysis(db,actor,[previous['incident_id']] if previous['incident_id'] else None,previous['agent_id'],retry_of=run_id)[0]
        result=mutation(request,actor,{},operation)
        background.add_task(service(request).execute_analysis,[result],actor,[result['incident_id']] if result['incident_id'] else None,result['agent_id'])
        return result

    @application.get('/api/v1/agents/{agent_id}')
    def agent_get(agent_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            agent=next((a for a in svc.registry(db) if a['id']==agent_id),None)
            if not agent:
                fail(404,'not_found','Agent was not found')
            return agent

    @application.get('/api/v1/resources')
    def resources(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate(svc.entities(db,'resource'),request)

    @application.post('/api/v1/resources',status_code=201)
    def resource_create(body:models.ResourceCreate,request:Request,actor=analyst):
        data=body.model_dump()
        return mutation(request,actor,data,lambda svc,db:svc.create_resource(db,data,actor))

    @application.get('/api/v1/resources/availability')
    def availability(request:Request,at:str|None=None):
        svc=service(request)
        with svc.store.transaction() as db:
            if at:
                try:
                    selected=datetime.fromisoformat(at.replace('Z','+00:00'))
                    if not selected.tzinfo:
                        raise ValueError()
                except ValueError:
                    fail(422,'invalid_time','at must be a timezone-aware ISO timestamp')
            else:
                selected=datetime.now(timezone.utc)
            assignments=svc.assignments(db)
            values=[]
            for resource in svc.entities(db,'resource'):
                overlaps=[a for a in assignments if a['resource_id']==resource['id'] and datetime.fromisoformat(a['start_at'].replace('Z','+00:00'))<=selected<datetime.fromisoformat(a['end_at'].replace('Z','+00:00'))]
                available=resource['status']!='unavailable' and not overlaps
                values.append({**resource,'available_at_requested_time':available,'available_capacity':resource['capacity'] if available else 0,'requested_at':selected.isoformat(),'assignments':overlaps})
            return paginate(values,request)

    @application.get('/api/v1/resources/{resource_id}')
    def resource_get(resource_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return svc.require(db,'resource',resource_id)

    @application.patch('/api/v1/resources/{resource_id}')
    def resource_patch(resource_id:str,body:models.ResourcePatch,request:Request,actor=analyst):
        data=body.model_dump(exclude_unset=True)
        return mutation(request,actor,data,lambda svc,db:svc.patch_resource(db,resource_id,data.copy(),actor))

    @application.get('/api/v1/resources/{resource_id}/assignments')
    def resource_assignments(resource_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            svc.require(db,'resource',resource_id)
            return paginate([a for a in svc.assignments(db) if a['resource_id']==resource_id],request,filters=False)

    @application.get('/api/v1/missions')
    def missions(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate(sorted(svc.entities(db,'mission'),key=lambda m:m['proposal_version'],reverse=True),request)

    @application.post('/api/v1/missions/generate',status_code=201)
    def mission_generate(request:Request,body:models.Generate|None=Body(default=None),actor=analyst):
        data=body.model_dump() if body else {}
        return mutation(request,actor,data,lambda svc,db:svc.coordinate(db,actor,data.get('incident_ids')))

    @application.get('/api/v1/missions/{mission_id}')
    def mission_get(mission_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return svc.require(db,'mission',mission_id)

    @application.post('/api/v1/missions/{mission_id}/regenerate',status_code=201)
    def mission_regenerate(mission_id:str,request:Request,body:models.Empty|None=Body(default=None),actor=analyst):
        def operation(svc,db):
            previous=svc.require(db,'mission',mission_id)
            return svc.coordinate(db,actor,previous['incident_ids'],parent_id=mission_id)
        return mutation(request,actor,{},operation)

    @application.get('/api/v1/missions/{mission_id}/conflicts')
    def mission_conflicts(mission_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            mission=svc.require(db,'mission',mission_id)
            return paginate(mission.get('current_conflicts',mission['conflicts']),request,filters=False)

    @application.post('/api/v1/missions/{mission_id}/approve')
    def mission_approve(mission_id:str,body:models.Approve,request:Request,actor=commander):
        data=body.model_dump()
        return mutation(request,actor,data,lambda svc,db:svc.decision(db,mission_id,data,actor,'approve'))

    @application.post('/api/v1/missions/{mission_id}/reject')
    def mission_reject(mission_id:str,body:models.Reject,request:Request,actor=commander):
        data=body.model_dump()
        return mutation(request,actor,data,lambda svc,db:svc.decision(db,mission_id,data,actor,'reject'))

    @application.post('/api/v1/missions/{mission_id}/request-revision',status_code=201)
    def mission_revision(mission_id:str,body:models.Revision,request:Request,actor=commander):
        data=body.model_dump()
        return mutation(request,actor,data,lambda svc,db:svc.decision(db,mission_id,data,actor,'request_revision'))

    @application.get('/api/v1/missions/{mission_id}/history')
    def mission_history(mission_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            svc.require(db,'mission',mission_id)
            return paginate(svc.store.audits(db,mission_id),request)

    @application.get('/api/v1/simulator/scenarios')
    def scenarios(request:Request):
        return paginate(SCENARIOS,request,filters=False)

    @application.post('/api/v1/simulator/scenarios/{scenario_id}/load')
    def scenario_load(scenario_id:str,body:models.Load,request:Request,actor=analyst):
        if not body.confirmed:
            fail(422,'confirmation_required','Confirm replacement of this selected synthetic scenario.')
        return mutation(request,actor,body.model_dump(),lambda svc,db:svc.load(db,scenario_id,actor))

    @application.post('/api/v1/simulator/incidents',status_code=201)
    def simulator_incident(body:models.IncidentCreate,request:Request,actor=analyst):
        data=body.model_dump()
        return mutation(request,actor,data,lambda svc,db:svc.create_incident(db,data,actor))

    @application.post('/api/v1/simulator/weather')
    def simulator_weather(body:models.Weather,request:Request,actor=analyst):
        data=body.model_dump(exclude_unset=True)
        def operation(svc,db):
            simulation=svc.simulation(db);weather=simulation['weather'];before=weather.copy()
            if body.expected_version is not None and body.expected_version!=weather['version']:
                fail(409,'version_conflict','Weather changed; refresh its current version.')
            weather.update(hazard_risk=body.hazard_risk,access_blocked=body.access_blocked,version=weather['version']+1,updated_at=now())
            svc.store.set_meta(db,'simulation',simulation)
            mission=svc.material_changed(db,actor,'weather.updated','synthetic-weather',before,weather)
            return {'weather':weather,'mission':mission,'simulation':svc.simulation(db)}
        return mutation(request,actor,data,operation)

    @application.post('/api/v1/simulator/resources',status_code=201)
    def simulator_resource(body:models.SimResource,request:Request,actor=analyst):
        data=body.model_dump(exclude_unset=True)
        def operation(svc,db):
            payload=data.copy();entity_id=payload.pop('resource_id',None)
            if entity_id:
                if payload.get('expected_version') is None:
                    fail(422,'expected_version_required','Resource updates require expected_version')
                return svc.patch_resource(db,entity_id,payload,actor)
            payload.pop('expected_version',None)
            try:
                checked=models.ResourceCreate.model_validate(payload)
            except Exception:
                fail(422,'invalid_resource','New resource needs name, type, coordinates and capacity.')
            return svc.create_resource(db,checked.model_dump(),actor)
        return mutation(request,actor,data,operation)

    @application.post('/api/v1/simulator/conflicts',status_code=201)
    def simulator_conflict(request:Request,body:models.Empty|None=Body(default=None),actor=analyst):
        def operation(svc,db):
            resources=svc.entities(db,'resource')
            rescue=next((r for r in resources if r['type']=='rescue'),None)
            if rescue:
                rescue=svc.patch_resource(db,rescue['id'],{'expected_version':rescue['version'],'status':'unavailable'},actor)
            incident=svc.create_incident(db,{'title':'Synthetic capacity conflict','description':'Controlled stress case: demand exceeds one unit and disabled access support.','category':'flood','coordinates':{'lat':22.598,'lng':88.372},'people_at_risk':1500,'damage_severity':9.5,'response_time_minutes':110,'source_reliability':.95},actor)
            mission=max(svc.entities(db,'mission'),key=lambda m:m['proposal_version'])
            return {'incident':incident,'resource':rescue,'mission':mission}
        return mutation(request,actor,{},operation)

    def pause_operation(svc,db,paused,actor):
        simulation=svc.simulation(db);before=simulation.copy();simulation['paused']=paused
        svc.store.set_meta(db,'simulation',simulation)
        svc.store.audit(db,actor,'simulation.paused' if paused else 'simulation.resumed','simulation',svc.scope(db),before,simulation,scenario=svc.scope(db))
        svc.store.event(db,'simulation.state_changed',simulation)
        return simulation

    @application.post('/api/v1/simulator/pause')
    def simulator_pause(request:Request,body:models.Empty|None=Body(default=None),actor=analyst):
        return mutation(request,actor,{},lambda svc,db:pause_operation(svc,db,True,actor))

    @application.post('/api/v1/simulator/resume')
    def simulator_resume(request:Request,body:models.Empty|None=Body(default=None),actor=analyst):
        return mutation(request,actor,{},lambda svc,db:pause_operation(svc,db,False,actor))

    @application.post('/api/v1/simulator/reset')
    def simulator_reset(body:models.Reset,request:Request,actor=admin):
        if not body.confirmed:
            fail(422,'confirmation_required','Reset requires confirmed:true and selected scenario_id.')
        return mutation(request,actor,body.model_dump(),lambda svc,db:svc.seed(db,body.scenario_id,body.scenario_id==svc.scope(db),actor))

    @application.post('/api/v1/simulator/stress-tests',status_code=202)
    def stress_create(request:Request,background:BackgroundTasks,body:models.Stress|None=Body(default=None),actor=analyst):
        data=body.model_dump() if body else {'event_count':20}
        result=mutation(request,actor,data,lambda svc,db:svc.enqueue_stress(db,data['event_count'],actor))
        background.add_task(service(request).execute_stress,result,actor)
        return result

    @application.get('/api/v1/simulator/stress-tests/{run_id}')
    def stress_get(run_id:str,request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return svc.require(db,'stress',run_id)

    @application.get('/api/v1/audit')
    def audit(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return paginate(svc.store.audits(db),request)

    @application.get('/api/v1/settings')
    def settings(request:Request):
        svc=service(request)
        with svc.store.transaction() as db:
            return svc.store.meta(db,'settings')

    @application.patch('/api/v1/settings')
    def settings_patch(body:models.SettingsPatch,request:Request,actor=admin):
        data=body.model_dump(exclude_unset=True)
        def operation(svc,db):
            item=svc.store.meta(db,'settings');before=item.copy()
            if item['version']!=body.expected_version:
                fail(409,'version_conflict','Settings changed; refresh before saving.')
            changes={k:v for k,v in data.items() if k!='expected_version'}
            item.update(changes);item['version']+=1
            svc.store.set_meta(db,'settings',item)
            svc.material_changed(db,actor,'settings.updated','settings',before,item)
            return item
        return mutation(request,actor,data,operation)

    return application

app=create_app()
