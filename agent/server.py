import json
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from .db import Dataset, Run, Span, Thread, get_sessionmaker, init_db
from .runner import run_agent
from .tools import upload_dataset as _upload_dataset_tool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="data-analysis-agent", lifespan=lifespan)


def ok(data):
    return {"ok": True, "data": data}


def err(msg):
    return {"ok": False, "error": msg}


@app.get("/health")
async def health():
    return {"ok": True, "status": "alive"}


class RunIn(BaseModel):
    goal: str
    thread_id: str | None = None
    dataset_id: str | None = None


@app.post("/runs")
async def create_run(body: RunIn):
    try:
        result = await run_agent(body.goal, thread_id=body.thread_id, dataset_id=body.dataset_id)
        answer = result["answer"]
        # Detect chart spec and wrap it for the UI
        chart_spec = None
        if isinstance(answer, str) and answer.startswith("CHART_SPEC:"):
            chart_spec = json.loads(answer[len("CHART_SPEC:"):])
            answer = None
        return ok({
            "run_id": result["run_id"],
            "thread_id": result["thread_id"],
            "answer": answer,
            "chart_spec": chart_spec,
            "iterations": result["iterations"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "cost_usd": result["cost_usd"],
        })
    except Exception as e:
        return err(str(e))


@app.post("/runs/stream")
async def stream_run(body: RunIn):
    """SSE token stream — emits chunks then a final done event."""
    from .graph import build_graph
    from .llm import get_model
    from .runner import _build_system_prompt, _get_dataset_schema
    from langchain_core.messages import HumanMessage, SystemMessage

    async def gen():
        try:
            model = get_model()
            thread_id = body.thread_id or uuid.uuid4().hex
            dataset_schema = await _get_dataset_schema(body.dataset_id)
            system_prompt = _build_system_prompt(dataset_schema)
            from .runner import _load_thread_history
            history = await _load_thread_history(thread_id)
            graph = build_graph(model)
            run_id = uuid.uuid4().hex
            messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=body.goal)]
            state = {
                "messages": messages,
                "iterations": 0, "answer": None, "run_id": run_id,
            }
            config = {"recursion_limit": 50}

            async for ev in graph.astream_events(state, config=config, version="v2"):
                if ev["event"] == "on_chat_model_stream":
                    chunk = ev["data"]["chunk"]
                    tok = chunk.content
                    if isinstance(tok, list):
                        tok = "".join(p.get("text", "") for p in tok if isinstance(p, dict))
                    if tok:
                        yield f"data: {json.dumps({'token': tok})}\n\n"
                elif ev["event"] == "on_chain_end" and ev.get("name") == "finalize":
                    answer = ev["data"]["output"].get("answer", "")
                    chart_spec = None
                    if isinstance(answer, str) and answer.startswith("CHART_SPEC:"):
                        chart_spec = json.loads(answer[len("CHART_SPEC:"):])
                        answer = None
                    yield f"data: {json.dumps({'done': True, 'run_id': run_id, 'thread_id': thread_id, 'answer': answer, 'chart_spec': chart_spec})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/datasets/upload")
