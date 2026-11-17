"""홈택스 공동인증서 웹 UI 로그인. 비밀번호는 일회성 메모리에서만 전달한다."""
import re
import time
import unicodedata
from hometax_download import is_hometax

OWNER='한동대학교'
EXPIRY='2027-07-02'


class LoginError(ValueError):pass


class OneTimePassword:
    def __init__(self,value):self._buffer=bytearray(value.encode('utf-8'))
    def __repr__(self):return '<OneTimePassword redacted>'
    def clear(self):
        for i in range(len(self._buffer)):self._buffer[i]=0
        self._buffer.clear()
    def take(self):
        try:return self._buffer.decode('utf-8')
        finally:self.clear()


def certificate_flags(text,owner=OWNER,expiry=EXPIRY):
    text=unicodedata.normalize('NFKC',text)
    owner_pattern=r'\s*'.join(map(re.escape,owner))+r'(?=\s|[()\[\]]|$)'
    owner_match=re.search(owner_pattern,text) is not None
    year,month,day=map(int,expiry.split('-'))
    date_pattern=rf'(?<!\d){year}\s*[-./년]\s*0?{month}\s*[-./월]\s*0?{day}(?:일)?(?!\d)'
    return {'owner_matches':owner_match,'expiry_matches':re.search(date_pattern,text) is not None}


def matches_certificate(text,owner=OWNER,expiry=EXPIRY):
    return certificate_flags(text,owner,expiry)['expiry_matches']


ROW_TEXT=r"""e => {
    const cells=[...e.querySelectorAll('td,[role="cell"],[role="gridcell"]')];
    const parts=[];
    for (const cell of cells.length ? cells : [e]) {
        parts.push(cell.innerText || '',cell.textContent || '');
        for (const node of [cell,...cell.querySelectorAll('[title],[aria-label]')])
            parts.push(node.getAttribute('title') || '',node.getAttribute('aria-label') || '');
    }
    return parts.join('\n');
}"""


def row_certificate_text(row):
    # 잘린 표시 문자열 대신 셀 텍스트와 전체 이름 tooltip을 읽는다. 저장하지 않는다.
    return row.evaluate(ROW_TEXT)


def inherited_hometax_frame(frame):
    # about:blank/srcdoc은 홈택스 부모의 출처를 상속한 경우만 허용한다.
    while frame is not None:
        if is_hometax(frame.url):return True
        if frame.url not in ('about:blank','about:srcdoc'):return False
        frame=frame.parent_frame
    return False


def selected_certificate(row):
    return row.evaluate(r'''e => e.getAttribute('aria-selected') === 'true' ||
        e.getAttribute('aria-checked') === 'true' ||
        !!e.querySelector('input:checked') ||
        /(?:^|[\s_-])(?:selected|ui-state-highlight)(?:$|[\s_-])/i.test(e.className || '')''') is True


