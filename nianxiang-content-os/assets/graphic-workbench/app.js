'use strict';
const original = structuredClone(window.WORKBENCH_DATA);
const storageKey = 'nianxiang-illustrated-workbench-v2-' + encodeURIComponent(original.id || location.pathname);
const $ = id => document.getElementById(id);
let state = structuredClone(original), storageAvailable = true, imageIndex = 0, toastTimer;
let pendingDraft = null;
let baseRevision = original.revision;
try {
  const saved = JSON.parse(localStorage.getItem(storageKey));
  if (saved && saved.workId === original.id && saved.draft) {
    if (saved.baseRevision === original.revision) restoreDraft(saved.draft);
    else if (saved.dirty) pendingDraft = saved;
  }
} catch { storageAvailable = false; }
function restoreDraft(draft) {
  if (typeof draft.body !== 'string' || !Array.isArray(draft.titles) || !draft.titles.every(t => typeof t.text === 'string') || !Array.isArray(draft.images) || !draft.images.every(i => original.images.some(o => o.id === i.id)) || new Set(draft.images.map(i => i.id)).size !== original.images.length || (draft.titles.length && (!Number.isInteger(draft.selectedTitle) || draft.selectedTitle < 0 || draft.selectedTitle >= draft.titles.length))) return false;
  state.body = draft.body;
  state.titles = draft.titles;
  state.selectedTitle = draft.selectedTitle;
  state.images = draft.images.map(i => structuredClone(original.images.find(o => o.id === i.id)));
  return true;
}
function dirty() { return JSON.stringify([state.body,state.titles,state.selectedTitle,state.images.map(i=>i.id)]) !== JSON.stringify([original.body,original.titles,original.selectedTitle,original.images.map(i=>i.id)]); }
function toast(message) {
  $('toast').textContent = message;
  $('toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.remove('show'), 2600);
}
function save() {
  try { localStorage.setItem(storageKey, JSON.stringify({workId:original.id,baseRevision,dirty:dirty() || baseRevision !== original.revision,draft:state})); storageAvailable = true; }
  catch { storageAvailable = false; }
  $('save-status').textContent = storageAvailable ? '已保存到本机' : '当前浏览器无法保存，请导出留存';
}
const wordCount = text => Array.from(text.replace(/\s/g, '')).length;
function count() { $('count').textContent = `${wordCount(state.body)} 字`; }
async function copy(text) {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
    else throw new Error('fallback');
    toast('已复制');
  } catch {
    const temp = document.createElement('textarea');
    temp.value = text; temp.style.position = 'fixed'; temp.style.opacity = '0';
    document.body.append(temp); temp.focus(); temp.select();
    const success = document.execCommand('copy'); temp.remove();
    toast(success ? '已复制' : '复制受浏览器限制，请手动选择文字复制');
  }
}
function renderTitles() {
  $('titles').replaceChildren();
  if (!state.titles.length) { $('titles').textContent = '暂无标题候选'; }
  state.titles.forEach((title, index) => {
    const row = document.createElement('div'); row.className = 'title-option' + (index === state.selectedTitle ? ' selected' : '');
    const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'chosen-title'; radio.checked = index === state.selectedTitle; radio.setAttribute('aria-label', `选用标题 ${index+1}：${title.text}`);
    const selectTitle = () => {
      if (state.selectedTitle === index) return;
      state.selectedTitle = index;
      for (const [i, card] of Array.from($('titles').children).entries()) {
        card.classList.toggle('selected', i === index);
        card.querySelector('input[type=radio]').checked = i === index;
      }
      save();
    };
    radio.addEventListener('change', selectTitle);
    row.addEventListener('click', selectTitle);
    const detail = document.createElement('div'); detail.className = 'title-detail';
    const input = document.createElement('input'); input.value = title.text; input.setAttribute('aria-label', `编辑标题 ${index+1}`);
    input.addEventListener('input', () => { state.titles[index].text = input.value; radio.setAttribute('aria-label', `选用标题 ${index+1}：${input.value}`); save(); });
    const origin = document.createElement('span'); origin.className = 'title-origin';
    const updateOrigin = () => { origin.textContent = state.titles[index].text !== original.titles[index].text ? '已编辑' : ''; };
    updateOrigin(); input.addEventListener('input', updateOrigin);
    const meta = document.createElement('div'); meta.className = 'title-meta';
    const type = document.createElement('span'); type.className = 'title-type'; type.textContent = title.type || '未分类';
    const length = document.createElement('span'); length.className = 'title-count'; length.setAttribute('aria-live', 'polite');
    const updateLength = () => { const n = Array.from(input.value).length; length.textContent = `${n} 字` + (n > 20 ? ' · 超过20字' : ''); length.classList.toggle('over-limit', n > 20); };
    updateLength(); input.addEventListener('input', updateLength);
    meta.append(type, length); detail.append(meta, input, origin); row.append(radio, detail);
    $('titles').append(row);
  });
}
function renderGallery() {
  $('gallery').replaceChildren();
  $('image-count').textContent = `${state.images.length} 张`;
  if (!state.images.length) { const empty = document.createElement('div'); empty.className = 'image-placeholder'; empty.setAttribute('role', 'img'); empty.setAttribute('aria-label', '配图占位，暂无配图'); const mark = document.createElement('span'); mark.className = 'placeholder-mark'; mark.textContent = '▧'; mark.setAttribute('aria-hidden', 'true'); const label = document.createElement('span'); label.textContent = '暂无配图'; empty.append(mark, label); $('gallery').append(empty); }
  state.images.forEach((item,index) => {
    const card = document.createElement('article'); card.className = 'image-card';
    const heading = document.createElement('div'); heading.className = 'image-top';
    const label = document.createElement('strong'); label.textContent = `0${index+1} / ${item.label}`;
    heading.append(label);
    const open = document.createElement('button'); open.className = 'image-open'; open.setAttribute('aria-label', `放大查看${item.label}`);
    const img = document.createElement('img'); img.src = item.path; img.alt = item.alt || item.label;
    const zoom = document.createElement('span'); zoom.className = 'zoom'; zoom.textContent = '放大 ↗'; open.append(img,zoom); open.addEventListener('click', () => showImage(index));
    const bottom = document.createElement('div'); bottom.className = 'image-bottom';
    const download = document.createElement('a'); download.href = item.path; download.download = item.path.split('/').pop(); download.textContent = '下载原图 ↓';
    const move = document.createElement('button'); move.className = 'order-button'; move.textContent = index === 0 ? '后移 →' : '← 前移'; move.setAttribute('aria-label', `将${item.label}${index === 0 ? '后移' : '前移'}`);
    move.disabled = state.images.length < 2;
    move.addEventListener('click', () => { const target = index === 0 ? 1 : index-1; [state.images[index],state.images[target]] = [state.images[target],state.images[index]]; renderGallery(); save(); toast('图组顺序已调整'); });
    bottom.append(download,move); card.append(heading,open,bottom); $('gallery').append(card);
  });
}
function showImage(index) {
  imageIndex = (index + state.images.length) % state.images.length;
  const item = state.images[imageIndex];
  $('large-image').src = item.path; $('large-image').alt = item.label;
  $('image-label').textContent = item.label;
  $('image-position').textContent = `${imageIndex+1} / ${state.images.length}`;
  $('download-large').href = item.path; $('download-large').download = item.path.split('/').pop();
  if (!$('lightbox').open) $('lightbox').showModal();
}
function selection() {
  return {schema_version:'nianxiang.graphic-workbench.selection.v1', work_id:original.id, base_revision:baseRevision, source:original.source || null, source_work:original.id || null, creation:original.creation || null, status:'local_draft', exported_at:new Date().toISOString(), body:state.body, selected_title:(state.titles[state.selectedTitle]?.text || ''), title_candidates:state.titles, images:state.images.map((i,index) => ({...i,order:index+1})), note:'标题编辑不改变图中文字；本文件为当前草稿。'};
}
$('body').value = state.body; count(); renderTitles(); renderGallery();
$('save-status').textContent = storageAvailable ? '本地草稿 · 自动保存' : '请导出留存当前草稿';
$('body').addEventListener('input', e => { state.body = e.target.value; count(); save(); });
$('copy-body').addEventListener('click', () => copy(state.body));
$('copy-title').addEventListener('click', () => copy((state.titles[state.selectedTitle]?.text || '')));
$('handoff').addEventListener('click', () => copy('阿响，请基于这份工作台当前选择继续共创。以下是当前正文、标题和配图清单，请按我的后续要求修改。\n\n'+JSON.stringify(selection(),null,2)));
$('export').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(selection(),null,2)], {type:'application/json;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = '图文工作台当前版本.json'; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000); toast('已导出当前文案、标题与图片清单');
});
$('reset').addEventListener('click', () => {
  if (!window.confirm('恢复本次载入内容？当前浏览器里的文案、标题与顺序修改会被替换。')) return;
  baseRevision = original.revision; state = structuredClone(original); $('body').value = state.body; count(); renderTitles(); renderGallery(); save(); toast('已恢复载入内容');
});
$('close-dialog').addEventListener('click', () => $('lightbox').close());
$('previous').addEventListener('click', () => showImage(imageIndex-1));
$('next').addEventListener('click', () => showImage(imageIndex+1));
$('lightbox').addEventListener('click', e => { if (e.target === $('lightbox')) { const r = e.target.getBoundingClientRect(); if(e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) e.target.close(); } });
document.addEventListener('keydown', e => { if (!$('lightbox').open) return; if(e.key === 'ArrowLeft') showImage(imageIndex-1); if(e.key === 'ArrowRight') showImage(imageIndex+1); });