async def upload_dataset_endpoint(
    file: UploadFile = File(...),
    name: str = Form(default=""),
):
    """Multipart file upload — parse CSV/JSON and register as a dataset."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".json"}:
        return err(f"Unsupported file type '{suffix}'. Only .csv and .json are accepted.")

    dataset_name = name or Path(file.filename or "dataset").stem

    # Write to a temp file, call the tool, clean up
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = await _upload_dataset_tool.ainvoke({"file_path": tmp_path, "name": dataset_name})
    finally:
        os.unlink(tmp_path)

    if result.startswith("Error"):
        return err(result)

    # Parse dataset_id from the result string
    dataset_id = None
    for line in result.splitlines():
        if line.startswith("dataset_id:"):
            dataset_id = line.split(":", 1)[1].strip()
            break

    # Fetch full dataset info
    async with get_sessionmaker()() as s:
        ds = (await s.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()

    if ds is None:
        return err("Dataset created but could not be retrieved.")

    return ok({
        "dataset_id": ds.id,
        "name": ds.name,
        "table_name": ds.table_name,
        "row_count": ds.row_count,
        "schema": ds.schema_json,
        "file_type": ds.file_type,
    })


@app.get("/datasets")
async def list_datasets():
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().all()
    return ok([{
        "dataset_id": d.id,
        "name": d.name,
        "table_name": d.table_name,
        "row_count": d.row_count,
        "schema": d.schema_json,
        "file_type": d.file_type,
    } for d in rows])


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    async with get_sessionmaker()() as s:
        th = (await s.execute(select(Thread).where(Thread.id == thread_id))).scalar_one_or_none()
    if not th:
        return err("Thread not found")
    return ok({"thread_id": thread_id, "total_tokens": th.total_tokens, "total_cost_usd": th.total_cost_usd})


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return _app_html()


def _app_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Analysis Agent</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#f9fafb;height:100vh;display:flex;flex-direction:column}
#header{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#fff;border-bottom:1px solid #e5e7eb;font-size:13px;color:#6b7280}
#header strong{color:#111827}
#btn-new{background:none;border:1px solid #d1d5db;border-radius:6px;padding:3px 10px;cursor:pointer;font-size:12px;color:#6b7280}
#btn-new:hover{border-color:#ef4444;color:#ef4444}
#main{display:flex;flex:1;min-height:0}
#sidebar{width:280px;flex-shrink:0;border-right:1px solid #e5e7eb;background:#fff;display:flex;flex-direction:column;padding:12px;gap:12px;overflow-y:auto}
#sidebar h3{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#9ca3af}
#drop-zone{border:2px dashed #d1d5db;border-radius:8px;padding:20px;text-align:center;cursor:pointer;transition:border-color .2s,background .2s;font-size:13px;color:#6b7280}
#drop-zone.drag{border-color:#3b82f6;background:#eff6ff}
#drop-zone:hover{border-color:#93c5fd}
#drop-zone input{display:none}
#upload-status{font-size:12px;margin-top:6px}
#active-ds{background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:8px;font-size:12px;display:none}
#active-ds .ds-name{font-weight:600;color:#1d4ed8}
#active-ds .ds-meta{color:#3b82f6;margin-top:2px}
#ds-list{display:flex;flex-direction:column;gap:4px}
.ds-btn{text-align:left;background:none;border:1px solid #e5e7eb;border-radius:6px;padding:6px 8px;cursor:pointer;font-size:12px;color:#374151;width:100%}
.ds-btn.active{background:#eff6ff;border-color:#93c5fd;color:#1d4ed8}
.ds-btn:hover{border-color:#93c5fd}
#traces-link{margin-top:auto;padding-top:8px;border-top:1px solid #f3f4f6;font-size:12px}
#traces-link a{color:#3b82f6;text-decoration:none}
#traces-link a:hover{text-decoration:underline}
#chat{display:flex;flex-direction:column;flex:1;min-width:0}
#messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:82%;border-radius:12px;padding:10px 14px;font-size:14px;line-height:1.5}
.msg.user{align-self:flex-end;background:#2563eb;color:#fff;border-bottom-right-radius:3px}
.msg.agent{align-self:flex-start;background:#fff;border:1px solid #e5e7eb;box-shadow:0 1px 2px rgba(0,0,0,.05);border-bottom-left-radius:3px}
.msg.agent .msg-content{color:#111827}
.msg.agent .msg-content table{border-collapse:collapse;width:100%;margin:4px 0;font-size:13px}
.msg.agent .msg-content table th,.msg.agent .msg-content table td{border:1px solid #e5e7eb;padding:4px 8px;text-align:left}
.msg.agent .msg-content table th{background:#f9fafb;font-weight:600}
.msg.agent .msg-content pre{background:#f3f4f6;padding:8px;border-radius:4px;overflow-x:auto;font-size:12px}
.msg.agent .msg-content code{background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:12px}
.msg-meta{font-size:11px;color:#9ca3af;margin-top:6px}
.msg-meta a{color:#3b82f6;text-decoration:none}
.msg-meta a:hover{text-decoration:underline}
.chart-container{margin-top:8px;min-height:300px}
#empty{flex:1;display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:14px;text-align:center}
#input-bar{display:flex;gap:8px;padding:12px 16px;background:#fff;border-top:1px solid #e5e7eb}
#goal-input{flex:1;border:1px solid #d1d5db;border-radius:8px;padding:8px 12px;font-size:14px;outline:none;resize:none;line-height:1.4;min-height:40px;max-height:120px}
#goal-input:focus{border-color:#3b82f6;box-shadow:0 0 0 2px rgba(59,130,246,.15)}
#send-btn{background:#2563eb;color:#fff;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;font-size:14px;font-weight:500;align-self:flex-end}
#send-btn:hover{background:#1d4ed8}
#send-btn:disabled{opacity:.5;cursor:not-allowed}
</style>
</head>
<body>
<div id="header">
  <span><strong id="hdr-dataset">No dataset</strong> &nbsp;·&nbsp; <span id="hdr-cost"></span></span>
  <button id="btn-new" onclick="newSession()">New session</button>
</div>
<div id="main">
  <div id="sidebar">
    <div>
      <h3>Upload Dataset</h3>
      <div id="drop-zone" onclick="document.getElementById('file-input').click()"
           ondragover="event.preventDefault();this.classList.add('drag')"
           ondragleave="this.classList.remove('drag')"
           ondrop="handleDrop(event)">
        <input id="file-input" type="file" accept=".csv,.json" onchange="handleFile(this.files[0])">
        Drop CSV / JSON here<br><span style="font-size:11px">or click to browse</span>
      </div>
      <div id="upload-status"></div>
    </div>
    <div id="active-ds-section" style="display:none">
      <h3>Active Dataset</h3>
      <div id="active-ds">
        <div class="ds-name" id="active-ds-name"></div>
        <div class="ds-meta" id="active-ds-meta"></div>
      </div>
    </div>
    <div id="all-ds-section" style="display:none">
      <h3>All Datasets</h3>
      <div id="ds-list"></div>
    </div>
    <div id="traces-link"><a href="/traces" target="_blank">View traces →</a></div>
  </div>
  <div id="chat">
    <div id="messages">
      <div id="empty">📊 Upload a CSV or JSON file, then ask questions in natural language.<br>
      <span style="font-size:12px">You can also request charts: "show revenue by region as a bar chart"</span></div>
    </div>
    <div id="input-bar">
      <textarea id="goal-input" placeholder="Upload a dataset first, then ask questions…" rows="1"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"
        oninput="autoResize(this)"></textarea>
      <button id="send-btn" onclick="sendMessage()">Send</button>
    </div>
  </div>
</div>
<script>
const API = '';
let threadId = lsGet('thread_id') || newId();
let activeDataset = null;
let allDatasets = [];
let totalCost = 0;
let totalTokens = 0;
let sending = false;

function lsGet(k){try{return localStorage.getItem(k)}catch{return null}}
function lsSet(k,v){try{localStorage.setItem(k,v)}catch{}}
function lsRemove(k){try{localStorage.removeItem(k)}catch{}}

function newId(){return Math.random().toString(36).slice(2)+Date.now().toString(36)}

function autoResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,120)+'px'}

function updateHeader(){
  const dsEl=document.getElementById('hdr-dataset');
  dsEl.textContent=activeDataset?'Dataset: '+activeDataset.name:'No dataset';
  const costEl=document.getElementById('hdr-cost');
  costEl.textContent=totalTokens>0?totalTokens.toLocaleString()+' tok · $'+totalCost.toFixed(5):'';
}

function setActiveDataset(ds){
  activeDataset=ds;
  lsSet('dataset_id',ds.dataset_id);
  document.getElementById('active-ds-section').style.display='';
  document.getElementById('active-ds').style.display='';
  document.getElementById('active-ds-name').textContent=ds.name;
  const cols=Object.keys((ds.schema&&ds.schema.columns)||{});
  document.getElementById('active-ds-meta').textContent=
    ds.row_count.toLocaleString()+' rows · '+cols.slice(0,4).join(', ')+(cols.length>4?'…':'');
  document.getElementById('goal-input').placeholder='Ask about '+ds.name+'…';
  renderDsList();
  updateHeader();
}

function renderDsList(){
  const list=document.getElementById('ds-list');
  if(allDatasets.length>1){
    document.getElementById('all-ds-section').style.display='';
    list.innerHTML=allDatasets.map(ds=>
      '<button class="ds-btn'+(activeDataset&&ds.dataset_id===activeDataset.dataset_id?' active':'')
      +'" onclick="setActiveDataset('+JSON.stringify(ds).replace(/"/g,'&quot;')+')">'
      +ds.name+' <span style="color:#9ca3af">('+ds.row_count+' rows)</span></button>'
    ).join('');
  }
}

function appendMessage(role,content,meta){
  const empty=document.getElementById('empty');
  if(empty)empty.remove();
  const msgs=document.getElementById('messages');
  const div=document.createElement('div');
  div.className='msg '+role;
  if(role==='user'){
    div.textContent=content;
  } else {
    const cd=document.createElement('div');
    cd.className='msg-content';
    if(content){cd.innerHTML=marked.parse(content)}
    div.appendChild(cd);
    if(meta){
      const m=document.createElement('div');
      m.className='msg-meta';
      m.innerHTML=(meta.runId?'<a href="/traces" target="_blank">trace</a> &nbsp;':'')
        +(meta.cost!=null?'$'+meta.cost.toFixed(5)+' · '+(meta.inputTokens+meta.outputTokens)+' tok':'');
      div.appendChild(m);
    }
  }
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
  return div;
}

function appendChart(spec){
  const msgs=document.getElementById('messages');
  const last=msgs.lastElementChild;
  const container=document.createElement('div');
  container.className='chart-container';
  last.querySelector('.msg-content').appendChild(container);
  Plotly.newPlot(container,spec.data,{...spec.layout,responsive:true});
}

async function handleFile(file){
  if(!file)return;
  const status=document.getElementById('upload-status');
  const dz=document.getElementById('drop-zone');
  dz.classList.remove('drag');
  status.style.color='#3b82f6';
  status.textContent='Uploading…';
  const form=new FormData();
  form.append('file',file);
  form.append('name',file.name.replace(/\\.[^.]+$/,''));
  try{
    const r=await fetch(API+'/datasets/upload',{method:'POST',body:form});
    const body=await r.json();
    if(!body.ok)throw new Error(body.error||'Upload failed');
    const ds=body.data;
    allDatasets.unshift(ds);
    setActiveDataset(ds);
    status.style.color='#16a34a';
    status.textContent='Uploaded: '+ds.name;
    const cols=Object.keys((ds.schema&&ds.schema.columns)||{});
    appendMessage('agent',
      '**'+ds.name+'** loaded — '+ds.row_count.toLocaleString()+' rows.\\n\\n'
      +'Columns: '+cols.join(', ')+'\\n\\nYou can now ask questions about this dataset.');
  }catch(e){
    status.style.color='#ef4444';
    status.textContent='Error: '+e.message;
  }
}

function handleDrop(e){
  e.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag');
  handleFile(e.dataTransfer.files[0]);
}

async function sendMessage(){
  const input=document.getElementById('goal-input');
  const goal=input.value.trim();
  if(!goal||sending)return;
  input.value='';
  input.style.height='auto';
  sending=true;
  document.getElementById('send-btn').disabled=true;

  appendMessage('user',goal);

  const body={goal,thread_id:threadId};
  if(activeDataset)body.dataset_id=activeDataset.dataset_id;

  const agentDiv=appendMessage('agent','…');
  try{
    const r=await fetch(API+'/runs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const json=await r.json();
    if(!json.ok)throw new Error(json.error||'Request failed');
    const d=json.data;
    const cd=agentDiv.querySelector('.msg-content');
    cd.innerHTML='';
    if(d.answer)cd.innerHTML=marked.parse(d.answer);
    if(d.chart_spec)appendChart(d.chart_spec);
    const meta=agentDiv.querySelector('.msg-meta')||document.createElement('div');
    meta.className='msg-meta';
    meta.innerHTML='<a href="/traces" target="_blank">trace</a> &nbsp;'
      +(d.cost_usd!=null?'$'+d.cost_usd.toFixed(5)+' · '+(d.input_tokens+d.output_tokens)+' tok':'');
    agentDiv.appendChild(meta);
    totalCost+=(d.cost_usd||0);
    totalTokens+=((d.input_tokens||0)+(d.output_tokens||0));
    updateHeader();
  }catch(e){
    agentDiv.querySelector('.msg-content').innerHTML='<span style="color:#ef4444">Error: '+e.message+'</span>';
  }finally{
    sending=false;
    document.getElementById('send-btn').disabled=false;
    input.focus();
  }
}

function newSession(){
  threadId=newId();
  lsSet('thread_id',threadId);
  lsRemove('dataset_id');
  activeDataset=null;
  totalCost=0;totalTokens=0;
  document.getElementById('messages').innerHTML=
    '<div id="empty" style="flex:1;display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:14px;text-align:center">'
    +'📊 Upload a CSV or JSON file, then ask questions in natural language.</div>';
  document.getElementById('active-ds-section').style.display='none';
  document.getElementById('goal-input').placeholder='Upload a dataset first, then ask questions…';
  updateHeader();
}

// Init: restore session
(async()=>{
  lsSet('thread_id',threadId);
  const did=lsGet('dataset_id');
  try{
    const r=await fetch(API+'/datasets');
    const body=await r.json();
    if(!body.ok)return;
    allDatasets=body.data||[];
    if(did){const found=allDatasets.find(d=>d.dataset_id===did);if(found)setActiveDataset(found);}
    renderDsList();
  }catch{}
  try{
    const r=await fetch(API+'/threads/'+threadId);
    const body=await r.json();
    if(body.ok){totalTokens=body.data.total_tokens||0;totalCost=body.data.total_cost_usd||0;updateHeader();}
  }catch{}
})();
</script>
</body>
</html>"""


