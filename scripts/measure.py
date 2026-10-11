"""Measure the local HTTP + SSE workflow on a documented synthetic dataset.

Run only against a disposable validation database: this resets the selected
scenario and injects synthetic incidents. No accuracy or production claim.
"""
import json
import math
import os
import platform
import statistics
import threading
import time
from pathlib import Path
import httpx

BASE=os.environ.get('MISSION_SYNC_API_URL','http://127.0.0.1:8000/api/v1')

def stats(samples):
    values=sorted(samples)
    return {'samples':len(values),'p50_ms':round(statistics.median(values),3),'p95_ms':round(values[math.ceil(len(values)*.95)-1],3),'max_ms':round(max(values),3)}

with httpx.Client(base_url=BASE,timeout=30) as api:
    auth=api.post('/auth/demo',json={'role':'administrator'});auth.raise_for_status()
    api.headers['Authorization']='Bearer '+auth.json()['token']
    api.post('/simulator/scenarios/kolkata-flood/load',json={'confirmed':True}).raise_for_status()
    api.post('/simulator/reset',json={'scenario_id':'kolkata-flood','confirmed':True}).raise_for_status()
    settings=api.get('/settings').json()
    api.patch('/settings',json={'expected_version':settings['version'],'weights':{'people':.35,'damage':.25,'response':.20,'conflict':-.10,'friction':-.10}}).raise_for_status()
    initial=api.get('/state').json()
    measures={}
    for name,path,count,method in [('dashboard_http','/dashboard/summary',50,'GET'),('proposal_http','/missions/generate',30,'POST')]:
        samples=[]
        for _ in range(count):
            start=time.perf_counter()
            response=api.get(path) if method=='GET' else api.post(path,json={})
            response.raise_for_status()
            samples.append((time.perf_counter()-start)*1000)
        measures[name]=stats(samples)
    replay=api.get('/events/stream',params={'once':'true'});replay.raise_for_status()
    ids=[int(line[4:]) for line in replay.text.splitlines() if line.startswith('id: ')]
    last=max(ids,default=0)
    received={};ready=threading.Event();stop=threading.Event();stream_error=[]
    def listen():
        try:
            with httpx.Client(timeout=httpx.Timeout(10,read=3)) as reader:
                with reader.stream('GET',BASE+'/events/stream',headers={'Last-Event-ID':str(last)}) as stream:
                    stream.raise_for_status()
                    ready.set()
                    for line in stream.iter_lines():
                        if line.startswith('data: '):
                            event=json.loads(line[6:])
                            if event['type']=='incident.created':
                                received[event['data']['entity_id']]=time.perf_counter()
                        if stop.is_set():
                            return
        except Exception as error:
            stream_error.append(type(error).__name__)
            ready.set()
    reader=threading.Thread(target=listen,daemon=True);reader.start()
    assert ready.wait(5),'SSE did not connect'
    ingestion=[];live=[]
    for index in range(10):
        start=time.perf_counter()
        response=api.post('/simulator/incidents',json={'title':f'Measured synthetic event {index:02}','description':'Disposable local benchmark input','category':'medical','coordinates':{'lat':22.57+index*.001,'lng':88.36},'people_at_risk':50,'damage_severity':6,'response_time_minutes':25,'source_reliability':.9})
        response.raise_for_status();iid=response.json()['id']
        ingestion.append((time.perf_counter()-start)*1000)
        deadline=time.perf_counter()+5
        while iid not in received and time.perf_counter()<deadline:
            time.sleep(.01)
        assert iid in received,f'No committed SSE update for {iid}; stream errors {stream_error}'
        live.append((received[iid]-start)*1000)
    stop.set()
    measures['event_ingestion_http']=stats(ingestion)
    measures['accepted_request_to_sse']=stats(live)
    stress=api.post('/simulator/stress-tests',json={'event_count':100});stress.raise_for_status();stress_id=stress.json()['id']
    deadline=time.perf_counter()+10
    while time.perf_counter()<deadline:
        result=api.get('/simulator/stress-tests/'+stress_id).json()
        if result['status'] in ['completed','failed']:
            break
        time.sleep(.05)
    assert result['status']=='completed',result
    report={'environment':{'python':platform.python_version(),'platform':platform.platform(),'cpu_count':os.cpu_count(),'external_inference':False},'dataset':{'initial_incidents':len(initial['incidents']),'resources':len(initial['resources']),'injected_events':10,'final_incidents':len(api.get('/state').json()['incidents'])},'measurements':measures,'planner_microbenchmark':result['metrics'],'notes':['Loopback HTTP plus committed SSE reception; UI rendering excluded from SSE timings.','Event samples include server ingestion, agents, scoring, planning and persistence.','No labeled ranking accuracy or conflict precision/recall claimed.']}
    Path('.local').mkdir(exist_ok=True)
    Path('.local/performance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
