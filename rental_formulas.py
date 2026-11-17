"""Recalculate the rental template's arithmetic/SUM formulas without executing code."""
import ast
import re
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries


def formula_values(sheet):
    cache={};visiting=set()
    def value(address):
        address=address.replace('$','')
        if address in cache:return cache[address]
        if address in visiting:raise ValueError('임대료 수식이 순환 참조합니다.')
        visiting.add(address);cell=sheet[address]
        if cell.data_type=='f':
            expression=cell.value[1:].replace('$','')
            expression=re.sub(r'([A-Z]+[0-9]+:[A-Z]+[0-9]+)',r'RANGE("\1")',expression)
            try:result=walk(ast.parse(expression,mode='eval').body)
            except (SyntaxError,KeyError,TypeError,ArithmeticError) as exc:raise ValueError(f'{address}: 계산할 수 없는 수식입니다.') from exc
        else:
            try:result=Decimal(str(cell.value)) if cell.value is not None else Decimal(0)
            except ArithmeticError:raise ValueError(f'{address}: 수식이 숫자가 아닌 셀을 참조합니다.') from None
        visiting.remove(address);cache[address]=result;return result
    def walk(node):
        if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):
            return Decimal(str(node.value))
        if isinstance(node,ast.Name) and re.fullmatch('[A-Z]+[0-9]+',node.id):return value(node.id)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return walk(node.operand)*(1 if isinstance(node.op,ast.UAdd) else -1)
        if isinstance(node,ast.BinOp):
            left,right=walk(node.left),walk(node.right)
            if isinstance(node.op,ast.Add):return left+right
            if isinstance(node.op,ast.Sub):return left-right
            if isinstance(node.op,ast.Mult):return left*right
            if isinstance(node.op,ast.Div):return left/right
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
            if node.func.id=='RANGE' and len(node.args)==1 and isinstance(node.args[0],ast.Constant):
                bounds=range_boundaries(node.args[0].value)
                return [value(sheet.cell(r,c).coordinate) for r in range(bounds[1],bounds[3]+1) for c in range(bounds[0],bounds[2]+1)]
            if node.func.id.upper()=='SUM':
                values=[walk(arg) for arg in node.args]
                return sum((sum(v,Decimal(0)) if isinstance(v,list) else v for v in values),Decimal(0))
        raise ValueError('지원하지 않는 임대 수식입니다. 원자료 Excel에서 계산 후 새로고침하세요.')
    return {cell.coordinate:value(cell.coordinate) for row in sheet for cell in row if cell.data_type=='f'}


def restore_formula_caches(saved_path,original,book,edited_sheet,recalculate):
    previous=load_workbook(BytesIO(original),data_only=True)
    try:
        computed=formula_values(book[edited_sheet]) if recalculate else {}
        with ZipFile(saved_path) as archive:parts=[(entry,archive.read(entry.filename)) for entry in archive.infolist()]
        ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        replacements={}
        for i,sheet in enumerate(book,1):
            name=f'xl/worksheets/sheet{i}.xml'
            raw=next(data for entry,data in parts if entry.filename==name)
            root=ET.fromstring(raw)
            for cell in root.iter(ns+'c'):
                if cell.find(ns+'f') is None:continue
                address=cell.attrib['r']
                cached=computed.get(address) if sheet.title==edited_sheet and recalculate else previous[sheet.title][address].value
                value=cell.find(ns+'v')
                if value is None:value=ET.SubElement(cell,ns+'v')
                if cached is None:value.text=None
                elif isinstance(cached,(int,float,Decimal)):
                    value.text=str(cached);cell.set('t','n')
                else:
                    value.text=str(cached);cell.set('t','str')
            replacements[name]=ET.tostring(root,encoding='utf-8')
        with ZipFile(saved_path,'w') as archive:
            for entry,data in parts:archive.writestr(entry,replacements.get(entry.filename,data))
    finally:previous.close()