KIND_COLOR = {"INTERNAL": "#6b7280", "LLM": "#2563eb", "TOOL": "#16a34a"}


def _esc(x) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _traces_html() -> str:
    async with get_sessionmaker()() as s:
        runs = (await s.execute(select(Run).order_by(Run.created_at.desc()))).scalars().all()
        spans = (await s.execute(select(Span).order_by(Span.start_ms))).scalars().all()
    by_run: dict[str, list] = {}
    for sp in spans:
        by_run.setdefault(sp.run_id, []).append(sp)
    rows = []
    for r in runs:
        rspans = by_run.get(r.id, [])
        maxd = max((sp.duration_ms for sp in rspans), default=1) or 1
        cost_str = f"${r.cost_usd:.4f}" if r.cost_usd else ""
        rows.append(f"<h2>{_esc(r.goal)} <small>[{_esc(r.status)}] · {len(rspans)} spans · {cost_str}</small></h2>")
        for sp in rspans:
            color = KIND_COLOR.get(sp.kind, "#6b7280")
            bar = max(2, int(200 * sp.duration_ms / maxd))
            err_attr = sp.attributes.get("error") if isinstance(sp.attributes, dict) else None
            err_html = f"<div style='color:#dc2626'>{_esc(err_attr)}</div>" if err_attr else ""
            rows.append(
                f"<div style='margin:4px 0'>"
                f"<span style='background:{color};color:#fff;padding:1px 6px;border-radius:4px'>{_esc(sp.kind)}</span> "
                f"<b>{_esc(sp.name)}</b> "
                f"<span style='display:inline-block;height:8px;width:{bar}px;background:{color};vertical-align:middle'></span> "
                f"{sp.duration_ms}ms"
                f"<pre style='margin:2px 0;color:#374151'>{_esc(sp.attributes)}</pre>{err_html}</div>"
            )
    body = "".join(rows) or "<p>No runs yet. POST a goal to /runs.</p>"
    return f"<html><body style='font-family:system-ui;max-width:900px;margin:2rem auto'><h1>Traces</h1>{body}</body></html>"


@app.get("/traces", response_class=HTMLResponse)
async def traces():
    return await _traces_html()
