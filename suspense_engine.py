"""Bounded candidate generation, deterministic weighted set packing and conservation checks."""
from collections import defaultdict, Counter
from dataclasses import dataclass, replace
from itertools import combinations
import hashlib
from suspense_data import compact, party, VERSION


@dataclass(frozen=True)
class Candidate:
    id: str
    credits: tuple
    debits: tuple
    kind: str
    score: int
    reasons: tuple
    state: str
    allocations: tuple = ()

    @property
    def ids(self):return frozenset(self.credits+self.debits)


def scope_applies(rule, a, b):
    return (rule.get('kind','counterparty')=='counterparty' and rule.get('approved') is True and bool(rule.get('reason')) and bool(rule.get('approver'))
            and (not rule.get('department') or a.department==b.department==rule['department'])
            and (not rule.get('start') or min(a.day,b.day).isoformat()>=rule['start'])
            and (not rule.get('end') or max(a.day,b.day).isoformat()<=rule['end'])
            and (not rule.get('purpose') or all(compact(rule['purpose']) in compact(t.description) for t in (a,b))))


def same_or_next_month(credit,debit):
    return credit.day<=debit.day and (debit.day.year-credit.day.year)*12+debit.day.month-credit.day.month in (0,1)


def explicit_purpose_conflict(a,b):
    # Narrow, evidenced distinction; unknown purpose is not a contradiction.
    def categories(t):
        description=compact(t.description)
        rental=('기부부동산임대' in compact(t.account) or '부동산임대료' in description)
        facility=any(word in description for word in ('시설이용료','시설사용료'))
        return {'부동산임대' for _ in [0] if rental}|{'시설이용' for _ in [0] if facility}
    left,right=categories(a),categories(b)
    return bool(left and right and left.isdisjoint(right))


