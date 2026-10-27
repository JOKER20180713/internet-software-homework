const knowledgeStyle = document.createElement('style');
knowledgeStyle.textContent = `
.knowledge{max-width:1280px;margin:32px auto;padding:0 28px 36px}.knowledge h1{font-size:30px;margin:0 0 4px}.knowledge-head{display:flex;justify-content:space-between;align-items:center;gap:12px}.knowledge-tabs{display:flex;gap:12px;margin:24px 0 14px}.knowledge-tabs button{min-width:140px;padding:11px}.knowledge p{margin:12px 0}.question-form{display:flex;gap:12px;margin:24px 0}.question-form input{flex:1;min-width:0;background:white}.question-form button{flex-shrink:0}.question-bubble{background:#f0e3e6;border-radius:16px;padding:14px 20px;margin:24px 0 22px auto;max-width:80%;width:fit-content}.answer-card{padding:26px 30px}.answer-text{font-size:21px;white-space:pre-wrap;line-height:1.8}.source-card{border-top:1px solid #eee;margin-top:20px;padding-top:16px}.source-heading{font-weight:700;font-size:17px}.source-meta{color:#777;font-size:14px}.source-text{font-size:16px;white-space:pre-wrap;line-height:1.9;margin:12px 0}.source-card button{font-size:14px}.status{min-height:26px;color:#777}.knowledge select{padding:8px;border:1px solid #ddd;border-radius:8px;background:white;font:inherit}.provenance{margin-top:20px}.provenance pre{font:16px/1.8 "Microsoft YaHei",sans-serif;white-space:pre-wrap;overflow-wrap:anywhere}.model-note{color:#888;font-size:13px;margin-top:16px}.knowledge-intro{color:#777;line-height:1.9}@media(max-width:700px){.knowledge{padding:0 16px;margin-top:20px}.knowledge h1{font-size:23px}.answer-card{padding:18px}.question-form{flex-wrap:wrap}.question-form input{flex-basis:100%}.answer-text{font-size:18px}.knowledge-tabs button{min-width:120px}.knowledge-head{align-items:flex-start}.source-heading{font-size:16px}}
`;
document.head.append(knowledgeStyle);
const knowledgeSection = document.createElement('main');
knowledgeSection.id = 'knowledge';
knowledgeSection.className = 'knowledge';
knowledgeSection.hidden = true;
knowledgeSection.innerHTML = `
<div class="knowledge-head"><div><h1 id="knowledge-title"></h1><div id="knowledge-user" class="hint"></div></div><button id="back-materials">返回材料</button></div>
<div class="knowledge-tabs"><button id="search-tab">知识检索</button><button id="ask-tab" class="primary">知识问答</button></div>
<p class="knowledge-intro" id="knowledge-intro">每个问题先在本班资料中检索，取前 4 条相关片段生成回答，并标注引用来源。没有检索命中时直接提示资料中未找到相关内容。</p>
<form id="question-form" class="question-form"><label for="question" hidden>输入问题</label><input id="question" placeholder="请输入与本班资料有关的问题…" maxlength="200" required autocomplete="off"><select id="search-mode" aria-label="检索模式" hidden><option value="hybrid">混合检索</option><option value="keyword">关键词检索</option><option value="vector">向量检索</option></select><button class="primary" id="send-question">发送问题</button></form>
<div id="knowledge-status" class="status" role="status"></div><div id="question-bubble" class="question-bubble" hidden></div>
<article id="answer-card" class="card answer-card" hidden><div id="answer-label" class="hint">依据回答</div><div id="answer-text" class="answer-text"></div><div id="sources"></div><div id="model-note" class="model-note"></div></article>
<article id="provenance" class="card provenance" hidden><h2 id="provenance-title"></h2><pre id="provenance-body"></pre></article>
`;
document.body.insertBefore(knowledgeSection, $('notice'));
let knowledgeMode = 'ask', queryVersion = 0;