const fontStorageKey = 'nianxiang-workbench-body-font-size';
let bodyFontSize = 16;
try { const storedSize = Number(localStorage.getItem(fontStorageKey)); if (Number.isInteger(storedSize) && storedSize >= 12 && storedSize <= 24) bodyFontSize = storedSize; } catch {}
function applyFontSize() {
  $('body').style.fontSize = bodyFontSize + 'px';
  $('font-size').textContent = bodyFontSize + 'px';
  $('font-smaller').disabled = bodyFontSize <= 12;
  $('font-larger').disabled = bodyFontSize >= 24;
  try { localStorage.setItem(fontStorageKey, String(bodyFontSize)); } catch {}
}
$('font-smaller').addEventListener('click', () => { bodyFontSize = Math.max(12, bodyFontSize - 2); applyFontSize(); });
$('font-larger').addEventListener('click', () => { bodyFontSize = Math.min(24, bodyFontSize + 2); applyFontSize(); });
$('font-reset').addEventListener('click', () => { bodyFontSize = 16; applyFontSize(); });
applyFontSize();

function safeDocumentUrl(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; }
}
function documentLink(label, url) {
  const href = safeDocumentUrl(url);
  if (!href) return null;
  const link = document.createElement('a'); link.textContent = label + ' ↗'; link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer'; return link;
}
function renderCreationNav() {
  const creation = original.creation || {};
  const topic = creation.topic || {};
  const hasTopic = typeof topic.title === 'string' && topic.title.trim();
  $('topic-details').hidden = !hasTopic;
  $('topic-name').textContent = hasTopic ? topic.title : '';
  $('topic-context').replaceChildren();
  for (const [key, label] of [['angle', '一句话切口'], ['valueBasis', '价值依据'], ['sourceClues', '来源线索'], ['judgment', '核心判断'], ['readerValue', '读者价值']]) {
    if (typeof topic[key] !== 'string' || !topic[key].trim()) continue;
    const row = document.createElement('p'); const heading = document.createElement('strong'); heading.textContent = label;
    const text = document.createElement('span'); text.textContent = topic[key]; row.append(heading, text); $('topic-context').append(row);
  }
  for (const source of topic.sources || []) {
    const link = documentLink(source.label || '来源素材', source.url);
    if (link) $('topic-context').append(link);
  }
  $('creation-links').replaceChildren();
  for (const [key, label] of [['topicMap', '选题地图'], ['draftBatch', '批量初稿']]) {
    const item = creation[key]; if (!item) continue;
    const link = documentLink(label, item.url);
    if (link) { if (item.title) link.title = item.title; $('creation-links').append(link); }
  }
  const hasLinks = $('creation-links').children.length > 0;
  $('creation-links').hidden = !hasLinks;
  $('creation-nav').hidden = !hasTopic && !hasLinks;
}
renderCreationNav();

