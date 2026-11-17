from itertools import permutations
from random import Random

from codecompass.product.reading_order import exact_supply_order, supply_demands, supply_metrics


def exhaustive(ids, parents, features, familiar, topics, demands):
    best = None; count = 0
    stable={u:i for i,u in enumerate(ids)}
    for route in permutations(ids):
        pos={u:i for i,u in enumerate(route)}
        if any(pos[p]>=pos[u] for u in route for p in parents[u]):
            continue
        count += 1
        gaps = sum(bool(row['suppliers']) and all(pos[s]>pos[row['target']] for s in row['suppliers'])
                   for row in demands)
        known=set(familiar); raw=[]; support=[]
        for unit in route:
            fresh=set(features[unit])-known
            raw.append(len(fresh));support.append(len(fresh.intersection(topics)));known.update(fresh)
        key=(0,gaps,max(support,default=0),sum(d*d for d in support),
             max(raw,default=0),sum(d*d for d in raw),tuple(stable[u] for u in route))
        if best is None or key<best[0]:
            best=(key,route)
    return best,count


def test_exact_matches_enumeration_including_peak_ties_and_or_conditions():
    rng=Random(611)
    for n in range(2,8):
        ids=list(range(n))
        for _ in range(2):
            parents={u:{p for p in range(u) if rng.random()<.23} for u in ids}
            features={u:frozenset(t for t in range(6) if rng.random()<.42) for u in ids}
            familiar={0}; topics={1,2,3}
            demands=[dict(target=u,suppliers=[p for p in ids if p!=u and rng.random()<.3],raw_suppliers=[],topic=1)
                     for u in ids]
            best,expected=exhaustive(ids,parents,features,familiar,topics,demands)
            actual,count,states=exact_supply_order(ids,parents,features,familiar,topics,demands)
            assert (tuple(actual),count)==(best[1],expected)
            m=supply_metrics(actual,demands,features,topics,familiar,parents)
            assert sum(m[k] for k in ('root_exposure_topic_count','satisfied_supply_topic_count','avoidable_supply_gap_count'))==n
            assert m['dependency_violations']==0 and states<=(1<<n)*4*7


def test_qualification_and_unavoidable_gap_preserve_verified_precedence():
    ids=['a','b','x','y','rev','other']
    roles=['target','target','foundation','related','related','target']
    sets=[{'a'},{'b'},{'a'},{'b'},{'a'},{'a','b'}]
    features={u:frozenset(fs) for u,fs in zip(ids,sets)}
    views={u:dict(kind=kind,pedagogical_features=features[u]) for u,kind in zip(ids,roles)}
    units={u:dict(concept_ids=features[u]) for u in ids}
    parents={'a':set(),'b':set(),'x':{'b'},'y':{'a'},'rev':{'a'},'other':{'a'}}
    topics,demands=supply_demands(ids,views,units,{'a','b'},set(),{},parents)
    a=next(d for d in demands if d['target']=='a')
    assert a['suppliers']==['x']
    assert next(c for c in a['qualifications'] if c['unit_id']=='rev')['basis']=='reverse_verified_precedence'
    assert next(c for c in a['qualifications'] if c['unit_id']=='x')['basis']=='equal_load_no_collateral'
    seq,_,_=exact_supply_order(ids,parents,features,set(),topics,demands)
    m=supply_metrics(seq,demands,features,topics,set(),parents)
    assert m['dependency_violations']==0 and m['avoidable_supply_gap_count']==1
    assert tuple(seq)==exhaustive(ids,parents,features,set(),topics,demands)[0][1]
