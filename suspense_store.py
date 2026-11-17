"""Scoped approvals, aliases and an append-only event log, separate from source workbooks."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
from suspense_data import VERSION


def ensure_builtin_rules(settings):
    """Migrate named exceptions once; never re-enable a disabled saved rule."""
    aliases=settings.setdefault('aliases',[])
    identity='department-church-chaplain'
    if not any(rule.get('id')==identity for rule in aliases):
        aliases.append({'id':identity,'kind':'department','source':'교목실 행정지원팀','target':'대학교회',
                        'department':'','start':'','end':'','purpose':'','approved':True,
                        'approver':'기본 규칙 이관','reason':'사용자 지정: 대학교회와 교목실 행정지원팀을 동일 부서로 비교',
                        'origin':'builtin'})
    return settings


def load_settings(path):
    path=Path(path)
    if not path.exists():return ensure_builtin_rules({'version':VERSION,'aliases':[],'actions':[],'previous':{}})
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('actions',[]),list):raise ValueError('승인 설정 파일 형식을 확인하세요.')
    return ensure_builtin_rules(data)


def save_settings(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temporary,path)


def action(settings,ledger,rows,kind,approver,reason,allocations=None,blocked=()):
    if not approver.strip() or not reason.strip():raise ValueError('승인자와 근거를 입력하세요.')
    byid={t.row_id:t for t in ledger['rows']}
    if not rows or not set(rows)<=set(byid):raise ValueError('원본 거래를 선택하세요.')
    stamp=datetime.now(timezone.utc).isoformat()
    record={'id':hashlib.sha256((stamp+'|'.join(sorted(rows))).encode()).hexdigest()[:16],
            'action':kind,'file_hash':ledger['hash'],'rows':sorted(rows),'approver':approver.strip(),'reason':reason.strip(),
            'timestamp':stamp,'allocations':allocations or {},'blocked':list(blocked),'version':VERSION,
            'evidence':[{k:getattr(byid[i],k) for k in ('row_id','voucher','department','counterparty','debit','credit','description')} | {'day':byid[i].day.isoformat()} for i in sorted(rows)]}
    settings.setdefault('actions',[]).append(record)
    return record


def add_alias(settings,source,target,department,start="0001-01-01",end="9999-12-31",purpose="",approver="별칭 등록 화면",reason="사용자가 원본·대응 명칭과 적용 부서를 지정함"):
    from datetime import date
    if not all(v.strip() for v in (source,target,department,start,end,approver,reason)):
        raise ValueError('別칭'.replace('別','별')+'·부서·시작일·종료일·승인자·근거를 입력하세요.')
    if date.fromisoformat(start)>date.fromisoformat(end):raise ValueError('적용 기간을 확인하세요.')
    rule={'source':source,'target':target,'department':department,'start':start,'end':end,'purpose':purpose,
          'approver':approver,'reason':reason,'approved':True,'timestamp':datetime.now(timezone.utc).isoformat()}
    rule['id']='R06-'+hashlib.sha256(json.dumps(rule,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    settings.setdefault('aliases',[]).append(rule)
    return rule


def change_counterparty_rule(settings,rule_id,source=None,target=None,department=None,delete=False):
    """Update user rules while retaining an audit snapshot outside the visible list."""
    from copy import deepcopy
    rule=next((a for a in settings.get('aliases',[]) if a.get('id')==rule_id and a.get('kind','counterparty')=='counterparty' and not a.get('deleted')),None)
    if rule is None:raise ValueError('변경할 거래처 규칙을 선택하세요.')
    before=deepcopy(rule)
    if delete:rule.update(approved=False,deleted=True)
    else:
        if not all(isinstance(v,str) and v.strip() for v in (source,target,department)):raise ValueError('원본 거래처·대응 거래처·적용 부서를 입력하세요.')
        rule.update(source=source.strip(),target=target.strip(),department=department.strip())
    settings.setdefault('alias_events',[]).append({'rule_id':rule_id,'action':'delete' if delete else 'update','before':before,'after':deepcopy(rule),'timestamp':datetime.now(timezone.utc).isoformat()})
    return rule
