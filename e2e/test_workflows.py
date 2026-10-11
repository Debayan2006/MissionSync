"""Exercise visible controls and persisted outcomes in a real Chromium browser."""
import re
import time
import pytest
from playwright.sync_api import expect
from .conftest import BASE

@pytest.mark.parametrize(('route','heading'), [
    ('/dashboard','Command dashboard'),('/incidents','Incident center'),
    ('/map','Incident map'),('/resources','Resource inventory'),
    ('/agents','Agent center'),('/missions','Mission planner'),
    ('/simulator','Simulation lab'),('/audit','Audit log'),('/settings','Settings'),
])
def test_required_routes_load(page, route, heading):
    page.goto(BASE + route)
    expect(page.get_by_role('heading', name=heading, exact=True)).to_be_visible()
    expect(page.get_by_label('Demo role')).to_have_value('administrator')
    expect(page.get_by_text('Synthetic simulation', exact=True)).to_be_visible()


def test_landing_navigation_and_demo(page, api):
    page.goto(BASE)
    expect(page.get_by_role('heading', level=1)).to_contain_text('connect the response')
    page.get_by_role('link', name='Features', exact=True).click()
    expect(page).to_have_url(re.compile(r'#features$'))
    expect(page.locator('#features')).to_be_in_viewport()
    page.get_by_role('link', name='Architecture', exact=True).click()
    expect(page).to_have_url(re.compile(r'#architecture$'))
    expect(page.locator('#architecture')).to_be_in_viewport()
    page.get_by_role('link', name='Launch Dashboard', exact=True).click()
    expect(page.get_by_role('heading', name='Command dashboard')).to_be_visible()
    page.goto(BASE)
    page.get_by_role('button', name='Run Live Demo', exact=True).first.click()
    expect(page).to_have_url(re.compile(r'/simulator$'))
    assert api.get('/state').json()['simulation']['scenario_id'] == 'kolkata-flood'