const fixedHeader = document.querySelector('.fixed-header');
if (fixedHeader) {
  let scrollUpdatePending = false;
  const updateHeader = () => {
    const isCompact = fixedHeader.classList.contains('is-scrolled');
    if (window.scrollY > 56) fixedHeader.classList.add('is-scrolled');
    else if (window.scrollY <= 8 && isCompact) fixedHeader.classList.remove('is-scrolled');
    scrollUpdatePending = false;
  };
  window.addEventListener('scroll', () => {
    if (!scrollUpdatePending) { scrollUpdatePending = true; requestAnimationFrame(updateHeader); }
  }, {passive:true});
  updateHeader();
}

function downloadJson(value, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}));
  const link = document.createElement('a'); link.href=url; link.download=name; document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
if (pendingDraft) {
  const dialog = $('version-conflict');
  dialog.addEventListener('cancel', e => e.preventDefault());
  let backedUp = false;
  $('conflict-export').addEventListener('click',()=>{downloadJson(pendingDraft,'工作台本机草稿备份.json');backedUp=true;});
  $('conflict-local').addEventListener('click',()=>{
    if (!restoreDraft(pendingDraft.draft)) { toast('图片或数据结构已变化，请导出草稿后在对话中合并'); return; }
    baseRevision = pendingDraft.baseRevision;
    $('body').value=state.body;count();renderTitles();renderGallery();save();dialog.close();
  });
  $('conflict-new').addEventListener('click',()=>{
    if (!backedUp) { downloadJson(pendingDraft,'工作台本机草稿备份.json'); backedUp=true; }
    baseRevision=original.revision; save();dialog.close();
  });
  dialog.showModal();
}
