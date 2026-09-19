from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def check(label, params):
    p = {'source': 'nasa_firms', 'limit': 50}
    p.update(params)
    r = c.get('/hotspots/labeling/candidates', params=p)
    j = r.json()
    cands = j.get('candidates', [])
    n_v = sum(1 for h in cands if h.get('verified'))
    n_fac = sum(1 for h in cands if h.get('facility'))
    n_facid = sum(1 for h in cands if h.get('facility_id') is not None)
    total = j.get('total_matched')
    print(f"{label:48} returned={len(cands):4} verified={n_v:4} with_fac_obj={n_fac:4} facility_id_not_null={n_facid:4} total_matched={total}")


check('ALL', {})
check('verified=True', {'verified': 'true'})
check('verified=False', {'verified': 'false'})
check('facility_id=True', {'facility_id': 'true'})
check('facility_id=False', {'facility_id': 'false'})
check('baseline_status=ABNORMAL', {'baseline_status': 'ABNORMAL'})
check('baseline_status=NORMAL', {'baseline_status': 'NORMAL'})
check('baseline_status=ELEVATED', {'baseline_status': 'ELEVATED'})
check('baseline_status=INSUFFICIENT_HISTORY', {'baseline_status': 'INSUFFICIENT_HISTORY'})
check('anomaly=True', {'anomaly': 'true'})
check('anomaly=False', {'anomaly': 'false'})
check('risk_level=HIGH', {'risk_level': 'HIGH'})
check('risk_level=LOW', {'risk_level': 'LOW'})
check('classification=unknown', {'classification': 'unknown'})
check('history_status=SUFFICIENT', {'history_status': 'SUFFICIENT'})
check('history_status=INSUFFICIENT', {'history_status': 'INSUFFICIENT'})
check('COMBO: unver+assoc+abnorm+anom', {'verified': 'false', 'facility_associated': 'true', 'baseline_status': 'ABNORMAL', 'anomaly': 'true'})
check('COMBO: unver+notassoc+normal', {'verified': 'false', 'facility_associated': 'false', 'baseline_status': 'NORMAL'})