"""홈택스 선택 항목 탐색: 접근성 이름과 실제 연결 label을 함께 확인한다."""
import re


def radio_name(name):
    return re.compile(r'^\s*'+r'\s*'.join(re.escape(c) for c in name if not c.isspace())+r'(?:\s*선택)?\s*$')


RADIOS='input[type="radio"], [role="radio"]'
# 실제 DOM에서 연결 관계를 읽기만 한다. 입력값/인증정보/페이지 본문은 수집하지 않는다.
FIND_RADIOS=r'''(target) => {
  const norm = s => (s || '').replace(/\s+/g, '').replace(/선택$/, '');
  const visible = e => !!e && e.getClientRects().length > 0 &&
    getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none';
  const nodes = [...document.querySelectorAll('input[type="radio"], [role="radio"]')];
  const labels = [...document.querySelectorAll('label')];
  const found = [];
  nodes.forEach((e, index) => {
    // 네이티브 input을 감싼 중복 ARIA 컨테이너는 별도 후보로 세지 않는다.
    if (e.tagName !== 'INPUT' && e.querySelector('input[type="radio"]')) return;
    const linked = [...(e.labels || [])];
    const names = [e.getAttribute('aria-label'), e.getAttribute('title'), ...linked.map(l => l.textContent)];
    const ids = (e.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    names.push(ids.map(id => document.getElementById(id)?.textContent || '').join(' '));
    if (e.getAttribute('role') === 'radio') names.push(e.textContent);
    // 레거시 WebSquare의 label 연결이 없는 한 항목 컨테이너도 제한적으로 지원한다.
    const parent = e.parentElement;
    if (parent && parent.querySelectorAll('input[type="radio"], [role="radio"]').length === 1)
      names.push(parent.textContent);
    if (!names.some(name => norm(name) === norm(target))) return;
    const label = linked.find(visible);
    if (!visible(e) && !label) return;
    found.push({index, label: label ? labels.indexOf(label) : null, native: e.tagName === 'INPUT'});
  });
  return found;
}'''


def candidates(frame,name):
    return frame.evaluate(FIND_RADIOS,name)


def locate_radio(frame,name):
    """DOM 순서의 첫 항목을 임의 선택하지 않고, 정확히 하나인 후보만 사용한다."""
    found=candidates(frame,name)
    if len(found)==1:
        item=found[0];control=frame.locator(RADIOS).nth(item['index'])
        click=frame.locator('label').nth(item['label']) if item['label'] is not None else control
        return control,click
    if len(found)>1:raise ValueError(f'{name}: 연결된 선택 항목 {len(found)}개. 같은 조회 화면/팝업을 하나만 열어 주세요.')
    # 웹 컴포넌트 접근성 트리에만 노출되는 경우도 지원한다.
    role=frame.get_by_role('radio',name=radio_name(name))
    visible=[role.nth(i) for i in range(role.count()) if role.nth(i).is_visible()]
    if len(visible)==1:return visible[0],visible[0]
    raise ValueError(f'{name}: 연결된 선택 항목을 찾지 못했습니다(화면 후보 {len(visible)}개).')


def selected(control):
    value=control.get_attribute('aria-checked')
    if value in ('true','false'):return value=='true'
    return control.is_checked()