function clearKnowledge() {
  queryVersion++;
  knowledgeSection.hidden = true;
  $('answer-card').hidden = true;
  $('sources').replaceChildren();
  $('answer-text').textContent = '';
  $('question').value = '';
  $('question-bubble').hidden = true;
  $('provenance').hidden = true;
  $('provenance-body').replaceChildren();
  $('knowledge-status').textContent = '';
  $('send-question').disabled = false;
}
window.clearKnowledge = clearKnowledge;
$('knowledge-link').onclick = () => {
  if (!user) return;
  $('home').hidden = true;
  knowledgeSection.hidden = false;
  $('knowledge-title').textContent = user.class_code + ' 班知识问答';
  $('knowledge-user').textContent = user.username + ' · ' + (user.role === 'teacher' ? '教师' : '学生');
};
$('back-materials').onclick = () => { clearKnowledge(); if (user) $('home').hidden = false; };
function mode(value) {
  queryVersion++;
  knowledgeMode = value;
  $('ask-tab').classList.toggle('primary', value === 'ask');
  $('search-tab').classList.toggle('primary', value === 'search');
  $('search-mode').hidden = value === 'ask';
  $('send-question').textContent = value === 'ask' ? '发送问题' : '检索';
  $('send-question').disabled = false;
  $('answer-card').hidden = true;
  $('provenance').hidden = true;
  $('knowledge-status').textContent = '';
}
$('ask-tab').onclick = () => mode('ask');
$('search-tab').onclick = () => mode('search');

async function showSource(hit, version, identity) {
  $('provenance').hidden = true;
  $('provenance-body').replaceChildren();
  try {
    const data = (await api('/api/materials/' + hit.material_id)).material;
    if (!user || version !== queryVersion || identity !== identityVersion) return;
    const chars = Array.from(data.body_text);
    if (chars.slice(hit.start_offset, hit.end_offset).join('') !== hit.snippet) throw Error('来源内容已变更，请重新检索');
    $('provenance-title').textContent = data.title;
    const highlight = document.createElement('mark');
    highlight.textContent = hit.snippet;
    $('provenance-body').append(document.createTextNode(chars.slice(0, hit.start_offset).join('')),
      highlight, document.createTextNode(chars.slice(hit.end_offset).join('')));
    $('provenance').hidden = false;
    $('provenance').scrollIntoView({behavior:'smooth', block:'start'});
  } catch (e) { if (version === queryVersion && identity === identityVersion) notice(e.message); }
}

$('question-form').onsubmit = async event => {
  event.preventDefault();
  const q = $('question').value.trim();
  if (!q || !user) return;
  const version = ++queryVersion, identity = identityVersion, thisMode = knowledgeMode;
  $('question-bubble').textContent = q;
  $('question-bubble').hidden = false;
  $('answer-card').hidden = true;
  $('provenance').hidden = true;
  $('provenance-body').replaceChildren();
  $('sources').replaceChildren();
  $('send-question').disabled = true;
  $('knowledge-status').textContent = thisMode === 'ask' ? '正在检索本班资料并生成回答…' : '正在检索本班资料…';
  try {
    const result = await api('/api/' + thisMode, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({q, mode:$('search-mode').value, limit:4})});
    if (!user || version !== queryVersion || identity !== identityVersion) return;
    const hits = result.sources || result.hits || [];
    $('answer-label').textContent = thisMode === 'ask' ? '依据回答' : '检索结果';
    $('answer-text').textContent = result.answer || (hits.length ? '找到 ' + hits.length + ' 条本班资料片段' : '资料中未找到相关内容。');
    for (const [index, hit] of hits.entries()) {
      const card = document.createElement('section'); card.className = 'source-card';
      const heading = document.createElement('div'); heading.className = 'source-heading';
      heading.textContent = '[' + (hit.citation || index + 1) + '] ' + hit.class_code + ' 班 · ' + hit.material_title;
      const position = document.createElement('div'); position.className = 'source-meta';
      position.textContent = '切片 ' + hit.chunk_index + ' · 字符偏移 ' + hit.start_offset + '–' + hit.end_offset;
      const text = document.createElement('div'); text.className = 'source-text'; text.textContent = hit.snippet;
      const button = document.createElement('button'); button.textContent = '查看来源原文';
      button.onclick = () => showSource(hit, version, identity);
      card.append(heading, position, text, button); $('sources').append(card);
    }
    $('model-note').textContent = result.model_called ? '回答由通义千问生成，请结合上方原文核对。' : '';
    $('answer-card').hidden = false;
    $('knowledge-status').textContent = '';
  } catch (e) {
    if (version === queryVersion && identity === identityVersion) $('knowledge-status').textContent = e.message;
  } finally {
    if (version === queryVersion && identity === identityVersion) $('send-question').disabled = false;
  }
};
