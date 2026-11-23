"""다크 테마 Canvas 차트. 정확한 원 단위 금액은 연결 표에 표시한다."""
import math
from decimal import Decimal,ROUND_HALF_UP
from statement_catalog import amount_text
from chart_rendering import polished_chart
from chart_tooltips import bind_tip,pie_hover,amount_detail

COLORS=('#1F77B4','#FF7F0E','#2CA02C','#D62728','#9467BD','#17BECF','#E377C2','#BCBD22','#8C564B','#4E79A7','#59A14F')
BG='#192131'


def million(value):
    rounded=(Decimal(str(value))/1000000).quantize(Decimal(1),rounding=ROUND_HALF_UP)
    return f'{rounded if rounded else Decimal(0):,}'


def compact(value):
    return million(value)+'백만원'


@polished_chart
def donut(canvas,slices,amount_label='결산',source_total=...,total_label='합계'):
    canvas.delete('all');w=max(canvas.winfo_width(),250);h=max(canvas.winfo_height(),180)
    total=sum((v for _,v in slices),Decimal(0))
    if total<=0:
        canvas.configure(scrollregion=(0,0,w,h))
        canvas.create_text(w/2,h/2,text='표시할 양수 결산이 없습니다.',fill='#A9B8CC');return
    visible_height=h;counts={-1:0,1:0};angle=90
    for _,value in slices:
        extent=float(value/total*360);counts[1 if math.cos(math.radians(angle+extent/2))>=0 else -1]+=1;angle+=extent
    h=max(h,max(counts.values())*48+60);canvas.configure(scrollregion=(0,0,w,h))
    radius=max(35,min(w*.235,visible_height*.36));cx=w/2;cy=h/2
    canvas.create_text(14,15,anchor='w',text='단위: 백만원',fill='#A9B8CC',font=('맑은 고딕',9))
    box=(cx-radius,cy-radius,cx+radius,cy+radius);start=90;labels={-1:[],1:[]}
    for i,(label,value) in enumerate(slices):
        extent=float(value/total*360);color=COLORS[i%len(COLORS)];tag=f'slice{i}'
        if len(slices)==1:canvas.create_oval(*box,fill=color,outline=BG,width=2,tags=(tag,))
        else:
            # Windows GDI Pie는 극소 각도의 시작/끝 좌표가 같으면 원 전체를 채울 수 있다.
            # 작은 조각도 실제 각도로 삼각 분할하여 원 전체를 덮지 않게 한다.
            steps=max(1,math.ceil(math.radians(extent)*radius*2));points=[cx,cy]
            for step in range(steps+1):
                theta=math.radians((start+extent*step/steps)%360)
                points.extend((cx+radius*math.cos(theta),cy-radius*math.sin(theta)))
            canvas.create_polygon(*points,fill=color,outline=BG,width=1,tags=(tag,))
        angle=math.radians(start+extent/2);side=1 if math.cos(angle)>=0 else -1
        x=cx+radius*math.cos(angle);y=cy-radius*math.sin(angle)
        labels[side].append((y,x,label,value,color));start+=extent
    # 좌우 라벨을 정렬하여 작은 조각의 과목/금액/비율도 항상 표시한다.
    for side,entries in labels.items():
        entries.sort();gap=min(54,(h-60)/max(1,len(entries)));previous=28-gap
        for index,(y,x,label,value,color) in enumerate(entries):
            ly=max(previous+gap,min(h-28-(len(entries)-1-index)*gap,y));previous=ly
            edge=cx+side*(radius+12);tx=edge+side*7
            canvas.create_line(x,y,edge,ly,tx,ly,fill=color,width=1)
            canvas.create_text(tx,ly,anchor='w' if side>0 else 'e',text=f'{label}\n{million(value)}백만원 ({value/total*100:.1f}%)',fill=color,font=('맑은 고딕',9,'bold'),justify='left' if side>0 else 'right',width=max(75,(w-radius*2)/2-26))
    title=canvas.create_text(cx,cy,text=total_label,fill='#A9B8CC',font=('맑은 고딕',10))
    amount=canvas.create_text(cx,cy,text=(million(total if source_total is ... else source_total)+'백만원') if source_total is not None else '자료 필요',fill='#EDF2FA',font=('맑은 고딕',12 if radius>100 else 9,'bold'))
    title_box=canvas.bbox(title)
    amount_box=canvas.bbox(amount)
    inner=radius*.43
    if title_box and amount_box:
        title_height=title_box[3]-title_box[1]
        amount_height=amount_box[3]-amount_box[1]
        inner=max(inner,math.hypot(max(title_box[2]-title_box[0],amount_box[2]-amount_box[0])/2+4,
                                   (title_height+amount_height+3)/2+4))
        inner=min(inner,radius*.78)
        canvas.coords(title,cx,cy-(amount_height+3)/2)
        canvas.coords(amount,cx,cy+(title_height+3)/2)
    pie_hover(canvas,cx,cy,radius,inner,slices,total)
    canvas.create_oval(cx-inner,cy-inner,cx+inner,cy+inner,fill=BG,outline=BG)
    canvas.tag_raise(title);canvas.tag_raise(amount)