class CertificateLogin:
    def __init__(self,downloader):
        self.downloader=downloader;self.context=downloader.context
        self.stage='로그인 준비'
    def step(self,stage):
        self.stage=stage;self.downloader.progress(stage+'…')
    def check(self):
        self.downloader.check()
    def frames(self):
        for page in self.context.pages:
            if page.is_closed() or not is_hometax(page.url):continue
            for frame in page.frames:
                if inherited_hometax_frame(frame):yield frame
    def pause(self):self.downloader.pause()
    def unique(self,items,label):
        if len(items)>1:raise LoginError(label+' 항목이 여러 개입니다. Chrome에서 직접 선택해 주세요.')
        return items[0] if items else None
    def named(self,name,scope=None):
        pattern=re.compile(r'^\s*'+r'[\s·ㆍ./]*'.join(map(re.escape,re.sub(r'[\s·ㆍ./]','',name)))+r'\s*$')
        found=[]
        for frame in ([scope] if scope is not None else self.frames()):
            for locator in (frame.get_by_role('button',name=pattern),frame.get_by_role('link',name=pattern),frame.get_by_role('tab',name=pattern),frame.get_by_text(pattern),frame.get_by_alt_text(pattern)):
                matches=self.downloader.visible(locator)
                if matches:
                    found.extend(matches);break
        return self.unique(found,name)
    def wait(self,probe,label,seconds=20):
        deadline=time.monotonic()+seconds
        while True:
            self.check();value=probe()
            if value is not None and value is not False:return value
            if time.monotonic()>=deadline:raise LoginError(label+'를 확인하지 못했습니다. Chrome에서 직접 로그인한 뒤 «로그인 완료 · 4종 받기»를 누르세요.')
            self.pause()
    def certificate(self):
        found=[]
        for frame in self.frames():
            for row in self.downloader.visible(frame.locator('tr, [role="row"]')):
                if matches_certificate(row_certificate_text(row)):found.append((frame,row))
        return self.unique(found,'만료일 2027-07-02 인증서')
    def logged_in(self):
        # 단순 인증창 닫힘을 성공으로 보지 않는다. 로그아웃 메뉴가 실제 표시돼야 한다.
        return self.named('로그아웃') is not None
    def diagnostic(self):
        from urllib.parse import urlparse
        report={'stage':self.stage,'popup_requested':getattr(self.downloader,'certificate_dialog_requested',False) is True,'pages':[]}
        for page in self.context.pages:
            if page.is_closed():continue
            item={'host':urlparse(page.url).hostname,'frames':[]};report['pages'].append(item)
            for frame in page.frames:
                entry={'host':urlparse(frame.url).hostname,'scheme':urlparse(frame.url).scheme,'search_allowed':is_hometax(page.url) and inherited_hometax_frame(frame)}
                item['frames'].append(entry)
                if not entry['search_allowed']:continue
                try:
                    rows=self.downloader.visible(frame.locator('tr, [role="row"]'))
                    entry['visible_rows']=len(rows)
                    entry['row_checks']=[certificate_flags(row_certificate_text(row)) for row in rows]
                    entry['matching_rows']=sum(flags['expiry_matches'] for flags in entry['row_checks'])
                    entry['selected_matches']=[selected_certificate(row) for row,flags in zip(rows,entry['row_checks']) if flags['expiry_matches']]
                    entry['visible_password_fields']=len(self.downloader.visible(frame.locator('input[type="password"]')))
                except Exception as exc:entry['error_type']=type(exc).__name__
        return report

    def open_certificate_dialog(self):
        # 한 Chrome 세션에서 창 열기 버튼은 한 번만 누른다. 실패 후 재시도는
        # 이미 열린 팝업을 다시 찾으며, 새 창을 계속 만들지 않는다.
        if getattr(self.downloader,'certificate_dialog_requested',False) is True:return
        if self.named('하드디스크 이동식') is not None or self.named('인증서 선택창') is not None:return
        tab=self.named('공동·금융인증')
        launch=self.named('공동·금융인증서') or self.named('공동인증서 로그인')
        if tab is None and launch is None:
            self.wait(lambda:self.named('로그인'),'로그인 메뉴').click()
            self.wait(lambda:self.named('공동·금융인증') or self.named('공동·금융인증서'),'공동·금융인증 메뉴')
            tab=self.named('공동·금융인증')
        if tab is not None:tab.click()
        self.step('공동·금융인증서 버튼 및 인증서 창 확인')
        def ready():
            storage=self.named('하드디스크 이동식') or self.named('인증서 선택창')
            if storage is not None:return ('open',storage)
            button=self.named('공동·금융인증서') or self.named('공동인증서 로그인')
            return ('launch',button) if button is not None else None
        state,control=self.wait(ready,'공동·금융인증서 버튼')
        if state=='launch':
            self.downloader.certificate_dialog_requested=True
            control.click()

    def run(self,secret):
        field=None;password=None
        try:
            self.downloader.blocked=False;self.check()
            if self.logged_in():return
            self.step('공동·금융인증 화면 열기')
            certificate=self.certificate()
            if certificate is None:
                self.open_certificate_dialog()
                self.step('인증서 목록 대기 · 만료일 2027-07-02')
                certificate=self.wait(self.certificate,'지정 인증서')
            frame,row=certificate
            self.step('지정 인증서 선택 확인');row.click()
            # 보안 모듈은 선택을 그림/자체 상태로만 표시하기도 한다. CSS class를
            # 필수 조건으로 삼지 않고 성공한 행 클릭과 유일한 만료일 조건을 재확인한다.
            self.check();confirmed=self.certificate()
            if confirmed is None:raise LoginError('선택 후 지정 인증서가 사라졌습니다. 직접 확인해 주세요.')
            frame,row=confirmed
            self.step('인증서 비밀번호 입력칸 확인')
            fields=[v for v in self.downloader.visible(frame.locator('input[type="password"]')) if v.is_enabled() and v.is_editable()]
            field=self.unique(fields,'인증서 비밀번호 입력')
            if field is None:raise LoginError('자동 입력 가능한 인증서 비밀번호 칸이 없습니다. 보안키패드에서 직접 입력해 주세요.')
            self.check();password=secret.take()
            if not password:raise LoginError('비밀번호를 다시 입력해 주세요.')
            self.step('인증서 비밀번호 입력칸 클릭');field.click(timeout=5000)
            self.step('인증서 비밀번호 입력');field.fill(password,timeout=5000)
            if field.input_value(timeout=5000)!=password:raise LoginError('보안 프로그램이 비밀번호 입력을 반영하지 않았습니다. 직접 로그인해 주세요.')
            password=None
            self.step('공동인증서 로그인 확인');self.check()
            self.wait(lambda:self.named('확인',frame),'인증서 확인 버튼',5).click(timeout=10000)
            self.wait(self.logged_in,'홈택스 로그인 완료',60)
        except LoginError:raise
        except Exception:
            # Playwright 예외에는 fill 인자가 포함될 수 있으므로 원문/traceback을 UI에 전달하지 않는다.
            raise LoginError(f'{self.stage} 단계에서 진행하지 못했습니다. Chrome 안내창을 확인하거나 직접 로그인해 주세요.') from None
        finally:
            password=None;secret.clear()
            if field is not None:
                try:
                    if field.is_visible():field.fill('',timeout=1500)
                except Exception:pass
