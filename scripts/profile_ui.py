"""Profile isolated empty-data menu creation and GUI event latency (not real-data throughput)."""
import sys,os,time,tempfile,json,cProfile,pstats
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
start=time.perf_counter();import app,qt_ui as q
imports=time.perf_counter()-start
errors=[];result=[];profile=cProfile.Profile()
for name in ('showinfo','showwarning','showerror'):setattr(q.messagebox,name,lambda *a,**kw:None)
with tempfile.TemporaryDirectory() as folder,patch.object(app,'desktop',return_value=Path(folder)),patch.object(q.Tk,'mainloop'),patch('startup_update.check_on_start'):
 profile.enable();start=time.perf_counter();app.main();r=q._default_root;r.report_callback_exception=lambda t,v,tb:errors.append(type(v).__name__+': '+str(v));ws=r._launcher.workspace
 for _ in range(3):r.update()
 initial=time.perf_counter()-start
 for key,(title,_) in ws.commands.items():
  start=time.perf_counter();ws.open(key);creation=time.perf_counter()-start;max_event=0;end=time.perf_counter()+.25;loops=0
  while time.perf_counter()<end:
   t=time.perf_counter();q.application().processEvents();max_event=max(max_event,time.perf_counter()-t);loops+=1;time.sleep(.002)
  result.append({'menu':title,'creation_ms':round(creation*1000,1),'max_event_ms':round(max_event*1000,1),'pumps':loops})
  ws.close_tab();q.application().processEvents()
 profile.disable();r.destroy();q.application().processEvents()
print(json.dumps({'imports_s':imports,'main_s':initial,'menus':result,'errors':errors},ensure_ascii=False,indent=2))
pstats.Stats(profile).strip_dirs().sort_stats('cumulative').print_stats(22)