def nice_axis(low,high):
    span=max(high-low,1);target=span/10
    power=10**math.floor(math.log10(max(target,1)))
    step=min((n*power for n in (1,2,5,10)),key=lambda n:abs(n-target))
    if 1000<=span<=10000:step=1000
    elif span<=40000 and span>10000:step=2000
    elif span>40000:step=max(1000,step)
    low=math.floor(min(0,low)/step)*step;high=math.ceil(max(0,high)/step)*step
    return low,max(high,low+step),step


def draw_curve(canvas,points,color):
    if len(points)>1:canvas.create_line(*[v for point in points for v in point],fill=color,width=2.5,smooth=False,capstyle='round',joinstyle='round')


def top_legend(canvas,names,w,y_offset=0):
    count=min(3,max(1,len(names)));cell=min(210,(w-110)/count);start=max(90,w*.57-cell*count/2)
    for j,name in enumerate(names):
        x=start+(j%count)*cell;y=16+y_offset+(j//count)*21;color=COLORS[j%len(COLORS)]
        canvas.create_line(x,y,x+16,y,fill=color,width=3,capstyle='round')
        canvas.create_text(x+22,y,text=name,anchor='w',fill=color,font=('맑은 고딕',9))
    return y_offset+max(52,36+math.ceil(len(names)/count)*21)


@polished_chart
def lines(canvas,headers,rows,amount_label='결산',hide_zero=False,name_labels=False):
    canvas.delete('all');w=max(canvas.winfo_width(),250);h=max(canvas.winfo_height(),180)
    values=[float(v) for row in rows for v in row[1:] if v is not None]
    if not values:
        canvas.create_text(w/2,h/2,text='비교할 과목과 결산 자료를 선택하세요.',fill='#A9B8CC');return
    maximum=max(abs(v) for v in values)
    scale,label=1e6,'백만원'
    lo=min([0]+values)/scale;hi=max([0]+values)/scale
    lo,hi,step=nice_axis(lo,hi+max((hi-lo)*.16,1))
    left=75;right=w-30;top=top_legend(canvas,headers[1:],w)+16;bottom=max(top+40,h-35)
    inset=min(32,(right-left)*.12)
    x=lambda i:(left+right)/2 if len(rows)==1 else left+inset+i*(right-left-2*inset)/(len(rows)-1)
    y=lambda value:bottom-(float(value)/scale-lo)/(hi-lo)*(bottom-top)
    tick=lo
    while tick<=hi+step/100:
        pos=y(tick*scale);canvas.create_line(left,pos,right,pos,fill='#2C384B')
        canvas.create_text(left-8,pos,text=million(tick*scale),anchor='e',fill='#A9B8CC',font=('맑은 고딕',8));tick+=step
    canvas.create_line(left,top,left,bottom,right,bottom,fill='#8D9CB3')
    canvas.create_text(left,15,text=f'{amount_label} ({label})',anchor='w',fill='#A9B8CC')
    stride=max(1,math.ceil(len(rows)/max(1,int((right-left)/50))))
    for i,row in enumerate(rows):
        if i%stride==0 or i==len(rows)-1:canvas.create_text(x(i),bottom+15,text=row[0],fill='#A9B8CC',font=('맑은 고딕',8))
    pending_labels=[]
    for j,name in enumerate(headers[1:]):
        color=COLORS[j%len(COLORS)];segment=[]
        for i,row in enumerate(rows):
            value=row[j+1]
            if value is None:
                draw_curve(canvas,segment,color);segment=[];continue
            if i and str(row[0]).isdigit() and str(rows[i-1][0]).isdigit() and int(row[0])-int(rows[i-1][0])>1:
                draw_curve(canvas,segment,color);segment=[]
            point=(x(i),y(value));segment.append(point)
            item=canvas.create_oval(point[0]-3,point[1]-3,point[0]+3,point[1]+3,fill=color,outline=BG)
            if not (hide_zero and value==0):
                nearby=name_labels and any(k!=j and other is not None and (other!=0 or not hide_zero) and abs(y(other)-point[1])<30 for k,other in enumerate(row[1:]))
                label_text=(name+' ' if nearby else '')+million(value)
                pending_labels.append((point[0],point[1]-22,label_text,color,9))
            bind_tip(canvas,item,amount_detail(row[0],name,value))
        draw_curve(canvas,segment,color)
    segments=[]
    for j in range(1,len(headers)):
        for i in range(1,len(rows)):
            if rows[i-1][j] is not None and rows[i][j] is not None:
                segments.append(((x(i-1),y(rows[i-1][j])),(x(i),y(rows[i][j]))))
    value_labels(canvas,pending_labels,left,top,right,bottom,segments)


@polished_chart
def stacked_years(canvas,headers,rows,amount_rows=None):
    """선택 분모 대비 연도별 누적 비율. 음수/누락은 해당 연도 막대를 생략한다."""
    canvas.delete('all');w=max(canvas.winfo_width(),420);h=max(canvas.winfo_height(),240)
    labels=headers[1:];left=65;right=max(left+120,w-205);top=52;bottom=h-48
    valid=[bool(row[1:]) and all(v is not None and v>=0 for v in row[1:]) for row in rows]
    peak=max([100]+[float(sum(row[1:])) for row,ok in zip(rows,valid) if ok])
    maximum=math.ceil(peak/20)*20
    if maximum>100:maximum=math.ceil(peak/50)*50
    y=lambda v:bottom-float(v)/maximum*(bottom-top)
    step=20 if maximum==100 else max(20,math.ceil(maximum/5/10)*10)
    for tick in range(0,maximum+1,step):
        pos=y(tick);canvas.create_line(left,pos,right,pos,fill='#2C384B')
        canvas.create_text(left-8,pos,text=f'{tick}%',anchor='e',fill='#A9B8CC',font=('맑은 고딕',9))
    canvas.create_line(left,top,left,bottom,right,bottom,fill='#8D9CB3')
    canvas.create_text(left,13,anchor='w',text='수입 분모 대비 지출 (%)',fill='#B9CCDF',font=('맑은 고딕',10))
    slot=(right-left)/max(1,len(rows));bar=min(95,slot*.65)
    for i,(row,ok) in enumerate(zip(rows,valid)):
        x=left+slot*(i+.5);canvas.create_text(x,bottom+18,text=row[0],fill='#C9D8E8',font=('맑은 고딕',9))
        if not ok:
            canvas.create_text(x,(top+bottom)/2,text='자료 확인',fill='#F1BB83',font=('맑은 고딕',9));continue
        total=0
        for j,value in sorted(enumerate(row[1:]),key=lambda pair:-pair[1]):
            high=total+float(value);color=COLORS[j%len(COLORS)]
            tag=f'ratio_{i}_{j}'
            canvas.create_rectangle(x-bar/2,y(high),x+bar/2,y(total),fill=color,outline=BG,width=1,tags=(tag,))
            if y(total)-y(high)>16:
                item=canvas.create_text(x,(y(total)+y(high))/2,text=f'{value:.1f}%',fill='#102334',font=('맑은 고딕',9,'bold'),tags=(tag,))
                bounds=canvas.bbox(item)
                if bounds and (bounds[1]<y(high)+2 or bounds[3]>y(total)-2 or bounds[2]-bounds[0]>bar-4):
                    canvas.delete(item)
            amount=amount_rows[i][j+1] if amount_rows and i<len(amount_rows) else None
            description=f'{row[0]} · {labels[j]}\n{value:.2f}% · '+(compact(amount) if amount is not None else '금액 자료 없음')
            bind_tip(canvas,tag,description)
            total=high
        canvas.create_text(x,y(total)-5,anchor='s',text=f'{total:.1f}%',fill='#E7EDF6',font=('맑은 고딕',9,'bold'))
    for j,label in enumerate(labels):
        yy=top+j*23;canvas.create_rectangle(right+18,yy,right+27,yy+9,fill=COLORS[j%len(COLORS)],outline='')
        canvas.create_text(right+34,yy+4,anchor='w',text=label,fill='#DCE7F5',font=('맑은 고딕',9))
    if not rows:canvas.create_text((left+right)/2,h/2,text='연도별 자료가 없습니다.',fill='#A9B8CC')


def segment_hits_box(segment,box):
    (x,y),(ex,ey)=segment
    low,high=0.,1.
    for start,delta,minimum,maximum in ((x,ex-x,box[0]-3,box[2]+3),(y,ey-y,box[1]-3,box[3]+3)):
        if not delta:
            if not minimum<=start<=maximum:return False
        else:
            a,b=sorted(((minimum-start)/delta,(maximum-start)/delta))
            low=max(low,a);high=min(high,b)
            if low>high:return False
    return True


VALUE_LABEL_OFFSETS=sorted(((dy,dx) for dy in (0,-18,18,-36,36,-54,54) for dx in (0,12,-12,24,-24,36,-36,48,-48,60,-60)),
                           key=lambda pair:pair[0]**2+pair[1]**2*.7+(180 if pair[0]>0 else 0))


def value_labels(canvas,labels,left,top,right,bottom,segments=(),*,skip_overlaps=False):
    """모든 선을 그린 후 숫자를 최상단에 배치하고 인접 라벨 겹침을 피한다."""
    occupied=[]
    for x,y,text,color,size in labels:
        anchor={'anchor':'s'} if skip_overlaps else {}
        item=canvas.create_text(x,y,text=text,fill=color,font=('맑은 고딕',size,'bold'),tags='chart_value',**anchor)
        box=canvas.bbox(item)
        if not isinstance(box,(tuple,list)) or len(box)!=4:box=(x-len(text)*3.5,y-7,x+len(text)*3.5,y+7)
        half=(box[2]-box[0])/2+3;hh=(box[3]-box[1])/2+2
        anchor_offset=y-(box[1]+box[3])/2 if skip_overlaps else 0
        x=max(left+half+10,min(right-half-6,x));chosen=None
        # Prefer labels above their own point. Use horizontal staggering before
        # falling back below, and keep all backgrounds clear of the y axis.
        for offset,dx in VALUE_LABEL_OFFSETS:
            cy=max(top+hh+3,min(bottom-hh,y+offset))
            cx=max(left+half+10,min(right-half-6,x+dx));candidate=(cx-half,cy-hh,cx+half,cy+hh)
            if all(candidate[2]<b[0] or candidate[0]>b[2] or candidate[3]<b[1] or candidate[1]>b[3] for b in occupied) and not any(segment_hits_box(seg,candidate) for seg in segments):
                chosen=(cx,cy,candidate);break
        if chosen is None:
            if skip_overlaps:
                canvas.delete(item)
                continue
            chosen=(x,max(top+hh+3,min(bottom-hh,y)),(x-half,max(top+3,min(bottom-2*hh,y-hh)),x+half,max(top+3,min(bottom-2*hh,y-hh))+2*hh))
        cx,cy,candidate=chosen
        occupied.append(candidate);canvas.coords(item,cx,cy+anchor_offset)
        canvas.create_rectangle(*candidate,fill=BG,outline='',tags='chart_value_background',state='disabled')
        canvas.itemconfigure(item,state='disabled');canvas.tag_raise(item)


@polished_chart
def grant_bars(canvas,headers,rows,counts=None):
    """보조금 목별 막대와 합계 선. 좌측은 목별, 우측은 합계의 백만원 축."""
    canvas.delete('all');w=max(canvas.winfo_width(),420);h=max(canvas.winfo_height(),240)
    if not rows or len(headers)<2:
        canvas.create_text(w/2,h/2,text='국고보조금 자료가 없습니다.',fill='#A9B8CC');return
    left=75;right=max(left+130,w-220);top=40;bottom=h-48
    values=[float(v)/1e6 for r in rows for v in r[1:] if v is not None]
    totals=[sum(r[1:]) if all(v is not None for v in r[1:]) else None for r in rows]
    if any(v<0 for v in values):lines(canvas,headers,rows,'국고보조금');return
    step=totalstep=5000
    maximum=max(5000,math.ceil(max([1]+values)*1.08/5000)*5000)
    totalmax=max(5000,math.ceil(max([1]+[float(v)/1e6 for v in totals if v is not None])*1.08/5000)*5000)
    y=lambda v:bottom-float(v)/1e6/maximum*(bottom-top)
    yt=lambda v:bottom-float(v)/1e6/totalmax*(bottom-top)
    for tick in range(0,int(maximum)+1,int(step)):
        pos=bottom-tick/maximum*(bottom-top);canvas.create_line(left,pos,right,pos,fill='#2C384B')
        canvas.create_text(left-8,pos,text=f'{tick:,}',anchor='e',fill='#A9B8CC',font=('맑은 고딕',9))
    for tick in range(0,int(totalmax)+1,int(totalstep)):
        canvas.create_text(right+8,bottom-tick/totalmax*(bottom-top),text=f'{tick:,}',anchor='w',fill='#F1BB83',font=('맑은 고딕',9))
    canvas.create_line(left,top,left,bottom,right,bottom,right,top,fill='#8D9CB3')
    canvas.create_text(left,14,text='목별 (백만원)',anchor='w',fill='#B9CCDF')
    canvas.create_text(right,14,text='합계 (백만원)',anchor='e',fill='#F1BB83')
    slot=(right-left)/len(rows);bw=slot*.74/max(1,len(headers)-1);segment=[];labels=[]
    for i,row in enumerate(rows):
        center=left+slot*(i+.5)
        if all(v is None for v in row[1:]):canvas.create_text(center,top+20,text='자료 누락',fill='#F1BB83',font=('맑은 고딕',9))
        canvas.create_text(center,bottom+18,text=(f'{counts.get(str(row[0]),0)}건\n{row[0]}년' if counts is not None else row[0]),fill='#C9D8E8',font=('맑은 고딕',9))
        for j,v in enumerate(row[1:]):
            if v is None:continue
            x=center-slot*.37+j*bw;color=COLORS[j%len(COLORS)]
            item=canvas.create_rectangle(x,y(v),x+bw-2,bottom,fill=color,outline='')
            bind_tip(canvas,item,amount_detail(row[0],headers[j+1],v))
            labels.append((x+bw/2,y(v)-14,million(v),color,9))
        value=totals[i]
        if value is None:
            draw_curve(canvas,segment,'#F1BB83');segment=[];continue
        if i and int(row[0])-int(rows[i-1][0])>1:
            draw_curve(canvas,segment,'#F1BB83');segment=[]
        point=(center,yt(value));segment.append(point)
        item=canvas.create_oval(center-3,point[1]-3,center+3,point[1]+3,fill='#F1BB83',outline=BG)
        bind_tip(canvas,item,amount_detail(row[0],'합계',value))
        labels.append((center,point[1]-20,million(value),'#F1BB83',10))
    draw_curve(canvas,segment,'#F1BB83')
    value_labels(canvas,labels,left,top,right,bottom)
    for j,label in enumerate([*headers[1:],'합계 (우측 축)']):
        yy=top+j*23;color='#F1BB83' if j==len(headers)-1 else COLORS[j%len(COLORS)]
        canvas.create_rectangle(w-145,yy,w-136,yy+9,fill=color,outline='')
        canvas.create_text(w-128,yy+4,anchor='w',text=label,fill=color,font=('맑은 고딕',9))


@polished_chart
def bars(canvas,headers,rows,amount_label='결산',legend_below_title=False,*,whole_won=False,show_total=False):
    """선택 과목의 막대를 그리고, 요청 시 각 구간의 합계선을 같은 축에 표시한다."""
    canvas.delete('all');w=max(canvas.winfo_width(),300);h=max(canvas.winfo_height(),220)
    scale,unit=(1,'원') if whole_won else (1e6,'백만원')
    def format_value(value):
        return f'{int(value):,}' if whole_won else million(value)

    def detail(period,name,value):
        return f'{period} · {name}\n{format_value(value)}원' if whole_won else amount_detail(period,name,value)

    names=list(headers[1:])
    totals=[sum(row[1:]) if all(v is not None for v in row[1:]) else None for row in rows] if show_total else []
    values=[float(v)/scale for r in rows for v in r[1:] if v is not None]
    values.extend(float(v)/scale for v in totals if v is not None)
    if not values:
        canvas.create_text(w/2,h/2,text='비교할 과목과 결산 자료를 선택하세요.',fill='#A9B8CC');return
    low,high=min(0,min(values)),max(0,max(values))
    lo,hi,step=nice_axis(low*1.16 if whole_won else low,high*(1.25 if whole_won else 1.16))
    legend=[*names,'합계'] if show_total else names
    left=max(75,20+max(len(f'{int(lo):,}'),len(f'{int(hi):,}'))*8) if whole_won else 75
    right=w-25;top=top_legend(canvas,legend,w,24 if legend_below_title else 0)+12;bottom=h-35
    y=lambda v:bottom-(float(v)/scale-lo)/(hi-lo)*(bottom-top)
    for v in range(int(lo),int(hi)+1,int(step)):
        pos=y(v*scale);canvas.create_line(left,pos,right,pos,fill='#2C384B')
        canvas.create_text(left-8,pos,text=f'{v:,}',anchor='e',fill='#A9B8CC',font=('맑은 고딕',9))
    canvas.create_line(left,top,left,bottom,right,bottom,fill='#8D9CB3')
    canvas.create_text(left,13,anchor='w',text=f'{amount_label} ({unit})',fill='#B9CCDF')
    slot=(right-left)/len(rows);bw=slot*.72/max(1,len(names))
    bar_labels=[];total_labels=[];segments=[]
    for i,row in enumerate(rows):
        cx=left+slot*(i+.5)
        period_anchor={'anchor':'n'} if whole_won else {}
        canvas.create_text(cx,bottom+(8 if whole_won else 16),text=row[0],fill='#C9D8E8',font=('맑은 고딕',9),**period_anchor)
        for j,value in enumerate(row[1:]):
            if value is None:continue
            color=COLORS[j%len(COLORS)];x=cx-slot*.36+bw*j
            bar_end=y(value)
            item=canvas.create_rectangle(x,bar_end,x+bw-2,y(0),fill=color,outline='')
            bind_tip(canvas,item,detail(row[0],names[j],value))
            if whole_won:
                bar_labels.append((x+(bw-2)/2,bar_end+(-20 if value>=0 else 20),format_value(value),color,9))
                segments.append(((x,bar_end),(x+bw-2,bar_end)))
            else:
                canvas.create_text(x+bw/2,bar_end+(-10 if value>=0 else 10),text=format_value(value),fill=color,font=('맑은 고딕',9,'bold'))

    color=COLORS[len(names)%len(COLORS)]
    previous=None
    for i,total in enumerate(totals):
        if total is None:
            previous=None
            continue
        point=(left+slot*(i+.5),y(total))
        x,yy=point
        if previous is not None:
            draw_curve(canvas,(previous,point),color)
            segments.append((previous,point))
        previous=point
        segments.append((point,point))
        item=canvas.create_oval(x-4,yy-4,x+4,yy+4,fill=color,outline=BG)
        bind_tip(canvas,item,detail(rows[i][0],'합계',total))
        total_labels.append((x,yy-22,format_value(total),color,9))
    if bar_labels or total_labels:
        value_labels(canvas,total_labels+bar_labels,left,top,right,bottom,segments,skip_overlaps=whole_won)
