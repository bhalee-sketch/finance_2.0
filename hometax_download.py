"""Chrome 공동인증서 로그인 이후 합계표 Excel 수신. 실서비스 초기 검증용."""
import calendar
import json
import re
import time
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from verifier import KINDS,year_folder,excel_rows,read,key
from hometax_controls import locate_radio,selected,candidates

HOME='https://www.hometax.go.kr/'
MENU='나의 메뉴 → 합계표 조회'

class DownloadError(ValueError):pass


def is_hometax(url):
    parsed=urlparse(url);host=(parsed.hostname or '').lower()
    return parsed.scheme=='https' and (host=='hometax.go.kr' or host.endswith('.hometax.go.kr'))


def masked_dialog(kind,message):
    return kind=='confirm' and all(word in message for word in ('주민등록번호','뒷자리','보안','해제'))


def download_dialog(kind,message):
    text=re.sub(r'\s+','',message).rstrip('?？.')
    return kind=='confirm' and text in (
        '파일을받으시겠습니까','파일을다운로드하시겠습니까','파일을내려받으시겠습니까')


def period_visible(text,year,month):
    day=calendar.monthrange(int(year),int(month))[1]
    def date(d):return rf'{int(year)}\s*[-./년]\s*0?{int(month)}\s*[-./월]\s*0?{d}(?:일)?'
    return bool(re.search(r'거래기간\s*'+date(1)+r'\s*[~～]\s*'+date(day)+r'(?!\d)',text))


def existing_files(folder,kind):
    if not folder.exists():return []
    return [p for p in folder.iterdir() if p.is_file() and not p.name.startswith('~$')
            and p.suffix.lower() in ('.xls','.xlsx','.xlsm') and '홈택스' in p.stem
            and kind in p.stem and '학사' not in p.stem]


def validate_excel(path,kind):
    """현재 검증기가 쓰는 홈택스 열 배치를 확인한다. 불일치 파일은 월 폴더에 넣지 않는다."""
    rows=excel_rows(path,1)
    try:
        prefix=[]
        for _,row in zip(range(9),rows):prefix.append(row)
    finally:rows.close()
    if len(prefix)<9:raise DownloadError('검증용 홈택스 자료의 머리글(9행)이 없습니다.')
    headers=[re.sub(r'\s+','',str(v or '')) for v in prefix[8]]
    if len(headers)<5 or '등록번호' not in headers[1] or not any(s in headers[2] for s in ('상호','성명')) or '공급가액' not in headers[4]:
        raise DownloadError('다운로드 파일의 열 배치가 현재 검증 양식과 다릅니다. 파일 확인이 필요합니다.')
    if '세금' in kind and (len(headers)<7 or '세액' not in headers[5] or '합계' not in headers[6]):
        raise DownloadError('세액·합계금액 열을 확인할 수 없습니다.')
    result={}
    read(path,True,'세금' in kind,result)
    rows=excel_rows(path,10)
    try:return sum(bool(key(row[1])) for row in rows if len(row)>1)
    finally:rows.close()


def install_file(source,root,year,month,kind):
    if kind not in KINDS:raise DownloadError('지원하지 않는 자료 종류입니다.')
    source=Path(source);folder=year_folder(root,year)/f'{int(month)}월'
    if existing_files(folder,kind):raise DownloadError('동일 종류의 기존 파일이 있어 덮어쓰지 않았습니다.')
    validate_excel(source,kind);folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'홈택스{kind}{source.suffix.lower()}'
    # 독점 생성: 다른 실행 창에서 파일을 만들었어도 덮어쓰지 않는다.
    try:
        with target.open('xb') as output,source.open('rb') as incoming:shutil.copyfileobj(incoming,output)
    except FileExistsError:raise DownloadError('다른 실행에서 같은 파일을 저장했습니다. 기존 파일을 유지합니다.')
    except Exception:
        target.unlink(missing_ok=True);raise
    return target


