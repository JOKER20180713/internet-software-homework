"""Minimal bounded MCP stdio client; only the approved get-sum tool is exposed."""
import atexit
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tracing

ROOT = Path(__file__).resolve().parent
LOCK = threading.RLock()
_client = None

class Client:
    def __init__(self):
        # The MCP subprocess receives no cloud key or user token.
        env = {k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','TEMP','TMP','COMSPEC','PATHEXT'}}
        self.process = subprocess.Popen([os.environ.get('MCP_NODE','node'),str(ROOT/'node_modules/@modelcontextprotocol/server-everything/dist/index.js'),'stdio'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',
            env=env,cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.inbox=queue.Queue()
        self.sequence=0
        threading.Thread(target=self.reader,daemon=True).start()
        self.identity=self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},
            'clientInfo':{'name':'campusclaw-review','version':'1.0.0'}})
        self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
    def reader(self):
        for line in self.process.stdout:
            try: self.inbox.put(json.loads(line))
            except ValueError: continue
        self.inbox.put({'closed':True})
    def send(self,payload):
        self.process.stdin.write(json.dumps(payload,ensure_ascii=False)+'\n')
        self.process.stdin.flush()
    def rpc(self,method,params):
        self.sequence+=1
        payload={'jsonrpc':'2.0','id':self.sequence,'method':method,'params':params}
        self.send(payload)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            try: response=self.inbox.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty: break
            if response.get('closed'): raise RuntimeError('MCP 服务已退出，请检查 Node 版本和 npm ci')
            if response.get('id')!=self.sequence: continue
            tracing.record({'type':'mcp_rpc','request':payload,'response':response})
            if 'error' in response: raise RuntimeError('MCP 调用失败')
            return response['result']
        self.process.terminate()
        raise RuntimeError('MCP 请求超时')
    def close(self):
        if self.process.poll() is None: self.process.terminate()

def client():
    global _client
    if _client is None or _client.process.poll() is not None:
        _client=Client()
        atexit.register(_client.close)
    return _client

def discover_add():
    with LOCK:
        c=client()
        listing=c.rpc('tools/list',{})
        tool=next((t for t in listing['tools'] if t['name']=='get-sum'),None)
        if tool is None: raise RuntimeError('MCP 未提供已批准的 get-sum 工具')
        # Map only the allowed schema, not other tools or server instructions.
        schema=tool['inputSchema']
        schema={k:v for k,v in schema.items() if k!='$schema'}
        mapped={'type':'function','function':{'name':'mcp_add','description':'通过 MCP get-sum 工具计算两个数字的和。','parameters':schema}}
        tracing.record({'type':'mcp_mapping','server':c.identity,'allowed':['get-sum'],'exposed_to_llm':mapped})
        return mapped

def call_add(args):
    if set(args)!={'a','b'} or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e12 for v in args.values()):
        raise ValueError('MCP 加法参数必须是两个有限数值')
    with LOCK: return client().rpc('tools/call',{'name':'get-sum','arguments':args})