def test_incident_create_edit_filters_evidence_and_map(page, api):
    page.goto(BASE + '/incidents')
    page.get_by_role('button', name='Create incident', exact=True).click()
    dialog=page.get_by_role('dialog')
    dialog.get_by_label('Incident title').fill('Browser clinic flooding')
    dialog.get_by_label('Description', exact=True).fill('Synthetic evidence: 250 people need assistance near the clinic.')
    dialog.get_by_label('People at risk').fill('250')
    dialog.get_by_label('Damage severity (0–10)').fill('8')
    dialog.get_by_label('Response delay (minutes)').fill('60')
    dialog.get_by_role('button', name='Create incident', exact=True).click()
    expect(dialog).not_to_be_visible()
    page.get_by_label('Search incidents').fill('Browser clinic')
    expect(page.get_by_role('link', name='Browser clinic flooding', exact=True)).to_be_visible()
    page.get_by_label('Category filter').select_option('fire')
    expect(page.get_by_text('No matching incidents')).to_be_visible()
    page.get_by_label('Category filter').select_option('flood')
    page.get_by_role('link', name='Browser clinic flooding', exact=True).click()
    expect(page.get_by_role('heading', name='Risk & priority')).to_be_visible()
    expect(page.get_by_role('heading', name='Evidence & sources')).to_be_visible()
    page.get_by_role('button', name='Edit incident', exact=True).click()
    dialog.get_by_label('Incident title').fill('Browser clinic updated')
    dialog.get_by_role('button', name='Save changes', exact=True).click()
    expect(page.get_by_role('heading', name='Browser clinic updated', exact=True)).to_be_visible()
    incident=next(i for i in api.get('/state').json()['incidents'] if i['title']=='Browser clinic updated')
    assert incident['version'] >= 2 and incident['people_at_risk']==250
    page.get_by_role('link', name='Focus on map', exact=True).click()
    expect(page.locator('.ms-map-popup')).to_contain_text('Browser clinic updated')
    expect(page.get_by_role('button', name=re.compile('Select Browser clinic updated'))).to_have_attribute('aria-pressed','true')
    page.get_by_role('link', name='View incident', exact=True).click()
    page.get_by_role('button', name='Analyze incident', exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('analysis submitted')


def test_map_controls_and_marker_keyboard(page, api):
    incident=api.get('/state').json()['incidents'][0]
    page.goto(BASE + '/map')
    svg=page.locator('svg[aria-label^="Interactive schematic"]')
    original=svg.get_attribute('viewBox')
    page.get_by_role('button', name='Zoom in', exact=True).click()
    assert svg.get_attribute('viewBox') != original
    page.get_by_role('button', name='Zoom out', exact=True).click()
    page.get_by_role('button', name='Fit map to filtered incidents', exact=True).click()
    marker=page.get_by_role('button', name=re.compile('Select '+re.escape(incident['title'])+','))
    marker.focus(); marker.press('Enter')
    expect(page.locator('.ms-map-popup')).to_contain_text(incident['title'])
    page.get_by_role('button', name='Close incident popup').click()
    expect(page.locator('.ms-map-popup')).to_have_count(0)
    page.get_by_label('Filter map by category').select_option('medical')
    assert page.locator('[data-map-marker]').count() == sum(i['category']=='medical' for i in api.get('/state').json()['incidents'])
    page.get_by_role('button', name='Resources', exact=True).click()
    expect(page.get_by_role('button', name='Resources', exact=True)).to_have_attribute('aria-pressed','false')


def test_resource_create_edit_and_role_permissions(page, api):
    page.goto(BASE + '/resources')
    page.get_by_role('button', name='Add resource', exact=True).click()
    dialog=page.get_by_role('dialog')
    dialog.get_by_label('Resource name').fill('Browser rescue team')
    dialog.get_by_label('Capacity', exact=True).fill('12')
    dialog.get_by_role('button', name='Save resource').click()
    expect(dialog).not_to_be_visible()
    page.get_by_label('Search resources').fill('Browser rescue')
    row=page.get_by_role('row').filter(has_text='Browser rescue team')
    expect(row).to_be_visible()
    row.get_by_role('button', name='Edit', exact=True).click()
    dialog.get_by_label('Status').select_option('unavailable')
    dialog.get_by_role('button', name='Save resource').click()
    expect(row).to_contain_text('Unavailable')
    assert next(r for r in api.get('/state').json()['resources'] if r['name']=='Browser rescue team')['status']=='unavailable'
    page.get_by_label('Demo role').select_option('viewer')
    expect(page.get_by_role('button', name='Add resource', exact=True)).to_be_disabled()
    page.goto(BASE + '/incidents')
    expect(page.get_by_role('button', name='Create incident', exact=True)).to_be_disabled()


def test_external_event_becomes_visible_without_reload(page, api, tmp_path):
    page.goto(BASE + '/incidents')
    expect(page.get_by_role('heading', name='Incident center')).to_be_visible()
    page.get_by_label('Search incidents').fill('SSE browser event')
    started=time.perf_counter()
    response=api.post('/simulator/incidents',json={
      'title':'SSE browser event','description':'Synthetic live update validation',
      'category':'medical','coordinates':{'lat':22.57,'lng':88.36},
      'people_at_risk':50,'damage_severity':6,'response_time_minutes':20,'source_reliability':.9,
    })
    assert response.status_code==201,response.text
    expect(page.get_by_role('link',name='SSE browser event',exact=True)).to_be_visible()
    elapsed=(time.perf_counter()-started)*1000
    # This is a measured sample, not a claim about production latency or model accuracy.
    from pathlib import Path
    Path('.local').mkdir(exist_ok=True)
    Path('.local/browser-update-latency-ms.txt').write_text(f'{elapsed:.2f}\n')


def test_mobile_navigation_and_connection_failure(page):
    page.set_viewport_size({'width':390,'height':844})
    page.goto(BASE+'/dashboard')
    page.get_by_role('button',name='Open navigation').click()
    page.get_by_role('navigation',name='Main navigation').get_by_role('link',name='Incidents',exact=True).click()
    expect(page.get_by_role('heading',name='Incident center')).to_be_visible()
    expect(page.get_by_role('button',name='Open navigation')).to_be_visible()
    page.route('**/api/v1/state',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":{"message":"Test service unavailable"}}'))
    page.goto(BASE+'/dashboard')
    expect(page.get_by_role('alert').filter(has_text='Unable to load operational state')).to_be_visible()
    page.unroute('**/api/v1/state')
    page.get_by_role('button',name='Retry connection').click()
    expect(page.get_by_role('heading',name='Command dashboard')).to_be_visible()


def test_mission_generation_alternatives_revision_approval_and_audit(page, api):
    page.goto(BASE+'/missions')
    page.get_by_role('button',name='Generate Plan',exact=True).click()
    expect(page.get_by_role('heading',name='Coordinated response plan')).to_be_visible()
    original_id=page.url.rsplit('/',1)[-1]
    original=api.get('/missions/'+original_id).json()
    expect(page.get_by_role('button',name='Approve proposal')).to_be_enabled()
    alternatives=[a for a in original['alternatives'] if a['status']=='feasible']
    if alternatives:
        page.get_by_label('Compare alternatives').select_option(alternatives[0]['id'])
        expect(page.get_by_role('heading',name=alternatives[0]['label'],exact=True)).to_be_visible()
        page.get_by_label('Compare alternatives').select_option('')
    page.get_by_role('tab',name='Input versions',exact=True).click()
    expect(page.get_by_text('Reproducible input references')).to_be_visible()
    page.get_by_role('tab',name='Rationale',exact=True).click()
    page.get_by_role('button',name='Request revision',exact=True).click()
    dialog=page.get_by_role('dialog')
    dialog.get_by_label('Revision comment').fill('Browser test: review alternate evacuation timing')
    dialog.get_by_role('button',name='Request revision',exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page).not_to_have_url(re.compile(re.escape(original_id)+r'$'))
    revised_id=page.url.rsplit('/',1)[-1]
    revised=api.get('/missions/'+revised_id).json()
    assert revised['proposal_version']>original['proposal_version']
    page.get_by_role('button',name='Approve proposal',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('proposal approved')
    assert api.get('/missions/'+revised_id).json()['status']=='approved'
    page.goto(BASE+'/audit')
    page.get_by_label('Search audit events').fill('mission.approved')
    expect(page.get_by_role('button',name='Mission.Approved',exact=True).first).to_be_visible()
    page.get_by_role('button',name='Mission.Approved',exact=True).first.click()
    expect(page.get_by_role('dialog')).to_contain_text('Human approved')


def test_reject_reason_and_stale_plan_guard(page, api):
    page.goto(BASE+'/missions')
    page.get_by_role('button',name='Generate Plan',exact=True).click()
    expect(page.get_by_role('heading',name='Coordinated response plan')).to_be_visible()
    mission_id=page.url.rsplit('/',1)[-1]
    page.get_by_role('button',name='Reject proposal',exact=True).click()
    dialog=page.get_by_role('dialog')
    dialog.get_by_label('Rejection reason').fill('Browser rejection: await additional synthetic evidence')
    dialog.get_by_role('button',name='Confirm rejection').click()
    expect(dialog).not_to_be_visible()
    mission=api.get('/missions/'+mission_id).json()
    assert mission['status']=='rejected' and 'Browser rejection' in mission['decision_reason']
    page.get_by_role('button',name='Regenerate Plan',exact=True).click()
    expect(page).not_to_have_url(re.compile(re.escape(mission_id)+r'$'))
    mission_id=page.url.rsplit('/',1)[-1]
    state=api.get('/state').json(); resource=state['resources'][0]
    changed=api.patch('/resources/'+resource['id'],json={'expected_version':resource['version'],'status':'unavailable'})
    assert changed.status_code==200,changed.text
    expect(page.get_by_text('This proposal has stale inputs.',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='Approve proposal')).to_be_disabled()
    page.get_by_role('button',name='Regenerate Plan',exact=True).click()
    expect(page).not_to_have_url(re.compile(re.escape(mission_id)+r'$'))


def test_simulator_controls_persist_and_reset_requires_confirmation(page, api):
    page.goto(BASE+'/simulator')
    page.get_by_role('button',name='Resume simulation',exact=True).click()
    expect(page.get_by_role('button',name='Pause simulation',exact=True)).to_be_visible()
    assert api.get('/state').json()['simulation']['paused'] is False
    page.get_by_role('button',name='Pause simulation',exact=True).click()
    expect(page.get_by_role('button',name='Resume simulation',exact=True)).to_be_visible()
    state=api.get('/state').json(); incident=state['incidents'][0]
    page.get_by_label('Severity incident').select_option(incident['id'])
    page.get_by_label('New damage severity',exact=True).fill('9.9')
    page.get_by_role('button',name='Apply severity change').click()
    expect(page.get_by_role('status')).to_contain_text('Severity changed')
    assert api.get('/incidents/'+incident['id']).json()['damage_severity']==9.9
    page.get_by_label('Hazard risk',exact=True).fill('0.9')
    page.get_by_label('Access route blocked').check()
    page.get_by_role('button',name='Change Weather',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('Weather changed')
    assert api.get('/state').json()['missions'][0]['status']=='infeasible'
    page.get_by_label('Access route blocked').uncheck()
    page.get_by_role('button',name='Change Weather',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('Weather changed')
    resource=api.get('/state').json()['resources'][0]
    page.get_by_label('Simulation resource').select_option(resource['id'])
    page.get_by_role('button',name='Disable Resource',exact=True).click()
    expect(page.get_by_role('button',name='Enable Resource',exact=True)).to_be_visible()
    assert api.get('/resources/'+resource['id']).json()['status']=='unavailable'
    page.get_by_role('button',name='Trigger Conflict',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('Controlled conflict created')
    assert api.get('/state').json()['missions'][0]['conflicts']
    page.get_by_label('Stress test event count').fill('10')
    page.get_by_role('button',name='Run Stress Test',exact=True).click()
    expect(page.get_by_text('invalid_assignment_count',exact=False)).to_be_visible()
    page.get_by_role('button',name='Reset Scenario',exact=True).click()
    dialog=page.get_by_role('dialog')
    expect(dialog).to_contain_text('Restore')
    dialog.get_by_role('button',name='Cancel',exact=True).click()
    assert any(i['title']=='Synthetic capacity conflict' for i in api.get('/state').json()['incidents'])
    page.get_by_role('button',name='Reset Scenario',exact=True).click()
    dialog.get_by_role('button',name='Confirm reset',exact=True).click()
    expect(dialog).not_to_be_visible()
    assert len(api.get('/state').json()['incidents'])==3
    page.get_by_label('Scenario',exact=True).select_option('industrial-fire')
    page.get_by_role('button',name='Load Scenario',exact=True).click()
    dialog.get_by_role('button',name='Confirm load',exact=True).click()
    expect(dialog).not_to_be_visible()
    assert api.get('/state').json()['simulation']['scenario_id']=='industrial-fire'


def test_agents_run_inspection_and_settings_save_discard(page, api):
    page.goto(BASE+'/agents')
    page.get_by_role('button',name='Run all agents',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('analysis cycle submitted')
    page.get_by_role('button',name='Inspect run',exact=True).first.click()
    dialog=page.get_by_role('dialog')
    expect(dialog.get_by_role('heading',name='Structured result',exact=True)).to_be_visible()
    dialog.get_by_text('Input snapshot & references',exact=True).click()
    expect(dialog.locator('details')).to_have_attribute('open','')
    dialog.get_by_role('button',name='Close dialog').click()
    page.get_by_label('Agent run status filter').select_option('failed')
    expect(page.get_by_text('No matching agent runs')).to_be_visible()
    page.goto(BASE+'/settings')
    initial=api.get('/settings').json()
    page.get_by_label('People weight',exact=True).fill('0.42')
    page.get_by_role('button',name='Discard changes',exact=True).click()
    expect(page.get_by_label('People weight',exact=True)).to_have_value(str(initial['weights']['people']))
    page.get_by_label('People weight',exact=True).fill('0.42')
    page.get_by_label('Event interval seconds',exact=True).fill('30')
    page.get_by_role('button',name='Save settings',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('Configuration saved')
    changed=api.get('/settings').json()
    assert changed['version']>initial['version'] and changed['weights']['people']==.42


def test_dashboard_controls_and_filtered_metrics(page, api):
    page.goto(BASE+'/dashboard')
    expect(page.get_by_role('heading',name='Command dashboard')).to_be_visible()
    page.get_by_role('button',name='Refresh dashboard').click()
    page.get_by_role('button',name='Run Analysis',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('Analysis jobs submitted')
    page.get_by_role('button',name='Dismiss notification').click()
    expect(page.locator('.toast')).to_have_count(0)
    page.get_by_label('Activity time range').select_option('1')
    expect(page.get_by_label('Activity time range')).to_have_value('1')
    page.get_by_role('button',name='Resume',exact=True).click()
    expect(page.get_by_role('button',name='Pause',exact=True)).to_be_visible()
    page.get_by_role('button',name='Pause',exact=True).click()
    expect(page.get_by_role('button',name='Resume',exact=True)).to_be_visible()
    page.get_by_role('button',name='Reset',exact=True).click()
    dialog=page.get_by_role('dialog')
    dialog.get_by_role('button',name='Cancel',exact=True).click()
    expect(dialog).not_to_be_visible()
    page.get_by_role('button',name='Reset',exact=True).click()
    dialog.get_by_role('button',name='Confirm reset',exact=True).click()
    expect(dialog).not_to_be_visible()
    assert len(api.get('/state').json()['incidents'])==3
    page.get_by_role('link',name=re.compile(r'Critical priority')).click()
    expect(page).to_have_url(re.compile(r'/incidents\?priority=critical$'))
    expect(page.get_by_label('Priority filter')).to_have_value('critical')
    page.goto(BASE+'/dashboard')
    page.get_by_role('link',name=re.compile(r'Resources available')).click()
    expect(page.get_by_label('Resource status filter')).to_have_value('available')


def test_landing_links_mobile_menu_and_form_cancel(page):
    for name,route in [('Incidents','/incidents'),('Mission planner','/missions'),('Explore the map','/map'),('Explore agents','/agents'),('Explore mission planning','/missions'),('Launch workspace','/dashboard')]:
        page.goto(BASE)
        page.get_by_role('link',name=name,exact=True).click()
        expect(page).to_have_url(re.compile(re.escape(route)+r'$'))
    page.set_viewport_size({'width':390,'height':844})
    page.goto(BASE)
    page.get_by_role('button',name='Toggle mobile menu').click()
    expect(page.get_by_role('link',name='Features',exact=True)).to_be_visible()
    page.get_by_role('link',name='Features',exact=True).click()
    expect(page).to_have_url(re.compile(r'#features$'))
    page.goto(BASE+'/incidents')
    page.get_by_role('button',name='Create incident',exact=True).click()
    dialog=page.get_by_role('dialog')
    dialog.get_by_label('Incident title').fill('Unsaved browser incident')
    dialog.get_by_role('button',name='Cancel',exact=True).click()
    expect(dialog).not_to_be_visible()
    page.get_by_label('Search incidents').fill('Unsaved browser')
    expect(page.get_by_text('No matching incidents')).to_be_visible()
