"""Persisted synthetic state and transactional coordination, without real dispatch."""
import copy
import hashlib
import json
import math
import time
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from .store import Store, now, uid
from .engine import CATEGORY_TYPES, score_incident, plan, detect_constraints

DEFAULT_WEIGHTS = {'people':.35,'damage':.25,'response':.20,'conflict':-.10,'friction':-.10}
AGENTS = [
    {'id':'vision','name':'Vision Agent','description':'Synthetic image damage evidence; no live feed or model inference.'},
    {'id':'incident','name':'Incident Agent','description':'Validates structured synthetic reports and preserves unknowns.'},
    {'id':'weather','name':'Weather / Terrain Agent','description':'Synthetic hazards, freshness, and access constraints.'},
    {'id':'resource','name':'Resource Agent','description':'Deterministic capacity, eligibility, exclusivity and availability checks.'},
    {'id':'risk','name':'Risk / Priority Agent','description':'Normalized configurable priority and factor contributions.'},
    {'id':'coordinator','name':'Mission Coordinator','description':'Versioned proposals and hard-constraint validation.'},
]
SCENARIOS = [
    {'id':'kolkata-flood','name':'Kolkata monsoon response','description':'Three synthetic incidents, six response units, clear initial access.','synthetic':True},
    {'id':'industrial-fire','name':'Industrial corridor fire','description':'A fire, medical surge and infrastructure outage.','synthetic':True},
]

def fail(status, code, message):
    raise HTTPException(status_code=status, detail={'code':code,'message':message})

