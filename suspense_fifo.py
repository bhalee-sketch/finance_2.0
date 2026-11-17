"""Chronological reassignment of strong same-purpose, equal-amount recurring pairs."""
from collections import defaultdict
from dataclasses import replace
import hashlib
from suspense_data import party,compact


def compatible(c,d,aliases):
    from suspense_engine import relation,scope_applies
    if not c.department or c.department!=d.department or c.unit!=d.unit or c.value!=d.value or c.day>d.day:return False
    if c.account and d.account and compact(c.account)!=compact(d.account):return False
    if c.months and d.months and set(c.months).isdisjoint(d.months):return False
    if c.period and d.period and c.period!=d.period:return False
    same=c.name and c.name==d.name
    short=c.name and d.name and min(len(c.name),len(d.name))>=4 and (c.name.startswith(d.name) or d.name.startswith(c.name))
    alias=any({party(a.get('source','')),party(a.get('target',''))}=={c.name,d.name} and scope_applies(a,c,d) for a in aliases)
    if not (same or short or alias) or relation(c,d,aliases)[0]<0:return False
    def generic(t):
        value=party(t.narrative).replace(t.name,'')
        for word in ('가수금','입금','정산','납부'):value=value.replace(word,'')
        return not value
    transfer=('가수금부서변경' in compact(d.description) and c.department in d.description and generic(c))
    return bool((c.narrative and c.narrative==d.narrative) or (generic(c) and generic(d)) or transfer)


def apply_fifo(rows,groups,aliases=(),blocked_pairs=(),cancel=lambda:False,excluded=()):
    """Never alter manual/split allocations or reduce settled value in a component."""
    from suspense_engine import Candidate,Cancelled
    byid={t.row_id:t for t in rows};protected=set(excluded)
    for g in groups:
        if g.ids&set(excluded) or g.state=='사용자 승인' or len(g.credits)!=1 or len(g.debits)!=1 or any(value!=byid[i].value for i,value in g.allocations):protected.update(g.ids)
    pools=defaultdict(list);debits=[]
    for t in rows:
        if t.row_id in protected or not t.side:continue
        if t.side=='C':pools[(t.department,t.unit,t.value)].append(t)
        else:debits.append(t)
    key=lambda t:(t.day,t.voucher,t.row,t.row_id)
    for pool in pools.values():pool.sort(key=key)
    used=set();proposals=[];blocked_pairs=set(blocked_pairs)
    for d in sorted(debits,key=key):
        if cancel():raise Cancelled('사용자가 검증을 중단했습니다.')
        eligible=[c for c in pools[(d.department,d.unit,d.value)] if c.row_id not in used and (c.row_id,d.row_id) not in blocked_pairs and compatible(c,d,aliases)]
        # Without an outgoing account, do not guess among different deposit accounts.
        if len({compact(c.account) for c in eligible if c.account})>1:continue
        if not eligible:continue
        c=eligible[0];used.add(c.row_id)
        identity='FIFO'+hashlib.sha256((c.row_id+'|'+d.row_id).encode()).hexdigest()[:16]
        proposals.append(Candidate(identity,(c.row_id,),(d.row_id,),'선입선출 1:1',100,('동일 부서·거래선·목적·동일금액: 이전 대변부터 차변 회계일자순 정산',),'조건부매칭'))
    # Old and proposed edges form independent components. Reject a rearrangement
    # that would discard settlement amounts through competing purpose constraints.
    parent={}
    def find(i):
        parent.setdefault(i,i)
        if parent[i]!=i:parent[i]=find(parent[i])
        return parent[i]
    for g in list(groups)+proposals:
        ids=list(g.ids)
        for i in ids[1:]:parent[find(i)]=find(ids[0])
    old=defaultdict(list);new=defaultdict(list)
    for g in groups:old[find(next(iter(g.ids)))].append(g)
    for g in proposals:new[find(next(iter(g.ids)))].append(g)
    output=[];changes=[]
    for component in set(old)|set(new):
        prior=old[component];proposed=new[component]
        if not proposed:output.extend(prior);continue
        covered={i for g in proposed for i in g.ids}
        kept=[g for g in prior if not g.ids&covered]
        old_value=sum(sum(dict(g.allocations).get(i,byid[i].value) for i in g.credits) for g in prior)
        new_value=sum(sum(dict(g.allocations).get(i,byid[i].value) for i in g.credits) for g in kept+proposed)
        if new_value<old_value:output.extend(prior);continue
        existing={(g.credits,g.debits):g for g in prior}
        chosen=[existing.get((g.credits,g.debits),g) for g in proposed]
        output.extend(kept+chosen)
        if {g.ids for g in prior}!={g.ids for g in kept+chosen}:
            changes.append(('선입선출 재배정',','.join(sorted(covered)),'동일 반복 거래의 대변을 입금일순으로 배분'))
    return output,changes
