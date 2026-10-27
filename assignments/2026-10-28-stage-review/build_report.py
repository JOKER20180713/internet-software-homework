"""Build the submission PDF from saved real traces and browser screenshots."""
from pathlib import Path
import json
import textwrap
import unicodedata
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, XPreformatted
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'
OUT=ROOT/'output/pdf';OUT.mkdir(parents=True,exist_ok=True)
FILE=OUT/'个人项目阶段性验收报告.pdf'
pdfmetrics.registerFont(TTFont('CN','C:/Windows/Fonts/simsun.ttc',subfontIndex=0))
pdfmetrics.registerFont(TTFont('CNBold','C:/Windows/Fonts/simhei.ttf'))
pdfmetrics.registerFontFamily('CN',normal='CN',bold='CNBold')
W,H=A4;CW=W-92
red=colors.HexColor('#8c001a');muted=colors.HexColor('#726870')
styles={
 'body':ParagraphStyle('body',fontName='CN',fontSize=10.5,leading=15.5,spaceAfter=6,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='CN',fontSize=8.5,leading=11.5,spaceAfter=4,wordWrap='CJK',textColor=muted),
 'h1':ParagraphStyle('h1',fontName='CNBold',fontSize=21,leading=25,spaceAfter=11,textColor=red),
 'h2':ParagraphStyle('h2',fontName='CNBold',fontSize=13,leading=18,spaceBefore=6,spaceAfter=6),
 'cell':ParagraphStyle('cell',fontName='CN',fontSize=9,leading=13,wordWrap='CJK'),
 'code':ParagraphStyle('code',fontName='CN',fontSize=8.1,leading=10.8,textColor=colors.HexColor('#26394b'))}
story=[]
def read(name):return json.loads((E/name).read_text('utf-8'))
def chats(tr):return [e for e in tr['events'] if e['type']=='provider' and e['kind']=='chat']
def p(text,style='body'):story.append(Paragraph(text,styles[style]))
def heading(text):p(text,'h1')
def sub(text):p(text,'h2')
def table(rows,widths=None):
    content=[[Paragraph(escape(str(v)).replace('\n','<br/>'),styles['cell']) for v in row] for row in rows]
    t=Table(content,colWidths=widths or [CW/len(rows[0])]*len(rows[0]),hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f2e6ea')),('LINEBELOW',(0,0),(-1,0),.7,red),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#e4dfe1'))]))
    story.extend([t,Spacer(1,10)])
def print_json(value,depth=0):
    if depth>=2 or not isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False)
    if isinstance(value,dict):
        return '{\n'+',\n'.join('  '*(depth+1)+json.dumps(k,ensure_ascii=False)+': '+print_json(v,depth+1) for k,v in value.items())+'\n'+'  '*depth+'}'
    return '[\n'+',\n'.join('  '*(depth+1)+print_json(v,depth+1) for v in value)+'\n'+'  '*depth+']'