class Service:
    def __init__(self, path):
        self.store = Store(path)
        with self.store.transaction() as db:
            if not self.store.meta(db,'settings'):
                self.store.set_meta(db,'settings',{'weights':DEFAULT_WEIGHTS,'event_interval_seconds':20,'version':1,'data_mode':'synthetic','dispatch_enabled':False,'priority_normalization':{'people':'min(people / 500, 1)','damage':'damage / 10','response':'min(delay_minutes / 120, 1); longer delay increases urgency','conflict':'fraction of unmet eligible capacity','friction':'assigned eligible resource fraction; penalizes reassignment','aggregate':'100 * clamp(weighted sum / sum positive weights, 0, 1); unknown terms stay null and contribute no value'}})
            if not self.store.meta(db,'simulation'):
                self.store.set_meta(db,'simulation',{'scenario_id':'kolkata-flood','paused':True,'weather':{'hazard_risk':.65,'access_blocked':False,'version':1,'updated_at':now(),'source':'synthetic'},'state_revision':1,'event_counter':0})
                self.seed(db,'kolkata-flood',activate=True,actor='system:seed')
            for kind in ['run','stress']:
                for interrupted in self.store.all(db,kind):
                    if interrupted['status'] in ['queued','running']:
                        interrupted.update(status='failed',completed_at=now(),error_message='Service restarted before this job completed. Retry the analysis or stress test.')
                        self.store.put(db,kind,interrupted)
                        self.store.event(db,'agent.run_failed' if kind=='run' else 'simulation.stress_test_failed',{'run_id':interrupted['id'],'reason':'interrupted_restart'})

    def simulation(self, db):
        return self.store.meta(db,'simulation')

    def scope(self, db):
        return self.simulation(db)['scenario_id']

    def entities(self, db, kind):
        return self.store.all(db,kind,self.scope(db))

    def require(self, db, kind, entity_id):
        value = self.store.get(db,kind,entity_id)
        if not value:
            fail(404,'not_found',f'{kind} {entity_id} was not found')
        if value.get('scenario_id') != self.scope(db):
            fail(409,'inactive_scenario','Entity belongs to a different simulation scope. Load its scenario first.')
        return value

    def bump(self, db):
        simulation = self.simulation(db)
        simulation['state_revision'] += 1
        self.store.set_meta(db,'simulation',simulation)
        return simulation

    def material_changed(self, db, actor, event_type, entity_id, before=None, after=None, reason=None):
        scope = self.scope(db)
        self.bump(db)
        for mission in self.entities(db,'mission'):
            if mission['status']=='pending_review':
                mission['status']='stale'
                mission['current_conflicts']=self.validate(db,mission['assignments'],incident_ids=mission['incident_ids'])
                mission['warnings'].append('Material inputs changed; regenerate before approving.')
                mission['updated_at']=now()
                self.store.put(db,'mission',mission)
            elif mission['status']=='approved':
                current_conflicts = self.validate(db,mission['assignments'],exclude_mission=mission['id'],incident_ids=mission['incident_ids'])
                mission['current_conflicts']=current_conflicts
                mission['requires_review']=bool(current_conflicts)
                self.store.put(db,'mission',mission)
        self.store.audit(db,actor,event_type,event_type.split('.')[0],entity_id,before,after,reason,scope)
        self.store.event(db,event_type,{'entity_id':entity_id,'scenario_id':scope,'state_revision':self.simulation(db)['state_revision']})
        return self.coordinate(db,actor=actor)

    def seed(self, db, scenario, activate, actor):
        if scenario not in [item['id'] for item in SCENARIOS]:
            fail(404,'scenario_not_found','Unknown synthetic scenario')
        db.execute('DELETE FROM entities WHERE scenario_id=?',(scenario,))
        prefix = 'kf' if scenario=='kolkata-flood' else 'if'
        timestamp=now()
        specs = [
            ('Riverside evacuation','flood',420,8,65,22.584,88.354,'Water has entered the synthetic riverside district. Residents need assisted evacuation.'),
            ('Warehouse fire','fire',180,7,45,22.569,88.392,'Synthetic warehouse smoke reports suggest two affected blocks.'),
            ('Clinic power failure','medical',80,6,35,22.548,88.371,'Backup power has failed in this simulated clinic. Patients need support.'),
        ]
        if scenario=='industrial-fire':
            specs=[('Industrial plant fire','fire',320,9,85,22.607,88.405,'Synthetic chemical-storage smoke report; no real observation.'),('Triage surge','medical',220,7,55,22.589,88.415,'Synthetic injuries reported near the industrial corridor.'),('Bridge inspection','infrastructure',90,5,30,22.576,88.408,'Synthetic access route needs engineering support.')]
        for index,(title,category,people,damage,response,lat,lng,description) in enumerate(specs,1):
            item={'id':f'{prefix}-incident-{index:03}','scenario_id':scenario,'title':title,'description':description,'category':category,'coordinates':{'lat':lat,'lng':lng},'people_at_risk':people,'damage_severity':damage,'response_time_minutes':response,'source_reliability':.9-index*.03,'hazard_risk':.65,'status':'open','version':1,'reported_at':timestamp,'updated_at':timestamp,'synthetic':True,'evidence':self.evidence(f'{prefix}-incident-{index:03}',description,.9-index*.03)}
            self.store.put(db,'incident',item)
        types=['rescue','rescue','fire','fire','medical','logistics'] if scenario=='kolkata-flood' else ['fire','fire','medical','medical','logistics','rescue']
        for index,kind in enumerate(types,1):
            self.store.put(db,'resource',{'id':f'{prefix}-resource-{index:03}','scenario_id':scenario,'name':f'{kind.title()} unit {index:02}','type':kind,'coordinates':{'lat':22.565+index*.005,'lng':88.355+index*.006},'capacity':6,'available_capacity':6,'status':'available','estimated_response_time':15+index*4,'last_updated_at':timestamp,'version':1,'synthetic':True})
        self.store.set_meta(db,f'scenario_state:{scenario}',{'weather':{'hazard_risk':.65,'access_blocked':False,'version':1,'updated_at':timestamp,'source':'synthetic'},'event_counter':0})
        if activate:
            simulation=self.simulation(db)
            simulation.update({'scenario_id':scenario,'paused':True,'weather':{'hazard_risk':.65,'access_blocked':False,'version':simulation['weather']['version']+1,'updated_at':timestamp,'source':'synthetic'},'state_revision':simulation['state_revision']+1,'event_counter':0})
            self.store.set_meta(db,'simulation',simulation)
            mission=self.coordinate(db,actor=actor)
        else:
            mission=None
        self.store.audit(db,actor,'simulation.reset','simulation',scenario,after={'scenario_id':scenario,'synthetic':True},reason='Confirmed scenario-scoped reset; prior audit preserved.',scenario=scenario)
        self.store.event(db,'simulation.state_changed',{'scenario_id':scenario,'action':'load' if activate else 'reset'})
        return {'scenario_id':scenario,'mission':mission,'simulation':self.simulation(db)}

    def load(self, db, scenario, actor):
        """Switch scopes without giving analysts a destructive reset capability."""
        if scenario not in [item['id'] for item in SCENARIOS]:
            fail(404,'scenario_not_found','Unknown synthetic scenario')
        outgoing=self.simulation(db)
        self.store.set_meta(db,f'scenario_state:{outgoing["scenario_id"]}',{'weather':outgoing['weather'],'event_counter':outgoing['event_counter']})
        if not self.store.all(db,'incident',scenario):
            return self.seed(db,scenario,True,actor)
        simulation=self.simulation(db)
        current=simulation['scenario_id']
        self.store.set_meta(db,f'scenario_state:{current}',{'weather':simulation['weather'],'event_counter':simulation['event_counter']})
        saved=self.store.meta(db,f'scenario_state:{scenario}',{'weather':{'hazard_risk':.65,'access_blocked':False,'version':1,'updated_at':now(),'source':'synthetic'},'event_counter':0})
        simulation.update(scenario_id=scenario,paused=True,weather=saved['weather'],event_counter=saved['event_counter'],state_revision=simulation['state_revision']+1)
        self.store.set_meta(db,'simulation',simulation)
        for mission in self.entities(db,'mission'):
            if mission['status']=='pending_review':
                mission.update(status='stale',updated_at=now())
                mission['warnings'].append('Simulation scope reloaded; review the newly validated proposal.')
                mission['current_conflicts']=self.validate(db,mission['assignments'],incident_ids=mission['incident_ids'])
                self.store.put(db,'mission',mission)
        mission=self.coordinate(db,actor)
        self.store.audit(db,actor,'simulation.loaded','simulation',scenario,after={'scenario_id':scenario,'existing_data_preserved':True},reason='Load preserves existing scenario changes. Administrator reset restores fixtures.',scenario=scenario)
        self.store.event(db,'simulation.state_changed',{'scenario_id':scenario,'action':'load','existing_data_preserved':True})
        return {'scenario_id':scenario,'mission':mission,'simulation':simulation,'existing_data_preserved':True}

    @staticmethod
    def evidence(incident_id, description, confidence):
        return [{'id':f'{incident_id}-report','type':'synthetic_report','label':'Synthetic ground report','source':'MissionSync deterministic scenario','description':description,'confidence':confidence,'synthetic':True}, {'id':f'{incident_id}-image','type':'synthetic_image','label':'Simulated damage observation','source':'Synthetic fixture; no actual image inference','description':'Damage categories are derived from scenario inputs, not a live drone feed.','confidence':min(confidence,.8),'synthetic':True}]

    def create_incident(self, db, data, actor):
        item={'id':uid('inc'),'scenario_id':self.scope(db),**data,'version':1,'status':'open','reported_at':now(),'updated_at':now(),'synthetic':True,'hazard_risk':self.simulation(db)['weather']['hazard_risk']}
        item['evidence']=self.evidence(item['id'],item['description'],item['source_reliability'])
        self.store.put(db,'incident',item)
        self.material_changed(db,actor,'incident.created',item['id'],after=item)
        return self.store.get(db,'incident',item['id'])

    def patch_incident(self, db, entity_id, data, actor):
        item=self.require(db,'incident',entity_id)
        expected=data.pop('expected_version')
        if expected!=item['version']:
            fail(409,'version_conflict','Incident changed; refresh and retry with its current version.')
        before=copy.deepcopy(item)
        item.update(data)
        item.update(version=item['version']+1,updated_at=now())
        item['evidence']=self.evidence(item['id'],item['description'],item['source_reliability'])
        self.store.put(db,'incident',item)
        self.material_changed(db,actor,'incident.updated',entity_id,before,item)
        return self.store.get(db,'incident',entity_id)

    def create_resource(self, db, data, actor):
        item={'id':uid('res'),'scenario_id':self.scope(db),**data,'version':1,'last_updated_at':now(),'synthetic':True}
        item['available_capacity']=item['capacity'] if item['status']=='available' else 0
        self.store.put(db,'resource',item)
        self.material_changed(db,actor,'resource.created',item['id'],after=item)
        return self.store.get(db,'resource',item['id'])

    def patch_resource(self, db, entity_id, data, actor):
        item=self.require(db,'resource',entity_id)
        expected=data.pop('expected_version')
        if expected!=item['version']:
            fail(409,'version_conflict','Resource changed; refresh and retry with its current version.')
        before=copy.deepcopy(item)
        item.update(data)
        item.update(version=item['version']+1,last_updated_at=now())
        booked=sum(a['capacity'] for a in self.assignments(db) if a['resource_id']==item['id'])
        item['available_capacity']=max(0,item['capacity']-booked) if item['status']=='available' else 0
        if booked and item['status']=='available':
            item['status']='assigned'
            item['available_capacity']=0
        self.store.put(db,'resource',item)
        self.material_changed(db,actor,'resource.status_changed',entity_id,before,item)
        return self.store.get(db,'resource',entity_id)

    def assignments(self, db, exclude_mission=None):
        assignments=[]
        for mission in self.entities(db,'mission'):
            if mission['status']=='approved' and mission['id']!=exclude_mission:
                assignments.extend([{**a,'mission_id':mission['id']} for a in mission['assignments']])
        return assignments

    def validate(self, db, assignments, exclude_mission=None, incident_ids=None):
        resources=self.entities(db,'resource')
        if exclude_mission:
            booked_ids={a['resource_id'] for a in assignments}
            for resource in resources:
                if resource['id'] in booked_ids and resource['status']=='assigned':
                    resource['status']='available'
                    resource['available_capacity']=resource['capacity']
        incidents=self.entities(db,'incident')
        if incident_ids is not None:
            incidents=[i for i in incidents if i['id'] in incident_ids]
        return detect_constraints(assignments,incidents,resources,self.assignments(db,exclude_mission),self.simulation(db)['weather'])

    def versions(self, db, incident_ids=None):
        return {'incidents':{item['id']:item['version'] for item in self.entities(db,'incident') if incident_ids is None or item['id'] in incident_ids},'resources':{item['id']:item['version'] for item in self.entities(db,'resource')},'weather':self.simulation(db)['weather']['version'],'settings':self.store.meta(db,'settings')['version'],'state_revision':self.simulation(db)['state_revision']}

    def create_run(self, db, agent_id, incident, result, confidence, warnings, actor, input_snapshot, reserved_id=None):
        run={'id':uid('run'),'scenario_id':self.scope(db),'agent_id':agent_id,'incident_id':incident['id'] if incident else None,'entity_ids':[incident['id']] if incident else list(input_snapshot['incidents']),'status':'queued','input_snapshot':input_snapshot,'input_references':input_snapshot,'result':None,'confidence':None,'warnings':[],'queued_at':now(),'started_at':None,'completed_at':None,'error_message':None,'synthetic':True}
        if reserved_id:
            reserved=self.store.get(db,'run',reserved_id)
            run.update(id=reserved_id,queued_at=reserved['queued_at'],initial_input_snapshot=reserved['input_snapshot'],retry_of=reserved.get('retry_of'))
        else:
            self.store.put(db,'run',run)
            self.store.event(db,'agent.run_queued',{'run_id':run['id'],'agent_id':agent_id})
        run.update(status='running',started_at=now())
        self.store.put(db,'run',run)
        self.store.event(db,'agent.run_started',{'run_id':run['id'],'agent_id':agent_id})
        run.update(status='completed',result=result,confidence=confidence,warnings=warnings,completed_at=now())
        self.store.put(db,'run',run)
        self.store.event(db,'agent.run_completed',{'run_id':run['id'],'agent_id':agent_id,'status':'completed'})
        return run

    def coordinate(self, db, actor, incident_ids=None, parent_id=None, requested_agent=None, reserved_runs=None):
        started=time.perf_counter()
        incidents=self.entities(db,'incident')
        if incident_ids:
            unknown=set(incident_ids)-{i['id'] for i in incidents}
            if unknown:
                fail(404,'incident_not_found','Requested planning incident was not found')
            incidents=[i for i in incidents if i['id'] in incident_ids]
        resources=self.entities(db,'resource')
        assignments=self.assignments(db)
        settings=self.store.meta(db,'settings')
        weather=self.simulation(db)['weather'].copy()
        weather['planning_start_at']=now()
        versions=self.versions(db,[i['id'] for i in incidents])
        run_ids=[]
        for incident in incidents:
            prior_score=incident.get('priority_score')
            incident=score_incident(incident,resources,assignments,settings['weights'])
            incident['hazard_risk']=weather['hazard_risk']
            self.store.put(db,'incident',incident)
            if prior_score is not None and prior_score!=incident['priority_score']:
                self.store.event(db,'incident.priority_changed',{'incident_id':incident['id'],'priority_score':incident['priority_score'],'previous_score':prior_score})
            outputs={
                'vision':({'damage_categories':[incident['category']],'damage_severity':incident['damage_severity'],'evidence_references':[incident['evidence'][1]['id']],'processing_state':'synthetic_fixture','model_inference':False},min(incident['source_reliability'],.8),['Synthetic damage evidence; no uploaded image or live drone feed.']),
                'incident':({'category':incident['category'],'coordinates':incident['coordinates'],'severity':incident['damage_severity'],'affected_people':incident['people_at_risk'],'evidence_references':[incident['evidence'][0]['id']],'uncertainty':[f'{key} is unknown' for key in ['people_at_risk','damage_severity','response_time_minutes'] if incident.get(key) is None]},incident['source_reliability'],incident.get('warnings',[])),
                'weather':({'hazard_risk':weather['hazard_risk'],'access_blocked':weather['access_blocked'],'freshness':weather['updated_at'],'evidence_references':['synthetic-weather'],'source':'synthetic'},.85,['Weather and access conditions are synthetic.']),
                'resource':({'eligible_resources':[r['id'] for r in resources if r['status']=='available' and r['type'] in CATEGORY_TYPES[incident['category']]],'available_capacity':sum(r['available_capacity'] for r in resources if r['type'] in CATEGORY_TYPES[incident['category']]),'active_assignments':assignments,'validation':'deterministic'},1.0,[]),
                'risk':({'priority_score':incident['priority_score'],'priority_band':incident['priority_band'],'factors':incident['priority_factors'],'ranking_change':None if prior_score is None else incident['priority_score']-prior_score},incident.get('confidence',incident['source_reliability']),incident.get('warnings',[])),
            }
            for agent_id,(result,confidence,warnings) in outputs.items():
                if requested_agent is None or requested_agent==agent_id:
                    reserved_id=(reserved_runs or {}).get((agent_id,incident['id']))
                    run_ids.append(self.create_run(db,agent_id,incident,result,confidence,warnings,actor,versions,reserved_id)['id'])
        incidents=[self.store.get(db,'incident',i['id']) for i in incidents]
        proposal=plan(incidents,resources,assignments,weather,settings['weights'])
        existing=self.entities(db,'mission')
        proposal_version=max([m['proposal_version'] for m in existing],default=0)+1
        timestamp=now()
        proposal.update({'id':uid('mission'),'scenario_id':self.scope(db),'incident_ids':[i['id'] for i in incidents if i['status']!='resolved'],'proposal_version':proposal_version,'version':proposal_version,'parent_id':parent_id,'input_versions':versions,'created_at':timestamp,'updated_at':timestamp,'approver':None,'approved_at':None,'decision_reason':None,'synthetic':True,'dispatch_enabled':False,'agent_run_ids':run_ids,'generation_ms':round((time.perf_counter()-started)*1000,3)})
        if proposal['status']!='infeasible':
            proposal['status']='pending_review'
        if not proposal['assignments'] and not proposal['conflicts']:
            proposal['status']='infeasible'
            proposal['conflicts']=[{'type':'no_required_response','message':'No positive response demand is present in the selected open incidents.'}]
        proposal['warnings']=list(dict.fromkeys(proposal.get('warnings',[])+['Synthetic decision support only. Approval does not dispatch real resources.']))
        self.store.put(db,'mission',proposal)
        if requested_agent is None or requested_agent=='coordinator':
            reserved_id=(reserved_runs or {}).get(('coordinator',None))
            run=self.create_run(db,'coordinator',None,{'mission_id':proposal['id'],'proposal_version':proposal_version,'status':proposal['status'],'assignments':proposal['assignments'],'conflicts':proposal['conflicts'],'input_versions':versions},1.0 if proposal['status']!='infeasible' else .7,proposal['warnings'],actor,versions,reserved_id)
            proposal['agent_run_ids'].append(run['id'])
            self.store.put(db,'mission',proposal)
        self.store.audit(db,actor,'mission.generated','mission',proposal['id'],after=proposal,reason='Deterministic synthetic coordination loop',scenario=self.scope(db))
        self.store.event(db,'mission.generated',{'mission_id':proposal['id'],'proposal_version':proposal_version,'status':proposal['status']})
        if proposal['conflicts']:
            self.store.event(db,'mission.conflict_detected',{'mission_id':proposal['id'],'conflicts':proposal['conflicts']})
        return proposal

    def enqueue_analysis(self, db, actor, incident_ids=None, requested_agent=None, retry_of=None):
        incidents=self.entities(db,'incident')
        if incident_ids:
            for entity_id in incident_ids:
                self.require(db,'incident',entity_id)
            incidents=[i for i in incidents if i['id'] in incident_ids]
        if not incidents:
            fail(409,'no_eligible_entities','No incident is available for this analysis.')
        versions=self.versions(db,[i['id'] for i in incidents])
        runs=[]
        tasks=[(agent['id'],incident['id']) for incident in incidents for agent in AGENTS if agent['id']!='coordinator' and (requested_agent is None or requested_agent==agent['id'])]
        if requested_agent is None or requested_agent=='coordinator':
            tasks.append(('coordinator',None))
        for agent_id,incident_id in tasks:
            run={'id':uid('run'),'scenario_id':self.scope(db),'agent_id':agent_id,'incident_id':incident_id,'entity_ids':[incident_id] if incident_id else [i['id'] for i in incidents],'status':'queued','input_snapshot':versions,'input_references':versions,'result':None,'confidence':None,'warnings':[],'queued_at':now(),'started_at':None,'completed_at':None,'error_message':None,'synthetic':True,'retry_of':retry_of}
            self.store.put(db,'run',run)
            self.store.event(db,'agent.run_queued',{'run_id':run['id'],'agent_id':agent_id})
            runs.append(run)
        self.store.audit(db,actor,'analysis.queued','run',runs[0]['id'],after={'run_ids':[r['id'] for r in runs],'input_versions':versions},scenario=self.scope(db))
        return runs

    def execute_analysis(self, runs, actor, incident_ids=None, requested_agent=None):
        try:
            with self.store.transaction() as db:
                if runs[0]['scenario_id']!=self.scope(db):
                    raise RuntimeError('inactive_scenario')
                for item in runs:
                    run=self.store.get(db,'run',item['id'])
                    if not run:
                        return  # A confirmed reset intentionally removed this scope.
                    if run['status']!='queued':
                        return  # Idempotent replay must not schedule this job twice.
                    run.update(status='running',started_at=now())
                    self.store.put(db,'run',run)
                    self.store.event(db,'agent.run_started',{'run_id':run['id'],'agent_id':run['agent_id']})
            # Re-read authoritative inputs inside a new transaction. A queued snapshot
            # cannot overwrite intervening state, and the proposal records actual versions.
            with self.store.transaction() as db:
                if runs[0]['scenario_id']!=self.scope(db):
                    raise RuntimeError('inactive_scenario')
                reserved={(r['agent_id'],r['incident_id']):r['id'] for r in runs}
                self.coordinate(db,actor,incident_ids,requested_agent=requested_agent,reserved_runs=reserved)
        except Exception:
            with self.store.transaction() as db:
                for item in runs:
                    run=self.store.get(db,'run',item['id'])
                    if run:
                        run.update(status='failed',completed_at=now(),error_message='Analysis could not complete against current state. Check the selected scenario and retry.')
                        self.store.put(db,'run',run)
                        self.store.event(db,'agent.run_failed',{'run_id':run['id'],'agent_id':run['agent_id'],'error_message':run['error_message']})

    def decision(self, db, entity_id, data, actor, action):
        item=self.require(db,'mission',entity_id)
        if data['expected_version']!=item['proposal_version']:
            fail(409,'version_conflict','Proposal version changed; refresh before deciding.')
        if item['status']!='pending_review':
            fail(409,'invalid_mission_state','Only a current pending review proposal can be decided.')
        if item['input_versions']!=self.versions(db,item['incident_ids']):
            fail(409,'stale_proposal','Material inputs changed. Regenerate this proposal.')
        before=copy.deepcopy(item)
        if action=='approve':
            chosen=data.get('alternative_id')
            if chosen:
                alternative=next((a for a in item['alternatives'] if a['id']==chosen),None)
                if not alternative:
                    fail(404,'alternative_not_found','Alternative was not found on this proposal')
                item['assignments']=alternative['assignments']
                item['chosen_alternative_id']=chosen
            conflicts=self.validate(db,item['assignments'],incident_ids=item['incident_ids'])
            if conflicts or not item['assignments']:
                fail(409,'invalid_plan','Plan violates current hard constraints or has no assignments; regenerate.')
            for resource_id in set(a['resource_id'] for a in item['assignments']):
                resource=self.require(db,'resource',resource_id)
                resource.update(status='assigned',available_capacity=0,version=resource['version']+1,last_updated_at=now())
                self.store.put(db,'resource',resource)
            item.update(status='approved',approver=actor,approved_at=now(),decision_reason='Human approved simulated assignments. No operational dispatch.')
            self.store.put(db,'mission',item)
            self.bump(db)
            for other in self.entities(db,'mission'):
                if other['id']!=item['id'] and other['status']=='pending_review':
                    other.update(status='stale',updated_at=now())
                    other['warnings'].append('Resource reservations changed after another proposal was approved.')
                    self.store.put(db,'mission',other)
        elif action=='reject':
            item.update(status='rejected',decision_reason=data['reason'],approver=actor,decided_at=now())
            self.store.put(db,'mission',item)
        else:
            item.update(status='rejected',decision_reason=data['comment'],approver=actor,decided_at=now())
            self.store.put(db,'mission',item)
        item['updated_at']=now()
        self.store.put(db,'mission',item)
        audit_action={'approve':'mission.approved','reject':'mission.rejected','request_revision':'mission.revision_requested'}[action]
        self.store.audit(db,actor,audit_action,'mission',entity_id,before,item,item['decision_reason'],self.scope(db))
        self.store.event(db,'mission.approved' if action=='approve' else 'mission.rejected' if action=='reject' else 'mission.revision_requested',{'mission_id':entity_id,'proposal_version':item['proposal_version'],'reason':item['decision_reason']})
        if action=='request_revision':
            return self.coordinate(db,actor,item['incident_ids'],parent_id=item['id'])
        return item

    def registry(self, db):
        runs=self.entities(db,'run')
        result=[]
        for agent in AGENTS:
            related=sorted([r for r in runs if r['agent_id']==agent['id']],key=lambda r:r['queued_at'],reverse=True)
            result.append({**agent,'status':'healthy' if not related or related[0]['status']=='completed' else related[0]['status'],'mode':'deterministic_synthetic','run_count':len(related),'last_run_at':related[0]['completed_at'] if related else None,'last_run_id':related[0]['id'] if related else None})
        return result

    def summary(self, db, time_range='24h'):
        incidents=self.entities(db,'incident'); resources=self.entities(db,'resource'); missions=self.entities(db,'mission'); runs=self.entities(db,'run')
        return {'incident_total':len(incidents),'critical_incidents':sum(i.get('priority_band')=='critical' for i in incidents),'high_priority_incidents':sum(i.get('priority_band') in ['critical','high'] for i in incidents),'available_resources':sum(r['status']=='available' for r in resources),'assigned_resources':sum(r['status']=='assigned' for r in resources),'pending_approvals':sum(m['status']=='pending_review' for m in missions),'active_missions':sum(m['status']=='approved' for m in missions),'completed_agent_runs':sum(r['status']=='completed' for r in runs),'total_people_at_risk':sum(i.get('people_at_risk') or 0 for i in incidents),'healthy_agents':sum(agent['status']=='healthy' for agent in self.registry(db)),'scenario_id':self.scope(db),'synthetic':True,'time_range':time_range,'last_updated_at':now()}

    def snapshot(self, db):
        return {'incidents':sorted(self.entities(db,'incident'),key=lambda i:i.get('priority_score',0),reverse=True),'resources':self.entities(db,'resource'),'missions':sorted(self.entities(db,'mission'),key=lambda i:i['proposal_version'],reverse=True),'agents':self.registry(db),'agent_runs':sorted(self.entities(db,'run'),key=lambda i:i['queued_at'],reverse=True),'audit':self.store.audits(db)[:100],'settings':self.store.meta(db,'settings'),'simulation':self.simulation(db),'summary':self.summary(db)}

    def tick(self):
        with self.store.transaction() as db:
            simulation=self.simulation(db)
            if simulation['paused']:
                return
            simulation['event_counter']+=1
            self.store.set_meta(db,'simulation',simulation)
            weather=simulation['weather']
            weather.update(hazard_risk=round(.35+(simulation['event_counter']%6)*.1,2),version=weather['version']+1,updated_at=now())
            self.store.set_meta(db,'simulation',simulation)
            self.material_changed(db,'system:simulator','weather.updated','synthetic-weather',after=weather,reason='Scheduled synthetic weather event')

    def stress(self, db, count, actor, run_id=None):
        from statistics import median
        incidents=self.entities(db,'incident');resources=self.entities(db,'resource');weather=self.simulation(db)['weather'];weights=self.store.meta(db,'settings')['weights']
        timings=[];invalid=0;infeasible=0
        for index in range(count):
            start=time.perf_counter()
            sample=copy.deepcopy(incidents)
            if sample:
                sample[index%len(sample)]['people_at_risk']=50+(index*37)%500
            result=plan(sample,resources,self.assignments(db),weather,weights)
            if result['status']=='infeasible':
                infeasible+=1
            else:
                invalid+=len(detect_constraints(result['assignments'],sample,resources,self.assignments(db),weather))
            timings.append((time.perf_counter()-start)*1000)
        timings.sort()
        previous=self.store.get(db,'stress',run_id) if run_id else None
        item={'id':run_id or uid('stress'),'scenario_id':self.scope(db),'status':'completed','event_count':count,'started_at':previous['started_at'] if previous else now(),'completed_at':now(),'metrics':{'recommendation_ms_p50':round(median(timings),3),'recommendation_ms_p95':round(timings[min(len(timings)-1,math.ceil(len(timings)*.95)-1)],3),'recommendation_ms_max':round(max(timings),3),'invalid_assignment_count':invalid,'infeasible_plan_count':infeasible,'sample_count':count,'incident_count':len(incidents),'resource_count':len(resources),'ranking_accuracy':None,'conflict_precision':None,'conflict_recall':None},'methodology':'CPU-only deterministic planner over independently varied synthetic people counts. Excludes network/browser/external inference. No labeled accuracy claim. Live simulation state is unchanged.','warnings':['Synthetic microbenchmark; does not establish operational performance or model accuracy.']}
        self.store.put(db,'stress',item)
        self.store.audit(db,actor,'stress_test.completed','stress',item['id'],after=item,scenario=self.scope(db))
        self.store.event(db,'simulation.stress_test_completed',{'run_id':item['id'],'status':'completed'})
        return item

    def enqueue_stress(self, db, count, actor):
        item={'id':uid('stress'),'scenario_id':self.scope(db),'status':'queued','event_count':count,'queued_at':now(),'started_at':None,'completed_at':None,'metrics':None,'warnings':[],'error_message':None}
        self.store.put(db,'stress',item)
        self.store.event(db,'simulation.stress_test_queued',{'run_id':item['id']})
        return item

    def execute_stress(self, item, actor):
        try:
            with self.store.transaction() as db:
                run=self.store.get(db,'stress',item['id'])
                if not run:
                    return
                if run['status']!='queued':
                    return
                if run['scenario_id']!=self.scope(db):
                    raise RuntimeError('inactive_scenario')
                run.update(status='running',started_at=now())
                self.store.put(db,'stress',run)
                self.store.event(db,'simulation.stress_test_started',{'run_id':item['id']})
            with self.store.transaction() as db:
                if item['scenario_id']!=self.scope(db):
                    raise RuntimeError('inactive_scenario')
                self.stress(db,item['event_count'],actor,item['id'])
        except Exception:
            with self.store.transaction() as db:
                run=self.store.get(db,'stress',item['id'])
                if run:
                    run.update(status='failed',completed_at=now(),error_message='Stress test could not complete. Select its scenario and retry the test.')
                    self.store.put(db,'stress',run)
                    self.store.event(db,'simulation.stress_test_failed',{'run_id':item['id']})