class BrowserDownloader:
    def __init__(self,context,stop=None,progress=lambda message:None,minimized=False):
        self.minimized=minimized;self._notice_check=0
        self.context=context;self.stop=stop;self.progress=progress;self.received=[];self.waiting=False;self.blocked=False;self.stage='시작'
        for page in context.pages:self.attach(page)
        context.on('page',self.attach)
    def attach(self,page):
        from hometax_window import window_state,close_notices
        if self.minimized:window_state(self.context,page,'minimized')
        def loaded():
            if self.minimized:window_state(self.context,page,'minimized')
            close_notices(page)
        page.on('domcontentloaded',loaded)
        page.set_default_timeout(15000)
        page.on('dialog',self.dialog)
        page.on('download',lambda download:self.received.append(download) if self.waiting else None)
    def dialog(self,dialog):
        from hometax_window import notice_text
        if masked_dialog(dialog.type,dialog.message):dialog.dismiss()
        elif self.waiting and not (self.stop and self.stop.is_set()) and download_dialog(dialog.type,dialog.message):
            dialog.accept()
        elif dialog.type=='alert' and notice_text(dialog.message):
            dialog.accept()
        else:
            self.blocked=True
            self.progress('추가 안내창이 나왔습니다. Chrome에서 직접 확인해 주세요. 자동으로 확인/취소하지 않습니다.')
    def check(self):
        if self.stop and self.stop.is_set():raise DownloadError('사용자가 중단했습니다. 완료 파일은 유지합니다.')
        if self.blocked:raise DownloadError('추가 안내창을 직접 처리한 뒤 다시 시도하세요.')
        now=time.perf_counter()
        if now-self._notice_check>1:
            self._notice_check=now
            from hometax_window import close_notices
            for page in self.context.pages:close_notices(page)
    def frames(self):
        for page in self.context.pages:
            if page.is_closed() or not is_hometax(page.url):continue
            for frame in page.frames:
                if is_hometax(frame.url):yield frame
    def visible(self,locator):return [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    def control(self,frame,name,role='button'):
        pattern=re.compile(r'^\s*'+r'\s*'.join(re.escape(c) for c in name if not c.isspace())+r'\s*$')
        for locator in (frame.get_by_role(role,name=pattern),frame.get_by_role('link',name=pattern),frame.get_by_text(pattern)):
            items=self.visible(locator)
            if len(items)==1:return items[0]
            if len(items)>1:raise DownloadError(f'«{name}» 항목이 여러 개입니다. 합계표조회 화면 하나만 열어 주세요.')
        raise DownloadError(f'«{name}» 항목을 찾지 못했습니다. 화면 변경 또는 로그인을 확인하세요.')
    def form(self):
        found=[]
        for frame in self.frames():
            try:locate_radio(frame,'월별')
            except ValueError:continue
            if '합계표' in frame.locator('body').inner_text():found.append(frame)
        if len(found)!=1:raise DownloadError('로그인 후 합계표조회 화면 하나를 열어 주세요. '+MENU)
        return found[0]
    def step(self,name):
        self.stage=name;self.progress(name+'…')
    def menu_control(self,name):
        matches=[]
        for frame in self.frames():
            try:matches.append(self.control(frame,name))
            except DownloadError as exc:
                if '여러 개' in str(exc):raise
        if len(matches)>1:raise DownloadError(f'«{name}» 항목이 여러 창에 있습니다. 홈택스 창 하나만 남겨 주세요.')
        return matches[0] if matches else None
    def pause(self):
        self.check()
        pages=[p for p in self.context.pages if not p.is_closed() and is_hometax(p.url)]
        if not pages:raise DownloadError('열린 홈택스 Chrome 창이 없습니다.')
        pages[0].wait_for_timeout(200)
    def navigate(self):
        self.step('합계표 화면 확인')
        try:return self.form()
        except DownloadError:pass
        for name in ('나의 메뉴','합계표 조회'):
            self.step(name+' 메뉴 열기');deadline=time.monotonic()+15
            while True:
                self.check();control=self.menu_control(name)
                if control is not None:
                    control.click();break
                if time.monotonic()>=deadline:raise DownloadError(f'«{name}» 메뉴를 찾지 못했습니다. '+MENU+' 경로를 직접 열어 주세요.')
                self.pause()
        self.step('합계표 화면 로딩 확인');deadline=time.monotonic()+15
        while True:
            self.check()
            try:return self.form()
            except DownloadError:
                if time.monotonic()>=deadline:raise
            self.pause()
    def failure_message(self,error):
        if isinstance(error,DownloadError):reason=str(error)
        elif type(error).__name__=='TimeoutError':reason='화면 응답 대기 시간이 초과되었습니다.'
        elif isinstance(error,OSError):reason='파일 저장 또는 읽기에 실패했습니다. 저장 폴더 권한과 파일 사용 여부를 확인하세요.'
        else:reason='화면 제어 또는 파일 검증에 실패했습니다.'
        # 브라우저 예외 원문에는 페이지 데이터가 포함될 수 있어 출력하지 않는다.
        return f'[{self.stage}] {reason} ({type(error).__name__})'
    def save_diagnostic(self,folder,error):
        """화면 본문·입력값·URL·인증정보 없이 알려진 항목의 탐색 결과만 저장."""
        report={'stage':self.stage,'error_type':type(error).__name__,'frames':[]}
        try:
            for frame in self.frames():
                item={'radios':{}};report['frames'].append(item)
                for name in ('전자세금계산서','전자계산서','매입','매출','월별','분기별'):
                    try:item['radios'][name]={'matches':len(candidates(frame,name))}
                    except Exception as exc:item['radios'][name]={'error_type':type(exc).__name__}
            target=Path(folder)/'화면진단.json'
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            return target
        except Exception:return None
    def radio(self,frame,name):
        self.step(name+' 선택')
        try:
            control,click=locate_radio(frame,name)
            if not selected(control):click.click()
            deadline=time.monotonic()+5
            while True:
                self.check();control,_=locate_radio(frame,name)
                if selected(control):return
                if time.monotonic()>deadline:raise DownloadError(f'{name} 선택이 반영되지 않았습니다.')
                frame.page.wait_for_timeout(100)
        except ValueError as e:raise DownloadError(str(e)) from e
    def select_period(self,frame,year,month):
        for value,label in ((str(year),'연도'),(str(month),'월')):
            self.step(label+' 선택');candidates=[]
            for select in self.visible(frame.locator('select')):
                options=select.locator('option').all_text_contents()
                normalized=[re.sub(r'\s+','',v) for v in options]
                expected=[v for v in normalized if re.fullmatch(r'\d{4}년?' if label=='연도' else r'0?[1-9]월?|1[0-2]월?',v)]
                if len(expected)<2:continue
                for raw,norm in zip(options,normalized):
                    if norm.rstrip('년월').lstrip('0')==value:
                        candidates.append((select,raw));break
            if len(candidates)!=1:raise DownloadError(f'{label} 선택 목록을 확인할 수 없습니다. Chrome 화면을 확인하세요.')
            select,raw=candidates[0];select.select_option(label=raw)
            if select.locator('option:checked').inner_text().strip()!=raw.strip():raise DownloadError(f'{label} 선택 실패')
    def ready(self,frame,name,year=None,month=None):
        """상시 통신하는 사이트에서도 다음 실제 UI가 준비되면 진행한다."""
        deadline=time.monotonic()+30
        while True:
            self.check()
            try:
                control=self.control(frame,name)
                busy=any(node.is_visible() for node in self.visible(frame.locator('[aria-busy="true"]')))
                period_ok=year is None or period_visible(frame.locator('body').inner_text(),year,month)
                if control.is_enabled() and control.get_attribute('aria-disabled')!='true' and not busy and period_ok:return
            except DownloadError:pass
            if time.monotonic()>=deadline:raise DownloadError(f'«{name}» 준비 대기 시간이 초과되었습니다. Chrome의 조회 결과와 안내창을 확인하세요.')
            self.pause()
    def download_popup(self):
        deadline=time.monotonic()+30
        while True:
            self.check();popups=[]
            for candidate in self.frames():
                try:button=self.control(candidate,'엑셀')
                except DownloadError:continue
                if button.is_enabled() and '내려받기 파일 종류 선택' in candidate.locator('body').inner_text():popups.append((candidate,button))
            if len(popups)==1:return popups[0]
            if len(popups)>1:raise DownloadError('엑셀 다운로드 팝업이 여러 개입니다. 하나만 열어 주세요.')
            if time.monotonic()>=deadline:raise DownloadError('엑셀 다운로드 팝업 준비 대기 시간이 초과되었습니다.')
            self.pause()
    def download_one(self,year,month,kind,staging):
        self.check();self.blocked=False;frame=self.navigate()
        side='매입' if kind.startswith('매입') else '매출';category='전자세금계산서' if '세금' in kind else '전자계산서'
        self.radio(frame,category);self.radio(frame,side);self.radio(frame,'월별');self.select_period(frame,year,month)
        self.step('조회 버튼 클릭');self.control(frame,'조회').click()
        self.step('조회 결과 거래기간 및 명세서 조회 버튼 대기');self.ready(frame,'명세서 조회',year,month)
        self.step('조회 조건 및 거래기간 검증')
        for label in (category,side,'월별'):
            try:control,_=locate_radio(frame,label)
            except ValueError as e:raise DownloadError(str(e)) from e
            if not selected(control):raise DownloadError('조회 조건이 변경되었습니다. 다운로드를 중단합니다.')
        if not period_visible(frame.locator('body').inner_text(),year,month):raise DownloadError('조회 결과의 거래기간이 선택 연월과 일치하는지 확인할 수 없습니다.')
        self.step('명세서 조회 버튼 클릭');self.control(frame,'명세서 조회').click()
        self.step('명세서 파일내려받기 버튼 대기');self.ready(frame,'파일내려받기')
        self.step('파일내려받기 버튼 클릭');self.control(frame,'파일내려받기').click()
        self.step('엑셀 팝업 및 전체 건수 확인')
        popup,button=self.download_popup();body=popup.locator('body').inner_text()
        count=re.search(r'검색\s*총\s*건수\s*[:：]\s*([\d,]+)',body)
        if not count:raise DownloadError('다운로드 대상 전체 건수를 확인할 수 없습니다.')
        total=int(count[1].replace(',',''))
        if total==0:raise DownloadError('조회 결과가 0건입니다. 검증용 파일을 자동 생성하지 않았습니다.')
        ranges=[]
        for select in self.visible(popup.locator('select')):
            label=select.locator('option:checked').inner_text()
            m=re.fullmatch(r'\s*1\s*[~～-]\s*([\d,]+)\s*',label)
            if m:ranges.append(int(m[1].replace(',','')))
        if ranges!=[total]:raise DownloadError('다운로드 범위가 전체 건수와 다릅니다. 분할 다운로드가 필요한 자료는 직접 확인하세요.')
        self.check();self.received.clear();self.waiting=True
        try:
            self.step('엑셀 다운로드');button.click();deadline=time.monotonic()+90
            while not self.received:
                self.check()
                if time.monotonic()>deadline:raise DownloadError('다운로드 대기 시간이 초과되었습니다.')
                popup.page.wait_for_timeout(100)
            if len(self.received)!=1:raise DownloadError('여러 다운로드가 동시에 발생했습니다. 자동화 Chrome을 직접 조작하지 마세요.')
            download=self.received[0];suffix=Path(download.suggested_filename).suffix.lower()
            if suffix not in ('.xls','.xlsx','.xlsm'):raise DownloadError('Excel 형식이 아닌 파일이 내려왔습니다.')
            target=Path(staging)/f'{kind}{suffix}';download.save_as(target)
            if download.failure():raise DownloadError('Chrome의 파일 다운로드가 실패했습니다.')
            self.step('다운로드 파일 양식 및 건수 검증')
            if validate_excel(target,kind)!=total:raise DownloadError('다운로드한 명세 행 수와 화면의 전체 건수가 다릅니다. 확인대기 파일을 확인하세요.')
            return target
        finally:self.waiting=False
    def run(self,root,year,month):
        self.blocked=False
        folder=year_folder(root,year)/f'{int(month)}월';out=[]
        if not 1<=int(month)<=12:raise DownloadError('월을 1~12 사이로 선택하세요.')
        stage=year_folder(root,year)/'홈택스확인대기'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        stage.mkdir(parents=True,exist_ok=True)
        for kind in KINDS:
            self.step(f'{kind} 기존 파일 확인');saved=None
            try:
                self.check();existing=existing_files(folder,kind)
                if len(existing)>1:raise DownloadError('같은 종류의 기존 파일이 여러 개입니다. 월 폴더를 정리하세요.')
                if existing:
                    validate_excel(existing[0],kind);out.append((kind,'기존 파일 유지',str(existing[0])));continue
                source=self.download_one(year,month,kind,stage)
                self.step('검증 파일 월 폴더 저장')
                target=install_file(source,root,year,month,kind);source.unlink();saved=target
                self.step('완료된 다운로드 팝업 닫기')
                # 성공한 다운로드 팝업만 닫는다. 사이트가 자동으로 닫았다면 생략.
                for frame in self.frames():
                    if '내려받기 파일 종류 선택' in frame.locator('body').inner_text():
                        try:self.control(frame,'취소').click()
                        except DownloadError:raise DownloadError('다운로드 팝업을 직접 닫고 다시 시도하세요.')
                out.append((kind,'저장 완료',str(target)))
            except Exception as e:
                message=self.failure_message(e)
                diagnostic=self.save_diagnostic(stage,e)
                if diagnostic:message+=f" / 진단: {diagnostic}"
                out.append((kind,'저장 완료·중단' if saved else '중단',(str(saved)+' / ' if saved else '')+message));break
        attempted={r[0] for r in out}
        out.extend((k,'미실행','앞 단계 확인 후 다시 시도하세요.') for k in KINDS if k not in attempted)
        if not any(stage.iterdir()):stage.rmdir()
        return out