def code(value):
    text=value if isinstance(value,str) else print_json(value)
    # Soft-wrap wide Chinese lines for print; original unmodified JSON remains in evidence.
    lines=[]
    for line in text.splitlines():
        buf='';n=0
        for c in line:
            width=2 if unicodedata.east_asian_width(c) in 'WF' else 1
            if n+width>108:lines.append(buf);buf='  ';n=2
            buf+=c;n+=width
        lines.append(buf)
    block=XPreformatted(escape('\n'.join(lines)),styles['code'])
    t=Table([[block]],colWidths=[CW],hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f6f5f4')),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#ddd7da')),('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]));story.extend([t,Spacer(1,9)])
def picture(name,caption,width=CW):
    file=E/'screenshots'/name
    with PILImage.open(file) as im:height=width*im.height/im.width
    story.extend([Image(str(file),width=width,height=height),Spacer(1,5)])
    p(caption+'（原尺寸图片见 evidence/screenshots，可放大核对。）','small')
def page():story.append(PageBreak())
def source(name,tr):p('证据：evidence/'+name+'；Trace '+tr['id'],'small')

repo='https://github.com/JOKER20180713/internet-software-homework'
folder=repo+'/tree/master/assignments/2026-10-28-stage-review'
t1=read('08-ui-template.json');c1=chats(t1)[0]
tk=read('04-knowledge.json');ck=chats(tk)[0]
ts=read('05-skill-builtin.json');cs=chats(ts)
tu=read('06-skill-upload.json');cu=chats(tu)
tm=read('07-mcp.json');cm=chats(tm)

heading('CampusClaw\n个人项目阶段性验收')
p('基于原有 Token 登录与班级知识库的 AI 应用平台','h2')
p('验收日期：2026 年 10 月 27 日　｜　提交类型：个人项目 PDF 报告','small')
sub('项目简介与 Git 仓库')
p('本项目在前期 CampusClaw 教学材料系统上扩展 AI 应用工作区。教师和学生登录后，可以使用学习、写作、班级知识问答及工具助手；对话使用阿里云百炼模型，并在右侧查看真实请求参数、响应和工具过程。')
p('Git 仓库：<link href="'+repo+'" color="#8c001a">'+repo+'</link>','small')
p('本次独立目录：<link href="'+folder+'" color="#8c001a">assignments/2026-10-28-stage-review</link>；源码、证据和本报告均在该目录。','small')
table([['验收功能','实现与可核验证据'],['多个 AI 应用','学习助手、写作助手、班级知识问答、工具助手；均通过真实模型调用验证。'],['提示词模板','按用户、按应用保存；{audience} 与 {style} 在服务端替换；每轮作为 system 消息传递。'],['知识库检索','教师上传 .txt/.md；按班级筛选后进行 BM25 + 向量混合检索，返回片段、来源与字符偏移。'],['内置及上传 Skill','内置学习提纲、计算核验；可上传 .md 技能；先发送元数据，再按需加载完整正文。'],['外部工具与 MCP','独立 HTTP 四则运算服务；官方 MCP 示例 get-sum 加法，通过 stdio JSON-RPC 接入。']],[115,CW-115])
sub('运行结构')
code('浏览器工作区 → Flask API（JWT / 用户与班级权限）\n                     ├─ SQLite：模板、技能、历史、知识片段、调用记录\n                     ├─ 百炼：qwen-plus / text-embedding-v4\n                     ├─ HTTP：127.0.0.1:8093/calculate\n                     └─ MCP 客户端 → 独立 Node.js 服务 → get-sum')
p('本次只使用新建的合成课堂材料和演示账号。密钥只从本机环境变量读取，公开仓库不含密钥、JWT、数据库或用户上传目录。','small')

page();heading('01  对话参数与模型返回')
p('<b>结论：</b>提示词模板会随每轮请求一起发送。变量替换后的模板位于 messages[0].content，role 为 system；当前问题为 user 消息。最多保留最近 3 轮 user/assistant 历史，不依靠模型服务记住上次对话。')
p('接口：POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions','small')
sub('实际请求 JSON')
code(c1['request'])
sub('实际返回字段摘录')
response=c1['response']
code({k:response[k] for k in ['id','model','choices','usage'] if k in response})
source('08-ui-template.json',t1)
p('记录保留完整响应；本页省略顶层创建时间等非关键字段。流量未设置 stream，使用完整 JSON 返回。Authorization 密钥请求头不记录。','small')

page();heading('02  提示词与多应用效果')
picture('01-apps-template-request.png','图 1：左侧四个应用及已保存模板；右侧为该问题实际发送的模型请求。')
sub('验证步骤与结果')
table([['操作','结果'],['保存模板并刷新页面','自定义模板仍存在；模板规定“学习提示：”开头，实际回答遵循该要求。'],['继续上一轮对话','02-history.json 显示 history_messages=2；第二次请求包含前一轮问题和回答。'],['切换写作助手','03-writing.json 返回班级读书交流通知，使用写作应用自己的模板。'],['浏览器验证','Chrome；1600×1100、390×844；页面非空、无错误遮罩、无控制台错误；退出后清空界面。']],[125,CW-125])
p('四个应用共享真实模型客户端，但各自配置和用途独立。知识应用执行检索，工具应用执行工具调用；它们不只是四个界面按钮。模板保存按当前用户隔离。','small')

page();heading('03  知识库是否全部发送')
p('<b>结论：</b>本次问答没有发送整个知识库。服务端按登录用户的班级先筛选候选片段，再做关键词/向量混合检索，最多发送前 2 个片段。')
r=tk['retrieval']
table([['核验项','实际值'],['本班已索引片段 / 本次发送',str(r['total_class_chunks'])+' / '+str(r['selected_count'])],['本次来源',', '.join(s['material_title'] for s in r['sources'])],['跨班隔离','B 班磁铁材料及 B_CLASS_PRIVATE_1028 标记未出现在聊天模型请求中。'],['未发送资料','图书角、运动会、合唱资料正文未发送；来源对照见 fixtures 与原始 JSON。'],['模型最终回答',tk['answer']]],[150,CW-150])
picture('04-knowledge-scope.png','图 2：本班 5 个索引片段中选出 2 个；回答引用科学材料并展示可溯源原文。')
p('入库时以约 800 字符切片、重叠 80 字符，发送到 text-embedding-v4（1024 维），向量存入 SQLite。问答时先对问题做向量化，再用 BM25 与余弦相似度进行 RRF 排序；发送给聊天模型的是命中片段文本，不是整个向量库。','small')
p('本次第二条是“位置”关键词引起的弱相关美术候选，最终答案只引用科学资料。这说明检索仍有噪声；不能把“最多取两条”解释为每条都完全相关。','small')
source('04-knowledge.json',tk)

page();heading('04  Skill 正文何时传递')
p('<b>结论：</b>绑定后，第一个模型请求只包含所选 Skill 的 ID、名称、描述及 load_skill 函数定义，不包含完整正文。服务端响应加载调用后，本轮后续请求的 role=tool 消息才包含完整正文。')
table([['观察点','本次真实结果'],['首轮请求','只开放 load_skill；CALC_SKILL_BODY_1028 正文标记不存在。'],['第二轮请求','包含完整 instructions；正文标记出现，同时开放 calculate 工具。'],['未绑定技能','没有发送其他内置技能或其他用户上传技能的完整正文。'],['下一次用户提问','重新从元数据开始加载；存储历史只保留问答文本，不保存此前工具正文。']],[123,CW-123])
sub('第一轮仅传递的技能元数据')
code({k:ts['skill'][k] for k in ['id','name','description']})
sub('加载后，第二轮新增的 tool 消息（完整正文）')
p('下方为便于阅读展开 content 字符串后的表示；实际请求中的 content 是 JSON 字符串，原样记录见证据文件。','small')
skill_msg=next(m for m in cs[1]['request']['messages'] if m['role']=='tool')
code({'role':skill_msg['role'],'tool_call_id':skill_msg['tool_call_id'],'content':json.loads(skill_msg['content'])})
sub('上传技能验证')
p('浏览器上传 fixtures/uploaded-summary.md 后，列表出现 three-line-summary，实际模型输出“主题 / 要点 / 自测”三行复习卡。首轮没有 UPLOADED_SKILL_BODY_1028，加载后才出现；其他用户使用该上传技能返回 404。')
p('Skill 是本平台约定格式的 Markdown 指令文件。仅校验和存储 name、description、正文；不把上传文件当成 Python、Shell 或本机助手指令执行。','small')
source('05-skill-builtin.json',ts);source('06-skill-upload.json',tu)

page();heading('05  Skill 的实际执行逻辑')
p('问题：请核验 (18 + 24) * 3 / 2 的结果。内置 calculation-review 技能通过三个模型轮次完成，执行权在服务端，模型只生成工具调用参数。')
table([['顺序','真实执行'],['LLM 第 1 轮','模型返回 load_skill(skill_id="calculation-review")。服务器核对技能已绑定及访问权限，返回完整正文。'],['LLM 第 2 轮','模型读到正文后返回 calculate(expression="(18 + 24) * 3 / 2")。服务器检查工具白名单和参数，POST 到独立 HTTP 进程。'],['工具执行','external_calculator.py 用 AST 只解析数字、括号、加减乘除，计算得到 63.0；禁止函数调用、属性访问和幂运算。'],['LLM 第 3 轮','role=tool 携带真实结果及对应 tool_call_id。模型据此输出表达式、工具结果和解释。']],[92,CW-92])
http=next(e for e in ts['events'] if e['type']=='external_http')
code(http['method']+' '+http['url']+'\nHTTP '+str(http['http_status'])+'\n请求：'+json.dumps(http['request'],ensure_ascii=False)+'\n响应：'+json.dumps(http['response'],ensure_ascii=False))
picture('08-external-tool-result.png','图 3：左侧显示技能结果，右侧为独立 HTTP 计算器的真实响应。',width=445)
source('05-skill-builtin.json',ts)

page();heading('06  MCP 接入后的模型参数')
p('<b>结论：</b>MCP 服务不会被直接塞进模型。客户端先取得 tools/list，再只将批准的 get-sum 映射为模型函数 mcp_add；聊天请求在常规参数上新增 tools 和首轮 tool_choice。')
sub('实际发送给 LLM 的工具定义与选择参数')
code({'model':cm[0]['request']['model'],'tools':cm[0]['request']['tools'],'tool_choice':cm[0]['request'].get('tool_choice')})
sub('模型返回的 tool_calls（参数由模型生成）')
code(cm[0]['response']['choices'][0]['message']['tool_calls'])
sub('客户端转换出的真实 MCP JSON-RPC 请求')
rpc=next(e for e in tm['events'] if e['type']=='mcp_rpc' and e['request']['method']=='tools/call')
code(rpc['request'])
p('服务：@modelcontextprotocol/server-everything@2.0.1，Node.js 24，stdio。连接协商使用 2025-03-26 协议；首次连接执行 initialize 和 notifications/initialized，然后 tools/list。实际发现 16 个工具，但应用仅映射并允许 get-sum。','small')
source('07-mcp.json',tm)

page();heading('07  MCP 返回与第二次模型请求')
sub('MCP 服务实际返回')
code(rpc['response'])
sub('随后传回 LLM 的 tool 消息')
toolmsg=next(m for m in cm[1]['request']['messages'] if m['role']=='tool')
code(toolmsg)
p('第二次聊天请求仍包含模板、用户问题、assistant.tool_calls、上方 tool 消息和 tools；不再强制 tool_choice。模型最终回答：<b>'+escape(tm['answer'])+'</b>。')
picture('11-mcp-protocol-call.png','图 4：左侧是模型最终回答，右侧是实际 MCP tools/call 请求。',width=445)
p('MCP 进程没有继承百炼 API Key 或用户 JWT。应用只开放加法工具，其他 MCP 能力未映射或调用；这是应用层白名单，不是操作系统沙箱。模型提出其他工具名或不合法参数时由服务端拒绝。','small')
source('07-mcp.json',tm)

page();heading('08  验证结果、复现与边界')
sub('完成的验证')
table([['层次','结果'],['自动化测试','27 项通过：10 项身份/权限 + 9 项知识库 + 8 项平台功能；单元测试使用 mock，不冒充真实模型调用。'],['真实模型与工具','8 份完整对话记录：模板、历史、写作、知识问答、内置 Skill、上传 Skill、MCP、网页模板；HTTP 与 MCP 实际工具结果已核验。'],['浏览器','模板保存刷新、网页真实问答、上传 Skill、历史选择、退出清理均通过；2 种视口；无控制台错误。'],['权限回归','未登录 401，学生上传材料 403，跨班材料 404，他人 Trace/Skill 404，注销 Token 重放失败。']],[110,CW-110])
sub('本地复现')
code('Python 3.12+，Node.js 24+\npip install -r requirements.txt\nnpm ci --ignore-scripts\n# 从本机环境提供 DASHSCOPE_API_KEY，不写入仓库\n.\\start.ps1\n# 浏览器打开 http://127.0.0.1:8092/platform\npython -m unittest test_auth test_rag test_platform -v\npython verify_live.py  # 新建演示库，实际调用百炼并产生费用')
p('演示登录：teacher_a / teacherpass123（A 班教师）；student_a1 / studentpass123（A 班学生）。新建数据库时先运行 verify_live.py 导入合成材料。完整步骤与 B 班演示账号见 README。')
sub('当前范围与已知限制')
p('这是本机课程原型，保留 Flask 开发服务器、公开演示账号、最多三轮文本历史和 SQLite 向量存储。上传 Skill 仅支持约定 Markdown，不支持任意代码包；MCP 为固定示例服务与单工具白名单，不是通用 MCP 商店。生成内容需要人工核对，当前引用校验只验证编号，不自动证明事实受原文支持。')
p('调用记录会含问题和返回正文，只允许所属用户查询；公开证据仅来自本次合成样例。截图右侧是应用记录的真实 JSON，不是浏览器 DevTools 直接抓到的模型网络请求。系统未记录密钥请求头，也未公开数据库。','small')
p('MCP 预检查于 10 月 27 日运行，登记最近扫描为 10 月 15 日、身份未验证、D 级，建议先询问；经用户明确确认后接入且只开放加法。登记不构成安全认证或对安装版本的完整代码审计。','small')

page();heading('09  证据索引与参考资料')
rows=[['证据文件','对应验证 / LLM 轮数']]
for name in ['01-template.json','02-history.json','03-writing.json','04-knowledge.json','05-skill-builtin.json','06-skill-upload.json','07-mcp.json','08-ui-template.json']:
    tr=read(name);rows.append([name,tr['question']+'\n'+str(len(chats(tr)))+' 轮聊天模型请求'])
table(rows,[135,CW-135])
p('各 JSON 中 events[].request 与 events[].response 是实际请求/响应，包含模型 request_id、HTTP 状态、usage、消息数组和工具参数。provider 表示模型调用，external_http 表示独立 HTTP 工具，mcp_rpc 表示协议消息，tool_result 表示回填模型的工具结果。截图为实际页面，未经拼接或生成替换。','small')
sub('主要源码定位')
p('platform_api.py：run_turn 对话编排、Skill 加载与工具白名单；knowledge.py：provider_call 实际请求与 search 班级检索；mcp_client.py：discover_add 和 call_add；external_calculator.py：calculate；tracing.py：每轮记录隔离。','small')
sub('参考资料')
for title,url in [('百炼 Function Calling 官方文档','https://help.aliyun.com/zh/model-studio/qwen-function-calling'),('百炼兼容 Chat Completions API','https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions'),('MCP 官方 Everything 示例服务','https://github.com/modelcontextprotocol/servers/tree/main/src/everything'),('MCP 预检查记录','https://policylayer.com/tools/server-everything')]:
    p('<link href="'+url+'" color="#8c001a">'+title+'</link>','body');p(url,'small')
p('Git 项目：<link href="'+folder+'" color="#8c001a">本次阶段验收独立目录</link>。本报告结论以 2026 年 10 月 27 日保存的实际记录为准，后续再次运行会生成新的 request_id 和模型响应。','small')

def chrome(c,doc):
    c.setFont('CN',8);c.setFillColor(muted)
    c.drawString(46,H-30,'CAMPUSCLAW  /  个人项目阶段性验收')
    c.setStrokeColor(colors.HexColor('#dcd6d8'));c.line(46,36,W-46,36)
    c.drawString(46,23,'2026-10-27  ·  GitHub: JOKER20180713/internet-software-homework')
    c.drawRightString(W-46,23,str(doc.page))

doc=SimpleDocTemplate(str(FILE),pagesize=A4,leftMargin=46,rightMargin=46,topMargin=52,bottomMargin=48,title='CampusClaw 个人项目阶段性验收报告',author='JOKER20180713')
doc.build(story,onFirstPage=chrome,onLaterPages=chrome)
print(FILE)
