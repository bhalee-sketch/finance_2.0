"""Control only automation-owned Chrome windows and recognisable notice overlays."""
import re


def window_state(context,page,state):
    session=None
    try:
        session=context.new_cdp_session(page)
        info=session.send('Browser.getWindowForTarget')
        session.send('Browser.setWindowBounds',{'windowId':info['windowId'],'bounds':{'windowState':state}})
        return True
    except Exception:return False
    finally:
        if session:
            try:session.detach()
            except Exception:pass


def notice_text(text):
    compact=re.sub(r'\s+','',text or '')
    if any(word in compact for word in ('인증','비밀번호','로그인','오류','실패','동의','삭제','취소하시','다운로드','내려받기','파일을받','신고','납부','결제','보안프로그램','설치')):return False
    return any(word in compact for word in ('공지사항','서비스이용안내','이용시간안내','이벤트안내'))


def close_notices(page):
    """Never click a generic page-level X/confirm or close an unknown popup."""
    from hometax_download import is_hometax
    if page.is_closed() or not is_hometax(page.url):return 0
    count=0
    # A separate notice window is safe to close only when both title and body
    # identify it as informational; authentication/download windows stay open.
    try:
        if page.opener() is not None and notice_text(page.title()) and notice_text(page.locator('body').inner_text(timeout=500)):
            page.close();return 1
    except Exception:pass
    for frame in page.frames:
        if not is_hometax(frame.url):continue
        containers=frame.locator('[role="dialog"], .w2window, .w2popup')
        for index in range(min(containers.count(),12)):
            box=containers.nth(index)
            try:
                if not box.is_visible() or not notice_text(box.inner_text(timeout=500)):continue
                button=box.get_by_role('button',name=re.compile(r'^\s*(?:닫기|창\s*닫기|팝업\s*닫기|close|×|✕|X)\s*$',re.I))
                visible=[button.nth(i) for i in range(button.count()) if button.nth(i).is_visible()]
                if len(visible)!=1:
                    button=box.get_by_role('link',name=re.compile(r'^\s*(?:닫기|창\s*닫기|팝업\s*닫기|close|×|✕|X)\s*$',re.I))
                    visible=[button.nth(i) for i in range(button.count()) if button.nth(i).is_visible()]
                if len(visible)==1:visible[0].click(timeout=800);count+=1
            except Exception:continue
    return count


def successful_downloads(rows):
    from verifier import KINDS
    return len(rows)==len(KINDS) and {r[0] for r in rows}==set(KINDS) and all(r[1] in ('저장 완료','기존 파일 유지') for r in rows)