def relation(a,b,aliases=()):
    score=0;reasons=[]
    if explicit_purpose_conflict(a,b):return -1000,('명시 거래 목적 상충: 부동산임대 / 시설이용',)
    if a.unit and b.unit and a.unit!=b.unit:return -1000,('회계단위 다름',)
    # Different church language accounts must not be merged.
    church=any('헌금' in t.description for t in (a,b))
    if church and a.account and b.account and compact(a.account)!=compact(b.account):return -1000,('헌금 계좌 다름',)
    if church and (('한국어' in a.description and '영어' in b.description) or ('영어' in a.description and '한국어' in b.description)):return -1000,('헌금 언어 다름',)
    if a.day>b.day:return -1000,('대변이 차변보다 늦음',)
    if a.name and a.name==b.name:score+=45;reasons.append('R01/R02 거래선 일치')
    elif any({party(rule.get('source','')),party(rule.get('target',''))}=={a.name,b.name} and scope_applies(rule,a,b) for rule in aliases):
        score+=40;reasons.append('R06 승인된 범위별 별칭')
    elif a.name and b.name and min(len(a.name),len(b.name))>=2 and (a.name.startswith(b.name) or b.name.startswith(a.name)):
        score+=20;reasons.append('R03 약칭 후보·전표 확인')
    if (len(a.name)>=2 and a.name in compact(b.description)) or (len(b.name)>=2 and b.name in compact(a.description)):
        score+=35;reasons.append('R04 거래선·적요 교차')
    if a.narrative and a.narrative==b.narrative and len(a.narrative)>=3:
        score+=35;reasons.append('R05 거래 목적 일치')
    else:
        words_a=set(a.description.split());words_b=set(b.description.split())
        shared={compact(v) for v in words_a&words_b if len(compact(v))>=3 and not any(x in v for x in ('정산','가수금','입금','반환'))}
        if shared:score+=15;reasons.append('사업·대상 단서: '+','.join(sorted(shared)))
    if a.department and a.department==b.department:score+=8;reasons.append('부서 일치')
    if a.account and a.account==b.account:score+=8;reasons.append('계좌 일치')
    if a.months and b.months:
        if set(a.months)&set(b.months):score+=30;reasons.append('M14 대상 월 일치')
        else:score-=20;reasons.append('M13 대상 월 다름·귀속 확인')
    if b.period:
        if b.period[0]<=a.day<=b.period[1]:score+=35;reasons.append('M10 명시 정산기간 포함')
        else:return -1000,('명시 정산기간 밖',)
    score+=max(0,6-(b.day-a.day).days//15)
    return score,tuple(reasons)


class Cancelled(Exception):pass


def generate(rows, aliases=(), progress=lambda *_:None, cancel=lambda:False, budget=2000000):
    ordered=sorted(rows,key=lambda t:(t.day,t.voucher,t.row,t.row_id));byid={t.row_id:t for t in rows}
    credits=[t for t in ordered if t.side=='C'];debits=[t for t in ordered if t.side=='D']
    candidates={};incomplete=set();steps=0;stopped=False
    def tick(ids):
        nonlocal steps,stopped
        if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
        steps+=1
        if steps>budget:
            incomplete.update(ids);stopped=True;return False
        return True
    def add(cs,ds,kind,force_review=False):
        cs=sorted(cs,key=lambda t:t.row_id);ds=sorted(ds,key=lambda t:t.row_id)
        department_pair=kind=='1:1 부서·금액'
        department_cohort=kind in ('N:1 부서·계좌·기간','N:N 부서·계좌·기간')
        ids=[t.row_id for t in cs+ds]
        if not tick(ids) or not cs or not ds:return
        if sum(t.value for t in cs)!=sum(t.value for t in ds):return
        # Rule 4: automated split/aggregate/period settlement stays within one department.
        if len(cs)>1 or len(ds)>1 or any(t.period for t in ds):
            departments={t.department for t in cs+ds}
            if len(departments)!=1 or not next(iter(departments)):return
        church_period=any(t.period and '헌금' in t.description for t in ds)
        if church_period:
            if not kind.startswith('기간'):return
            if len({t.account for t in cs})!=1 or not cs[0].account:return
            force_review=force_review or any('한국어' in t.counterparty and '영어' in t.description or '영어' in t.counterparty and '한국어' in t.description for t in ds)
        if len(cs)>1 and len(ds)>1 and Counter(t.value for t in cs)==Counter(t.value for t in ds):
            return  # Independent equal-amount pairs add no N:N explanatory evidence.
        # Every member must have a chronological, contextually related counterpart.
        explicit_months={m for t in cs+ds for m in t.months}
        # Do not collapse independent monthly settlements into a larger equal-total group.
        if len(cs)>1 and len(ds)>1 and len(explicit_months)>1 and not any(t.period or len(t.months)>1 for t in ds):
            return
        pairs=[relation(c,d,aliases) for c in cs for d in ds]
        for t,others in [(c,ds) for c in cs]+[(d,cs) for d in ds]:
            minimum=-999 if department_pair else 8
            if max((relation(t,o,aliases)[0] if t.side=='C' else relation(o,t,aliases)[0]) for o in others)<minimum:return
        qualities=[max(relation(c,d,aliases)[0] for d in ds) for c in cs]+[max(relation(c,d,aliases)[0] for c in cs) for d in ds]
        reasons=sorted({reason for score,why in pairs if score>=8 for reason in why})
        score=min(qualities)
        if department_cohort:
            if len({t.account for t in cs})!=1 or not cs[0].account:return
            balance=0
            for t in sorted(cs+ds,key=lambda t:(t.day,t.side!='C',t.row_id)):
                balance+=t.credit-t.debit
                if balance<0:return
            score=55 if kind.startswith('N:1') else 45
            force_review=True
            reasons.append('동일 부서·입금계좌·일자 범위 합계 / 개별 거래선 상이 허용')
            reasons.append(f'입금 {len(cs)}건, {min(t.day for t in cs)}~{max(t.day for t in cs)} / 수납명세·사업 귀속 확인 필요')
        if department_pair:
            if len(cs)==len(ds)==1 and not same_or_next_month(cs[0],ds[0]):return
            if len(cs)!=1 or len(ds)!=1 or not cs[0].department or cs[0].department!=ds[0].department:return
            score=35+max(0,6-(ds[0].day-cs[0].day).days//15)
            reasons.append('M04 사용자 기준: 부서명·금액 일치 / 거래선 상이 허용')
            if ds[0].months and not cs[0].months and cs[0].day.month in ds[0].months:
                score+=15;reasons.append('대상 월과 입금 월 일치 (보조 근거)')
            force_review=True
        voucher_bundle=len(ds)>1 and bool(ds[0].voucher) and len({t.voucher for t in ds})==1
        if church_period:reasons.append('M10 기간·입금계좌별 전체 수납 합계')
        if voucher_bundle:score+=24;reasons.append('M06/M14 동일 전표 차변 묶음')
        monthly=any('대상 월 일치' in reason for reason in reasons)
        if monthly and (len(cs)>1 or len(ds)>1):score+=15;reasons.append('M14 월별 합산·분할 후보')
        if any(t.refund for t in cs+ds):force_review=True;reasons.append('M09/M11 반환금 거래 귀속 확인 필요')
        if any('약칭' in r or '대상 월 다름' in r for r in reasons):force_review=True
        if len(cs)>1 and len(ds)>1:
            reasons.append('M08/M15 합산 상계·개별 차액은 상세 거래 확인')
            unmatched_amounts=sorted(set(c.value for c in cs)^set(d.value for d in ds))
            if unmatched_amounts:
                reasons.append('개별 금액: '+','.join(map(str,unmatched_amounts[:12])))
                differences=[abs(c.value-d.value) for c in cs for d in ds if c.value!=d.value]
                if differences:reasons.append(f'M15 개별 금액 차이 최소 {min(differences):,}원 · 개별 연결 확정 아님')
        if len({t.department for t in cs+ds})>1:force_review=True;reasons.append('M12 관련 부서 간 거래·사용 목적 확인')
        state='자동매칭' if score>=65 and not force_review else '조건부매칭' if score>=35 else '검토후보'
        key='G'+hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest()[:16]
        candidate=Candidate(key,tuple(t.row_id for t in cs),tuple(t.row_id for t in ds),kind,score,tuple(reasons),state)
        if key not in candidates or (score,kind)>(candidates[key].score,candidates[key].kind):candidates[key]=candidate
    indexes=defaultdict(list)
    for c in credits:
        for key in [('name',c.name),('dept',c.department),('account',c.account),('purpose',c.narrative),('amount-dept',(c.value,c.department))]:
            if key[1]:indexes[key].append(c)
    neighbours=defaultdict(list)
    for i,d in enumerate(debits):
        if i%100==0:progress('C 후보 생성',i,len(debits))
        pool={c.row_id:c for key in [('name',d.name),('purpose',d.narrative),('amount-dept',(d.value,d.department))] if key[1] for c in indexes[key]}
        for key in [('dept',d.department),('account',d.account)]:
            if key[1] and (not pool or len(indexes[key])<=48):
                pool.update((c.row_id,c) for c in indexes[key])
        for rule in aliases:
            target=party(rule.get('target',''));source=party(rule.get('source',''))
            if d.name in (source,target):
                for c in indexes[('name',source if d.name==target else target)]:pool[c.row_id]=c
        for c in sorted(pool.values(),key=lambda t:t.row_id):
            if not tick((c.row_id,d.row_id)):break
            score,_=relation(c,d,aliases)
            if score<=-1000:continue
            if score<35:
                if c.value==d.value and c.department and c.department==d.department:
                    add([c],[d],'1:1 부서·금액')
                continue
            neighbours[d.row_id].append(c);neighbours[c.row_id].append(d)
            if c.value==d.value:add([c],[d],'1:1')
        if stopped:break
    if stopped:incomplete.update(t.row_id for t in rows)
    def subsets(pool,target,owner):
        # Whole contextual buckets handle hundreds of rows without a powerset search.
        buckets=defaultdict(list)
        for t in pool:
            for key in [('all',),('voucher',t.voucher),('party',t.name),('purpose',t.narrative),('month',t.months),('account',t.account)]:
                if len(key)==1 or key[1]:buckets[key].append(t)
        emitted=set()
        for group in buckets.values():
            if sum(t.value for t in group)==target:
                ids=tuple(t.row_id for t in group)
                if ids not in emitted:emitted.add(ids);yield group
        if sum(t.value for t in pool)==target:return
        if len(pool)>24:
            incomplete.update([owner]+[t.row_id for t in pool]);return
        states={0:[()]};count=0
        for t in pool:
            additions=defaultdict(list)
            for total,combos in list(states.items()):
                if total+t.value>target:continue
                for combo in combos:
                    if not tick([owner,t.row_id]):return
                    new=combo+(t.row_id,);count+=1
                    if total+t.value==target and new not in emitted:
                        emitted.add(new);yield [byid[x] for x in new]
                    elif total+t.value<target:additions[total+t.value].append(new)
                    if count>=8000:
                        incomplete.update([owner]+[x.row_id for x in pool]);return
            for total,combos in additions.items():states.setdefault(total,[]).extend(combos)
    if not stopped:
        for i,t in enumerate(ordered):
            if i%100==0:progress('C 합산·월별 후보',i,len(ordered))
            pool=neighbours[t.row_id]
            if not pool:continue
            if t.side=='D' and t.period and '헌금' in t.description:continue
            # Prefer meaningful relations; department-only candidates remain review candidates.
            strong=[o for o in pool if (relation(t,o,aliases) if t.side=='C' else relation(o,t,aliases))[0]>=35]
            pool=[o for o in strong if o.value<t.value and t.department and o.department==t.department]
            pool=sorted(pool,key=lambda x:x.row_id)
            if not pool:continue
            for group in subsets(pool,t.value,t.row_id):
                if len(group)>1:add([t],group,'1:N') if t.side=='C' else add(group,[t],'N:1')
            if stopped:break
    # N:N: contextual aggregate and bounded subsets within each account/purpose/month bucket.
    buckets=defaultdict(list)
    explained={i for c in candidates.values() if c.score>=65 for i in c.ids}
    for t in ordered:
        if not t.side:continue
        for key in [('party',t.unit,t.department,t.name),('purpose',t.unit,t.department,t.narrative),('dept-account',t.unit,t.department,t.account),('month',t.unit,t.department,t.months)]:
            if key[-1] and (key[0] not in ('dept-account','month') or t.row_id not in explained):buckets[key].append(t)
    for key,group in sorted(buckets.items(),key=lambda item:str(item[0])):
        if stopped:break
        cs=[t for t in group if t.side=='C'];ds=[t for t in group if t.side=='D']
        if not cs or not ds:continue
        # Uniform positive amounts cannot form a non-decomposable N:N settlement.
        # All relevant 1:1 edges were generated and are solved jointly by assignment.
        # This is a completed reduction, not a skipped combinatorial search.
        if len({t.value for t in group})==1:continue
        if len(cs)*len(ds)>10000:incomplete.update(t.row_id for t in group);continue
        if len(cs)>1 and len(ds)>1:add(cs,ds,'N:N',force_review=key[0]=='dept-account')
        if len(group)<=12:
            sums=defaultdict(list)
            for size in range(2,min(len(cs),5)+1):
                for combo in combinations(cs,size):sums[sum(t.value for t in combo)].append(combo)
            for size in range(2,min(len(ds),5)+1):
                for combo in combinations(ds,size):
                    for matches in sums.get(sum(t.value for t in combo),[]):add(matches,combo,'N:N')
        elif len(cs)>1 and len(ds)>1:incomplete.update(t.row_id for t in group)
    # Explicit church aggregation windows, optionally including a refund debit.
    for d in debits:
        if stopped:break
        if not d.period or '헌금' not in d.description:continue
        cs=[c for c in neighbours[d.row_id] if d.department and c.department==d.department and d.period[0]<=c.day<=d.period[1] and (not d.account or c.account==d.account)]
        accounts=defaultdict(list)
        for c in cs:
            if c.account:accounts[c.account].append(c)
            else:incomplete.update((c.row_id,d.row_id))
        for account,receipts in sorted(accounts.items()):
            language='한국어' if '한국어' in account else '영어' if '영어' in account else ''
            labels={word for word in ('한국어','영어') if word in d.description or word in d.counterparty}
            if language and labels and language not in labels:continue
            add(receipts,[d],'기간 N:1',len(labels)>1)
            for refund in debits:
                if refund is d or not refund.refund or refund.department!=d.department or (refund.account and refund.account!=account):continue
                if d.period[0]<=refund.day<=d.day:add(receipts,[d,refund],'기간 N:N 반환',True)
    if not stopped:
        # Generate large N:1 cohorts without requiring each payer's name to resemble
        # the consolidated settlement counterparty. No arbitrary powerset is searched.
        progress('C 동일 부서·계좌 수납 합산',0,len(debits))
        provisional,_,_=optimize(list(candidates.values()),cancel)
        reserved={i for c in provisional for i in c.ids}
        receipt_buckets=defaultdict(list)
        for c in credits:
            if c.department and c.account:receipt_buckets[(c.unit,c.department,c.account)].append(c)
        for (unit,department,account),receipts in sorted(receipt_buckets.items()):
            settlements=[d for d in debits if d.row_id not in reserved and d.department==department and (not d.unit or not unit or d.unit==unit) and (not d.account or d.account==account) and not (d.period and '헌금' in d.description)]
            for d in settlements:
                eligible=[c for c in receipts if c.row_id not in reserved and c.value<d.value and c.day<=d.day and (not d.period or d.period[0]<=c.day<=d.period[1])]
                for pool in (eligible,):
                    pool=sorted(pool,key=lambda c:(c.day,c.voucher,c.row,c.row_id))
                    left=0;total=0
                    for right,c in enumerate(pool):
                        if not tick((c.row_id,d.row_id)):break
                        total+=c.value
                        while total>d.value and left<=right:total-=pool[left].value;left+=1
                        if total==d.value and right-left+1>1:add(pool[left:right+1],[d],'N:1 부서·계좌·기간',True)
                    if stopped:break
                if stopped:break
            if stopped:break
        # Re-solve provisionally, then offer a complete residual cohort for N:N.
        # Provisional links are never committed: the caller optimizes all candidates again.
        if not stopped:
            provisional,_,_=optimize(list(candidates.values()),cancel)
            reserved={i for c in provisional for i in c.ids}
            for (unit,department,account),receipts in sorted(receipt_buckets.items()):
                cs=[c for c in receipts if c.row_id not in reserved]
                ds=[d for d in debits if d.row_id not in reserved and d.department==department and (not d.unit or not unit or d.unit==unit) and (not d.account or d.account==account) and not (d.period and '헌금' in d.description)]
                if len(cs)>1 and len(ds)>1:
                    if len(cs)*len(ds)>10000:incomplete.update(t.row_id for t in cs+ds)
                    else:add(cs,ds,'N:N 부서·계좌·기간',True)
    if stopped:incomplete.update(t.row_id for t in rows)
    return sorted(candidates.values(),key=lambda c:c.id),incomplete


def pair_assignment(component,cancel,node_limit=2000000):
    """Exact maximum-weight bipartite assignment using residual augmenting paths."""
    from collections import deque
    credits=sorted({c.credits[0] for c in component});debits=sorted({c.debits[0] for c in component})
    vertices=['source']+credits+debits+['sink'];index={v:i for i,v in enumerate(vertices)}
    source=0;sink=len(vertices)-1;graph=[[] for _ in vertices];refs={}
    def edge(a,b,cost):
        forward=[b,1,cost,len(graph[b])];back=[a,0,-cost,len(graph[a])]
        graph[a].append(forward);graph[b].append(back);return forward
    for c in credits:edge(source,index[c],0)
    for d in debits:edge(index[d],sink,0)
    for c in sorted(component,key=lambda c:c.id):refs[c.id]=edge(index[c.credits[0]],index[c.debits[0]],-(c.score+20)*2)
    operations=0;limited=False
    while True:
        dist=[float('inf')]*len(vertices);dist[source]=0;previous={};queue=deque([source]);waiting={source}
        while queue:
            if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
            a=queue.popleft();waiting.remove(a)
            for k,e in enumerate(graph[a]):
                operations+=1
                if operations>node_limit:limited=True;break
                b,cap,cost,_=e
                if cap and dist[a]+cost<dist[b]:
                    dist[b]=dist[a]+cost;previous[b]=(a,k)
                    if b not in waiting:queue.append(b);waiting.add(b)
            if limited:break
        if limited or dist[sink]>=0 or sink not in previous:break
        b=sink
        while b!=source:
            a,k=previous[b];e=graph[a][k];e[1]=0;graph[b][e[3]][1]=1;b=a
    return [c for c in component if refs[c.id][1]==0],limited


def row_assignment(component,cancel,node_limit):
    """Exact set packing by remaining row mask, bounded by distinct states."""
    from functools import lru_cache
    identities=sorted({i for c in component for i in c.ids})
    index={identity:n for n,identity in enumerate(identities)}
    choices=defaultdict(list)
    for c in component:
        mask=sum(1<<index[i] for i in c.ids)
        for i in c.ids:choices[index[i]].append((mask,c))
    nodes=0
    class Limit(Exception):pass
    @lru_cache(None)
    def solve(mask):
        nonlocal nodes
        if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
        nodes+=1
        if nodes>node_limit:raise Limit()
        if not mask:return 0,()
        bit=mask&-mask;row=bit.bit_length()-1
        best=solve(mask^bit)
        for members,c in choices[row]:
            if members&mask!=members:continue
            value,ids=solve(mask^members)
            option=(value+(c.score+20)*len(c.ids),tuple(sorted(ids+(c.id,))))
            if option[0]>best[0] or (option[0]==best[0] and option[1]<best[1]):best=option
        return best
    try:_,ids=solve((1<<len(identities))-1)
    except Limit:return [],True
    return [c for c in component if c.id in ids],False


def optimize(candidates, cancel=lambda:False, node_limit=50000, _fallback_stage=True, residual_search=False):
    """Solve independent conflict components. Never present a bounded search as exhaustive."""
    fallback=[c for c in candidates if c.kind=='1:1 부서·금액']
    if _fallback_stage and fallback:
        # Department/amount-only evidence is the specified final fallback, not a reason
        # to merge otherwise independent strong-evidence conflict components.
        strong=[c for c in candidates if c.kind!='1:1 부서·금액']
        chosen,limited,conflicts=optimize(strong,cancel,node_limit,False,residual_search)
        used=set().union(*(c.ids for c in chosen)) if chosen else set()
        remaining=[c for c in fallback if not c.ids&(used|limited)]
        extra,more_limited,more_conflicts=optimize(remaining,cancel,node_limit,False,residual_search)
        return chosen+extra,limited|more_limited,conflicts|more_conflicts
    eligible=[c for c in candidates if c.state!='검토후보'];byrow=defaultdict(list)
    for i,c in enumerate(eligible):
        for row in c.ids:byrow[row].append(i)
    visited=set();selected=[];incomplete=set();conflicts=set()
    for start in range(len(eligible)):
        if start in visited:continue
        stack=[start];component=[];visited.add(start)
        while stack:
            i=stack.pop();component.append(eligible[i])
            for row in eligible[i].ids:
                for other in byrow[row]:
                    if other!=i:conflicts.add(eligible[i].id)
                    if other not in visited:visited.add(other);stack.append(other)
        if all(len(c.credits)==len(c.debits)==1 for c in component):
            pairs,limited=pair_assignment(component,cancel)
            selected.extend(pairs)
            if limited:incomplete.update(row for c in component for row in c.ids)
            continue
        if residual_search and len({i for c in component for i in c.ids})<=22:
            picked,limited=row_assignment(component,cancel,node_limit)
            selected.extend(picked)
            if limited:incomplete.update(i for c in component for i in c.ids)
            continue
        component.sort(key=lambda c:(-c.score*len(c.ids),c.id))
        if len(component)>150:
            incomplete.update(row for c in component for row in c.ids);continue
        weights=[(c.score+20)*len(c.ids) for c in component];suffix=[0]*(len(weights)+1)
        for i in range(len(weights)-1,-1,-1):suffix[i]=suffix[i+1]+weights[i]
        best=(-1,());nodes=0;limited=False
        def search(index,used,value,chosen):
            nonlocal best,nodes,limited
            if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
            nodes+=1
            if nodes>node_limit:limited=True;return
            if value+suffix[index]<best[0]:return
            if index==len(component):
                ids=tuple(sorted(component[i].id for i in chosen))
                if value>best[0] or (value==best[0] and ids<best[1]):best=(value,ids)
                return
            candidate=component[index]
            if not used&candidate.ids:search(index+1,used|candidate.ids,value+weights[index],chosen+(index,))
            search(index+1,used,value,chosen)
        search(0,frozenset(),0,())
        if limited:incomplete.update(row for c in component for row in c.ids)
        selected.extend(c for c in component if c.id in best[1])
    return selected,incomplete,conflicts


def validate(rows,groups):
    byid={t.row_id:t for t in rows};used=set();allocations=defaultdict(int);checks=[]
    duplicate=len(byid)!=len(rows);balanced=True;capacity=True
    for group in groups:
        if used&group.ids:duplicate=True
        used.update(group.ids)
        amounts=dict(group.allocations) if group.allocations else {i:byid[i].value for i in group.ids}
        if set(amounts)!=set(group.ids):capacity=False
        for row,value in amounts.items():
            if row not in byid or value<0 or value>byid[row].value:capacity=False
            allocations[row]+=value
        if sum(amounts.get(i,0) for i in group.credits)!=sum(amounts.get(i,0) for i in group.debits):balanced=False
    for row,value in allocations.items():
        if row not in byid or value>byid[row].value:capacity=False
    residual={t.row_id:(t.debit-(allocations[t.row_id] if t.side=='D' else 0),t.credit-(allocations[t.row_id] if t.side=='C' else 0)) for t in rows}
    debit=sum(t.debit for t in rows);credit=sum(t.credit for t in rows)
    checks=[('건수 검산',len(rows)==len(used)+len([t for t in rows if t.row_id not in used])),
            ('중복·계좌·기간 배정 검산',not duplicate),('그룹 대차 검산',balanced),('배분 초과 검산',capacity),
            ('차변 보존',debit==sum(v[0] for v in residual.values())+sum(allocations[t.row_id] for t in rows if t.side=='D')),
            ('대변 보존',credit==sum(v[1] for v in residual.values())+sum(allocations[t.row_id] for t in rows if t.side=='C')),
            ('순잔액 보존',debit-credit==sum(d-c for d,c in residual.values()))]
    return {'checks':checks,'ok':all(ok for _,ok in checks),'residual':residual,'allocations':dict(allocations),'debit':debit,'credit':credit,'net':debit-credit}


def residual_period_candidates(rows, exact=False, cancel=lambda:False):
    """Same/next calendar month candidates; never infer purpose from amount alone."""
    buckets=defaultdict(list);out={};limited=set()
    for t in rows:
        if t.side and t.department and t.unit:
            key=(t.department,t.unit,t.name,t.narrative) if exact else (t.department,t.unit)
            if not exact or (t.name and len(t.narrative)>=3):buckets[key].append(t)
    def compatible(c,d):
        delta=(d.day.year-c.day.year)*12+d.day.month-c.day.month
        return c.day<=d.day and delta in (0,1) and relation(c,d)[0]>-1000 and not (c.account and d.account and compact(c.account)!=compact(d.account) and not d.refund)
    def add(cs,ds):
        if not cs or not ds or sum(t.value for t in cs)!=sum(t.value for t in ds):return
        if len({compact(t.account) for t in cs if t.account})>1:return
        if any(not compatible(c,d) for c in cs for d in ds):return
        ids=sorted(t.row_id for t in cs+ds)
        identifier='G'+hashlib.sha256('|'.join(ids).encode()).hexdigest()[:16]
        kind=('적요 일치 ' if exact else '동월·익월 ')+('1:1' if len(cs)==len(ds)==1 else 'N:N' if len(cs)>1 and len(ds)>1 else 'N:1' if len(cs)>1 else '1:N')
        out[identifier]=Candidate(identifier,tuple(t.row_id for t in cs),tuple(t.row_id for t in ds),kind,150 if exact else 40,('금액·부서·회계 일치', '거래선·적요 일치 묶음' if exact else '거래 목적 미확정·동월/익월 합계 후보 확인'),'조건부매칭')
    for bucket in buckets.values():
        if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
        cs=[t for t in bucket if t.side=='C'];ds=[t for t in bucket if t.side=='D']
        if exact:
            # Only mutual unique exact pairs or a complete balanced purpose cohort.
            for c in cs:
                peers=[d for d in ds if d.value==c.value and compatible(c,d)]
                if len(peers)==1 and sum(x.value==peers[0].value and compatible(x,peers[0]) for x in cs)==1:add([c],peers)
            add(cs,ds)
            for year,month in sorted({(c.day.year,c.day.month) for c in cs}):
                credit=[c for c in cs if (c.day.year,c.day.month)==(year,month)]
                for offset in (0,1):
                    target=year*12+month-1+offset
                    debit=[d for d in ds if d.day.year*12+d.day.month-1==target]
                    add(credit,debit)
            continue
        for owner,pool in [(d,[c for c in cs if compatible(c,d)]) for d in ds]+[(c,[d for d in ds if compatible(c,d)]) for c in cs]:
            pool=[t for t in pool if t.value<=owner.value]
            if len(pool)>18:limited.update(t.row_id for t in pool+[owner]);continue
            # Bound cardinality, retaining explicit incompleteness for larger combinations.
            if len(pool)>4:limited.update(t.row_id for t in pool+[owner])
            for n in range(1,min(4,len(pool))+1):
                for subset in combinations(pool,n):
                    if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
                    if owner.side=='D':add(list(subset),[owner])
                    else:add([owner],list(subset))
        for month in sorted({(c.day.year,c.day.month) for c in cs}):
            credit=[c for c in cs if (c.day.year,c.day.month)==month]
            debit=[d for d in ds if credit and all(compatible(c,d) for c in credit)]
            add(credit,debit)
    return list(out.values()),limited


def residual_explicit_period(rows,cancel=lambda:False):
    """Compare full account receipts with an explicit settlement and in-period refunds."""
    out=[];limited=set()
    for d in rows:
        if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
        if d.side!='D' or not d.period or not d.department or not d.unit:continue
        accounts=defaultdict(list)
        for c in rows:
            if c.side=='C' and c.department==d.department and c.unit==d.unit and c.account and d.period[0]<=c.day<=d.period[1] and relation(c,d)[0]>-1000:
                if d.account and compact(d.account)!=compact(c.account):continue
                labels={w for w in ('한국어','영어') if w in d.description or w in d.counterparty}
                language={w for w in ('한국어','영어') if w in c.account}
                if labels and (len(labels)!=1 or language!=labels):continue
                accounts[c.account].append(c)
        for account,cs in accounts.items():
            refunds=[t for t in rows if t.side=='D' and t.row_id!=d.row_id and t.refund and t.department==d.department and t.unit==d.unit and d.period[0]<=t.day<=min(d.period[1],d.day) and (not t.account or compact(t.account)==compact(account) or t.refund)]
            if len(refunds)>8:limited.update(t.row_id for t in cs+refunds+[d]);continue
            for n in range(len(refunds)+1):
                for extra in combinations(refunds,n):
                    ds=[d,*extra]
                    if sum(c.value for c in cs)!=sum(t.value for t in ds):continue
                    balance=0
                    for t in sorted(cs+ds,key=lambda t:(t.day,0 if t.side=='C' else 1,t.row_id)):
                        balance+=t.value if t.side=='C' else -t.value
                        if balance<0:break
                    if balance<0:continue
                    ids=sorted(t.row_id for t in cs+ds)
                    ident='E'+hashlib.sha256('|'.join(ids).encode()).hexdigest()[:16]
                    out.append(Candidate(ident,tuple(c.row_id for c in cs),tuple(t.row_id for t in ds),'잔여 명시기간 N:N' if len(ds)>1 else '잔여 명시기간 N:1',110,('동일 부서·회계·입금계좌의 명시기간 전체 입금 합계','기간 내 반환 포함·반환 귀속 확인 필요' if extra else '명시기간 정산 합계','일자별 누적 수납잔액 검산'),'조건부매칭'))
    return out,limited


def run(ledger,settings=None,progress=lambda *_:None,cancel=lambda:False):
    from suspense_store import ensure_builtin_rules
    from copy import deepcopy
    settings=ensure_builtin_rules(deepcopy(settings or {}))
    department_map={rule['source']:rule['target'] for rule in settings.get('aliases',[]) if rule.get('kind')=='department' and rule.get('approved')}
    rows=[replace(t,department=department_map[t.department]) if t.department in department_map else t for t in ledger['rows']]
    byid={t.row_id:t for t in rows}
    progress('A/B 정규화·의미 분석',len(rows),len(rows))
    candidates,incomplete=generate(rows,settings.get('aliases',[]),progress,cancel)
    generation_incomplete=set(incomplete)
    blocked={g for e in settings.get('actions',[]) if e.get('file_hash')==ledger['hash'] for g in e.get('blocked',[])}
    manual=[];locked=set();history=[]
    for action in settings.get('actions',[]):
        if action.get('file_hash')!=ledger['hash']:continue
        if action['action']=='release':
            removed=set(action['rows']);manual=[c for c in manual if not c.ids&removed];locked=set().union(*(c.ids for c in manual)) if manual else set();continue
        if action['action']!='approve':continue
        ids=set(action['rows'])
        if not ids<=set(byid):raise ValueError('승인 원본행이 입력 파일과 일치하지 않습니다.')
        manual=[c for c in manual if not c.ids&ids]
        if any(not byid[i].side for i in ids):raise ValueError('음수·양변·0원 행은 승인 배분 대상이 아닙니다.')
        cs=tuple(sorted(i for i in ids if byid[i].side=='C'));ds=tuple(sorted(i for i in ids if byid[i].side=='D'))
        alloc=tuple(sorted((i,int(v)) for i,v in action.get('allocations',{}).items()))
        manual.append(Candidate('U'+action['id'],cs,ds,'수동 재배정' if action.get('reassignment') else '부분정산' if alloc and any(value<byid[i].value for i,value in alloc) else '사용자 매칭',1000,('승인: '+action['approver'],'근거: '+action['reason']),'사용자 승인',alloc))
        locked=set().union(*(c.ids for c in manual))
    if not validate(rows,manual)['ok']:raise ValueError('사용자 승인 배분이 검산을 통과하지 못했습니다.')
    progress('D/E 후보 충돌·전체 최적화',0,len(candidates))
    # Protect exact-purpose equal-amount pairs before broad aggregate combinations.
    exact_pairs=[]
    aggregate_by_credit=defaultdict(list)
    for candidate in candidates:
        if len(candidate.ids)>2 and candidate.id not in blocked and not candidate.ids&locked:
            for identity in candidate.credits:aggregate_by_credit[identity].append(candidate)
    for c in candidates:
        if len(c.credits)!=1 or len(c.debits)!=1 or c.id in blocked or c.ids&locked:continue
        a,b=byid[c.credits[0]],byid[c.debits[0]]
        months=(b.day.year-a.day.year)*12+b.day.month-a.day.month
        earlier_aggregate=any(o.id not in blocked and not o.ids&locked and len(o.ids)>2 and a.row_id in o.credits and o.score>=c.score and all(byid[i].day<b.day for i in o.debits) for o in aggregate_by_credit[a.row_id])
        if not earlier_aggregate and a.department and a.department==b.department and a.unit==b.unit and a.name and a.name==b.name and a.narrative and a.narrative==b.narrative and a.value==b.value and months in (0,1) and a.day<=b.day:
            exact_pairs.append(replace(c,score=200+max(0,62-(b.day-a.day).days),state=c.state,reasons=c.reasons+('거래선·적요·동일금액 우선 배정·일자 보조 비교',)))
    exact_chosen,exact_limit,_=optimize(exact_pairs,cancel,residual_search=True)
    original_scores={c.id:c.score for c in candidates}
    exact_chosen=[replace(c,score=original_scores[c.id]) for c in exact_chosen if not c.ids&exact_limit]
    exact_protected={i for c in exact_chosen for i in c.ids}
    selected,limited,conflicts=optimize([c for c in candidates if c.id not in blocked and not c.ids&(locked|exact_protected)],cancel)
    selected=exact_chosen+selected
    incomplete|=limited
    groups=manual+selected;used=set().union(*(c.ids for c in groups)) if groups else set()
    # Unallocated partial relations are proposals only: no silent completion of source rows.
    remaining=[t for t in rows if t.row_id not in used and t.side]
    partial=[];partial_steps=0
    for c in [t for t in remaining if t.side=='C']:
        if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
        for d in [t for t in remaining if t.side=='D']:
            partial_steps+=1
            if partial_steps>20000:incomplete.update(t.row_id for t in remaining);break
            score,reasons=relation(c,d,settings.get('aliases',[]))
            if score>=50 and c.value!=d.value:
                value=min(c.value,d.value);identifier='P'+hashlib.sha256((c.row_id+d.row_id).encode()).hexdigest()[:16]
                partial.append(Candidate(identifier,(c.row_id,),(d.row_id,),'부분정산 후보',score,reasons+('M16 배분 승인 전 원본 잔액 유지',),'검토후보',((c.row_id,value),(d.row_id,value))))
        if partial_steps>20000:break
    progress('F/G 잔여 재탐색·역검증',len(remaining),len(rows))
    final=[]
    candidate_index=defaultdict(list)
    for candidate in candidates:
        for row in candidate.ids:candidate_index[row].append(candidate)
    for c in groups:
        if c.state=='사용자 승인':final.append(c);continue
        rivals=list({o.id:o for row in c.ids for o in candidate_index[row] if o.id!=c.id and o.id not in blocked}.values())
        ambiguous=any(abs(o.score-c.score)<=10 for o in rivals)
        state='검토후보' if c.ids&limited else '조건부매칭' if c.ids&generation_incomplete or (ambiguous and c.state=='자동매칭') else c.state
        reasons=c.reasons+(('경쟁 후보 존재·원전표 확인',) if rivals else ())+(('후보 선택 최적화 미완료',) if c.ids&limited else ('추가 합산 탐색 미완료·선택 연결은 조건부 유지',) if c.ids&generation_incomplete else ())
        final.append(Candidate(c.id,c.credits,c.debits,c.kind,c.score,reasons,state,c.allocations))
    # Incomplete optimization stays a proposal; broader generation limits do not discard solved selections.
    groups=[c for c in final if c.state!='검토후보']
    first_pass_count=len(groups)
    used={i for g in groups for i in g.ids}
    # A partially approved row stays protected: residual recheck never reuses its capacity.
    residual_rows=[t for t in rows if t.row_id not in used and t.side]
    residual_ids={t.row_id for t in residual_rows}
    progress('G 미매칭 잔여 전용 재검증',0,len(residual_rows))
    exact_candidates,_=residual_period_candidates(residual_rows,True,cancel)
    exact_candidates=[c for c in exact_candidates if c.id not in blocked]
    exact_selected,exact_limited,_=optimize(exact_candidates,cancel,residual_search=True)
    exact_selected=[c for c in exact_selected if not c.ids&exact_limited]
    exact_used={i for c in exact_selected for i in c.ids}
    retry_candidates,retry_generation=generate([t for t in residual_rows if t.row_id not in exact_used],settings.get('aliases',[]),progress,cancel)
    retry_generation=set(retry_generation)
    retry_candidates=[c for c in retry_candidates if c.id not in blocked and c.ids<=residual_ids and not c.ids&exact_used]
    retry_selected,retry_limited,_=optimize(retry_candidates,cancel,residual_search=True)
    retry_limited=set(retry_limited)
    retry_selected=[c for c in retry_selected if not c.ids&retry_limited]
    protected=exact_used|{i for c in retry_selected for i in c.ids}
    monthly,monthly_generation=residual_period_candidates([t for t in residual_rows if t.row_id not in protected],False,cancel)
    monthly=[c for c in monthly if c.id not in blocked]
    monthly_selected,monthly_limited,_=optimize(monthly,cancel,residual_search=True)
    monthly_selected=[c for c in monthly_selected if not c.ids&monthly_limited]
    retry_selected=exact_selected+retry_selected+monthly_selected
    used_retry={i for c in retry_selected for i in c.ids}
    period_candidates,period_generation=residual_explicit_period([t for t in residual_rows if t.row_id not in used_retry],cancel)
    period_candidates=[c for c in period_candidates if c.id not in blocked]
    period_selected,period_limited,_=optimize(period_candidates,cancel,residual_search=True)
    retry_selected.extend(c for c in period_selected if not c.ids&period_limited)
    solved={i for c in retry_selected for i in c.ids}
    retry_limited=(retry_limited|monthly_limited|period_limited)-solved
    retry_generation=(retry_generation|monthly_generation|period_generation)-exact_used
    retry_candidates=exact_candidates+retry_candidates+monthly+period_candidates
    incomplete.difference_update(residual_ids)
    incomplete.update(retry_generation|retry_limited)
    generation_incomplete.difference_update(residual_ids)
    generation_incomplete.update(retry_generation)
    limited.difference_update(residual_ids);limited.update(retry_limited)
    retry_groups=[]
    for c in retry_selected:
        if c.ids&retry_limited or not c.ids<=residual_ids:continue
        # A second-pass connection is explicitly reviewable, not an implicit confirmation.
        reasons=c.reasons+('미매칭 잔여 재검증 연결·원전표 확인',)
        if c.ids&retry_generation:reasons+=('추가 합산 탐색 미완료',)
        retry_groups.append(Candidate(c.id,c.credits,c.debits,c.kind,c.score,reasons,'조건부매칭',c.allocations))
    groups.extend(retry_groups)
    retry_group_ids={c.id for c in retry_groups}
    candidates=list({c.id:c for c in candidates+retry_candidates}.values())
    from suspense_fifo import apply_fifo
    blocked_pairs={(c.credits[0],c.debits[0]) for c in candidates if c.id in blocked and len(c.credits)==len(c.debits)==1}
    groups,fifo_history=apply_fifo(rows,groups,settings.get('aliases',[]),blocked_pairs,cancel,limited)
    history.extend(fifo_history)
    selected_ids={g.id for g in groups}
    suggestions=[Candidate(c.id,c.credits,c.debits,c.kind,c.score,c.reasons+(('탐색 미완료',) if c.ids&incomplete else ()), '검토후보',c.allocations) for c in candidates+partial if c.id not in selected_ids and c.id not in blocked]
    groups.sort(key=lambda c:(min(byid[i].day for i in c.credits),c.id))
    checks=validate(rows,groups)
    previous=settings.get('previous',{}).get(ledger['hash'],[])
    old={tuple(sorted(ids)) for ids in previous};new={tuple(sorted(c.ids)) for c in groups}
    for ids in sorted(old-new):history.append(('해제',','.join(ids),'연관 후보 전체 재최적화 / 승인·해제 반영'))
    for ids in sorted(new-old):history.append(('연결',','.join(ids),'전체 후보 비교 후 선택'))
    progress('H 최종 검산',len(rows),len(rows))
    return {'ledger':ledger,'groups':groups,'generation_incomplete':sorted(generation_incomplete),'optimization_incomplete':sorted(limited),
            'residual_recheck_groups':sorted(retry_group_ids),'search_status':{g.id:('사용자 승인' if g.state=='사용자 승인' else '추가 합산 탐색 미완료' if g.ids&generation_incomplete else '잔여 재검증 선택' if g.id in retry_group_ids else '선택 완료') for g in groups},'candidates':candidates+partial,'suggestions':suggestions,'incomplete':sorted(incomplete),'validation':checks,'history':history,'settings':settings,'version':VERSION,
            'stages':[('전체 원본',len(rows)),('통합 후보',len(candidates)),('1차 선택',first_pass_count),('잔여 재검증 추가 그룹',len(retry_groups)),('최적화 선택',len(groups)),('부분정산 후보',len(partial)),('탐색 미완료 행',len(incomplete))]}
