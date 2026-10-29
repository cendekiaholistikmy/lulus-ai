<script>
  import { onMount } from 'svelte';
  import { House, FileText, Sparkles, Upload, LogOut, Download, CircleCheck, CircleAlert, Search, LoaderCircle, ShieldCheck, Trash2, ArrowRight, RotateCw, Send } from '@lucide/svelte';

  const NUMERIC = new Set(['decimal', 'integer', 'nonNegativeInteger', 'positiveInteger', 'float', 'double', 'int', 'long', 'short', 'nonPositiveInteger', 'negativeInteger']);
  const SOURCE_LABEL = { regex: 'Auto', ai: 'Auto', manual: 'Edited', taxonomy: 'Default' };
  const TITLES = { dashboard: 'New filing', form: 'Filing', assistant: 'Assistant', library: 'Library' };
  const CHIPS = ['What is missing?', 'Why is it invalid?', 'Where is the registration number?'];

  let signedIn = $state(false);
  let email = $state('demo@lulus.ai');
  let password = $state('demo-password');
  let tab = $state('dashboard');
  let library = $state([]);

  let entries = $state({ EA7: 'EA7', AR1965: 'AR1965' });
  let entry = $state('EA7');
  let file = $state(null);
  let pdfUrl = $state('');
  let showPreview = $state(true);
  let formPurpose = $state('');
  let formInfo = $state(null);
  let progress = $state('');
  let busy = $state(false);
  let notice = $state({ text: '', kind: 'ok' });

  let fields = $state([]);
  let values = $state({});
  let sources = $state({});
  let errors = $state({});
  let ocrText = $state('');
  let pageData = $state([]);
  let entityId = $state('');
  let period = $state({ start: '', end: '' });
  let result = $state(null);
  let validating = $state(false);
  let search = $state('');
  let onlyMissing = $state(false);

  let question = $state('');
  let answer = $state('');
  let friendlyErrors = $state('');
  let chatBusy = $state(false);
  let chatError = $state('');

  const filled = (f) => values[f.id] !== undefined && values[f.id] !== '';
  let missing = $derived(fields.filter((f) => !filled(f)));
  let doneCount = $derived(fields.length - missing.length);
  let percent = $derived(fields.length ? Math.round((doneCount / fields.length) * 100) : 0);
  let errorCount = $derived(Object.keys(errors).length);
  let shown = $derived(fields.filter((f) =>
    (!onlyMissing || !filled(f)) && (!search.trim() || f.label.toLowerCase().includes(search.trim().toLowerCase()))));
  let suggestedId = $derived(fields.find((f) => /registration\s*(number|no)/i.test(f.label) && filled(f))?.id);

  function say(text, kind = 'ok') { notice = { text, kind }; }

  async function api(path, body) {
    const response = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error ?? `Request failed (${response.status})`);
    return data;
  }

  const KEY = 'lulus.draft.v1';
  function save() { try { localStorage.setItem(KEY, JSON.stringify({ entry, values, sources, entityId, period, ocrText })); } catch {} }
  $effect(() => { if (fields.length) save(); });

  onMount(() => {
    try {
      const d = JSON.parse(localStorage.getItem(KEY) ?? 'null');
      if (d) { entry = d.entry ?? entry; values = d.values ?? {}; sources = d.sources ?? {}; entityId = d.entityId ?? ''; period = d.period ?? period; ocrText = d.ocrText ?? ''; }
      library = JSON.parse(localStorage.getItem('lulus.library.v1') ?? '[]');
    } catch {}
  });

  async function enter() {
    signedIn = true;
    try { entries = (await api('/api/mbrs', { cmd: 'entries' })).entries; if (!entries[entry]) entry = Object.keys(entries)[0]; } catch {}
    if (Object.keys(values).length) { try { await loadForm(); } catch {} }
  }

  async function loadForm() {
    const form = await api('/api/mbrs', { cmd: 'form', entry });
    fields = form.fields;
    formInfo = { key: form.key, desc: form.desc, fieldCount: form.fields.length };
    for (const [id, v] of Object.entries(form.defaults ?? {})) if (!values[id]) { values[id] = v; sources[id] = 'taxonomy'; }
    try {
      formPurpose = (await api('/api/chat', { question: `What is the purpose of the ${entry} form? Explain in one short sentence for a Malaysian SSM filer.`, missing: [], values: {}, errors: {}, context: form.desc ?? entry })).answer ?? '';
    } catch { formPurpose = ''; }
  }

  function apply(found, source) {
    let n = 0;
    for (const [id, v] of Object.entries(found ?? {})) {
      if (sources[id] === 'manual' && values[id]) continue;
      values[id] = v; sources[id] = source; n++;
    }
    return n;
  }

  async function runExtract() {
    const data = await api('/api/mbrs', { cmd: 'extract', entry, text: ocrText, values: { ...values } });
    const n = apply(data.stage1, 'regex') + apply(data.stage2, 'ai');
    return `${data.note ?? `${n} field${n === 1 ? '' : 's'} reviewed.`}${Object.keys(data.invalid ?? {}).length ? ` · ${Object.keys(data.invalid).length} invalid suggestion${Object.keys(data.invalid).length === 1 ? '' : 's'} rejected.` : ''}`;
  }

  async function process() {
    if (!file || busy) return;
    busy = true; say(''); result = null; errors = {};
    try {
      progress = 'Reading document…';
      const body = new FormData(); body.append('file', file);
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
      pdfUrl = URL.createObjectURL(file);
      library = [{ name: file.name, entry, date: new Date().toISOString(), status: 'Uploaded' }, ...library.filter((x) => x.name !== file.name)].slice(0, 30);
      localStorage.setItem('lulus.library.v1', JSON.stringify(library));
      const response = await fetch('/api/ocr', { method: 'POST', body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error ?? 'Could not read the document.');
      ocrText = data.text;
      pageData = data.pageData ?? [];
      if (!ocrText.trim()) throw new Error('No text found in this document.');
      progress = 'Preparing form…';
      values = {}; sources = {};
      await loadForm();
      progress = 'Filling fields…';
      say(await runExtract());
      tab = 'form';
    } catch (error) { say(error.message, 'bad'); }
    finally { busy = false; progress = ''; }
  }

  async function refill() {
    if (busy || !ocrText) return;
    busy = true; progress = 'Filling…';
    try { say(await runExtract()); } catch (error) { say(error.message, 'bad'); }
    finally { busy = false; progress = ''; }
  }

  async function validate() {
    if (validating) return;
    validating = true; result = null; errors = {}; say('');
    try {
      const data = await api('/api/mbrs', { cmd: 'validate', entry, values: { ...values }, entity: { identifier: entityId || values[suggestedId] || '' }, period: { ...period } });
      errors = data.fieldErrors ?? {};
      result = data;
      // Preserve the taxonomy/Arelle wording exactly. These messages are the
      // authoritative validation rules and include the source formula when
      // one is available.
      friendlyErrors = [
        ...Object.entries(errors).map(([id, message]) => `${id}: ${message}`),
        ...(data.problems ?? []),
      ].join('\n');
      const bad = Object.keys(errors).length;
      if (bad) say(`${bad} invalid field${bad === 1 ? '' : 's'}.`, 'bad');
      else if (data.problems.length) say(`${data.problems.length} issue${data.problems.length === 1 ? '' : 's'} found.`, 'bad');
      else say('Valid. Ready to download.');
    } catch (error) { say(error.message, 'bad'); }
    finally { validating = false; }
  }

  function download() {
    if (!result?.xml) return;
    const url = URL.createObjectURL(new Blob([result.xml], { type: 'application/xml' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `${entry}.xml` });
    a.click(); URL.revokeObjectURL(url);
  }

  function edit(id) { sources[id] = 'manual'; if (errors[id]) { const { [id]: _, ...rest } = errors; errors = rest; } result = null; }
  function clearDraft() { values = {}; sources = {}; errors = {}; result = null; ocrText = ''; fields = []; try { localStorage.removeItem(KEY); } catch {} say('Draft cleared.'); }

  async function ask(text = question) {
    if (!text.trim() || chatBusy) return;
    question = text; chatBusy = true; chatError = ''; answer = '';
    const labelled = Object.fromEntries(fields.filter(filled).map((f) => [f.label, values[f.id]]));
    const errs = Object.fromEntries(Object.entries(errors).map(([id, e]) => [fields.find((f) => f.id === id)?.label ?? id, e]));
    try { answer = (await api('/api/chat', { question: text, missing: missing.map((f) => f.label), values: labelled, errors: errs, context: ocrText })).answer; }
    catch (error) { chatError = error.message; }
    finally { chatBusy = false; }
  }
</script>

<svelte:head><title>lulus.ai</title></svelte:head>

{#if !signedIn}
  <main class="login-shell"><section class="login-card"><div class="logo">l</div><h1>lulus.ai</h1>
    <form onsubmit={(event) => { event.preventDefault(); enter(); }}><label>Email<input type="email" bind:value={email} required /></label><label>Password<input type="password" bind:value={password} required /></label><button class="wide">Sign in <ArrowRight size={16} /></button></form></section></main>
{:else}
  <div class="app-shell">
    <aside class="sidebar"><div class="brand"><span class="logo small">l</span>lulus.ai</div>
      <nav>
        <button class:active={tab === 'dashboard'} onclick={() => (tab = 'dashboard')}><House size={16} /> Home</button>
        <button class:active={tab === 'form'} onclick={() => (tab = 'form')}><FileText size={16} /> Filing {#if errorCount}<b class="pill bad">{errorCount}</b>{/if}</button>
        <button class:active={tab === 'assistant'} onclick={() => (tab = 'assistant')}><Sparkles size={16} /> Assistant</button>
        <button class:active={tab === 'library'} onclick={() => (tab = 'library')}><FileText size={16} /> Library</button>
      </nav>
      <button class="signout" onclick={() => (signedIn = false)}><LogOut size={16} /> Sign out</button></aside>

    <main class="content">
      <header><h1>{TITLES[tab]}</h1></header>
      {#if notice.text}<p class="banner {notice.kind}" role="status">{#if notice.kind === 'bad'}<CircleAlert size={16} />{:else}<CircleCheck size={16} />{/if}{notice.text}</p>{/if}

      {#if tab === 'dashboard'}
        <section class="metrics"><div><small>Filled</small><strong>{fields.length ? `${doneCount}/${fields.length}` : '—'}</strong></div><div><small>To review</small><strong>{fields.length ? missing.length + errorCount : '—'}</strong></div><div><small>Status</small><strong>{result ? (result.xml && !result.problems.length ? 'Valid' : 'Issues') : '—'}</strong></div></section>
        <section class="card upload-card">
          <select bind:value={entry} onchange={() => loadForm().catch(() => {})} aria-label="Form type">{#each Object.keys(entries) as key}<option value={key}>{key}</option>{/each}</select>
          {#if formInfo}<div class="form-info"><div class="eyebrow">Selected form</div><h2>{formInfo.key}</h2><p>{formInfo.desc || formPurpose || 'This form is used to prepare an MBRS filing.'}</p><small>{formInfo.fieldCount} fields will be reviewed before submission.</small></div>{/if}
          <input type="file" accept="application/pdf" onchange={(event) => (file = event.currentTarget.files[0] ?? null)} />
          <div class="row"><button onclick={process} disabled={busy || !file}>{#if busy}<LoaderCircle size={16} class="spin" /> {progress}{:else}<Upload size={16} /> Upload{/if}</button>
            {#if fields.length}<button class="secondary" onclick={() => (tab = 'form')}>Open draft</button><button class="secondary" onclick={clearDraft}><Trash2 size={16} /> Clear</button>{/if}</div></section>

      {:else if tab === 'form'}
        {#if !fields.length}
          <section class="card"><p>Nothing here yet.</p><button onclick={() => (tab = 'dashboard')}><Upload size={16} /> Upload</button></section>
        {:else}
          <div class="filing-columns"><section class="card form-layout">
            <div class="form-pane">
            <div class="row pane-tools"><button class="secondary" onclick={() => (showPreview = !showPreview)}>{showPreview ? 'Hide PDF preview' : 'Show PDF preview'}</button></div>
            {#if formPurpose}<p class="purpose"><b>About this form:</b> {formPurpose}</p>{/if}
            <div class="progress" title="{percent}%"><span style="width:{percent}%"></span></div>
            <p class="meta">{doneCount} / {fields.length}{errorCount ? ` · ${errorCount} invalid` : ''}</p>
            <div class="row"><div class="search grow"><Search size={16} /><input placeholder="Search" bind:value={search} /></div><label class="check"><input type="checkbox" bind:checked={onlyMissing} />Missing only</label></div>
          <section class="card">
            {#each shown as f (f.id)}
              <div class="field" class:invalid={errors[f.id]}>
                <label for={f.id}>{f.label}{#if sources[f.id] && filled(f)}<b class="pill {sources[f.id]}">{SOURCE_LABEL[sources[f.id]]}</b>{/if}</label>
                {#if f.enum}
                  <select id={f.id} bind:value={values[f.id]} onchange={() => edit(f.id)}><option value="">—</option>{#each f.enum as o}<option value={o}>{o}</option>{/each}</select>
                {:else if f.textblock}
                  <textarea id={f.id} bind:value={values[f.id]} oninput={() => edit(f.id)}></textarea>
                {:else if f.base === 'date'}
                  <input id={f.id} type="date" bind:value={values[f.id]} oninput={() => edit(f.id)} />
                {:else}
                  <input id={f.id} inputmode={NUMERIC.has(f.base) ? 'decimal' : 'text'} bind:value={values[f.id]} oninput={() => edit(f.id)} />
                {/if}
                {#if errors[f.id]}<small class="error">{errors[f.id]}</small>{/if}
              </div>
            {:else}<p>No matches.</p>{/each}
          </section>
          <section class="card">
            <div class="grid">
              <label>Registration number<input bind:value={entityId} placeholder={suggestedId ? values[suggestedId] : ''} /></label>
              <label>Period start<input type="date" bind:value={period.start} /></label>
              <label>Period end<input type="date" bind:value={period.end} /></label>
            </div>
            <div class="actions"><button onclick={validate} disabled={validating}>{#if validating}<LoaderCircle size={16} class="spin" /> Checking…{:else}<ShieldCheck size={16} /> Validate{/if}</button>
              <button class="secondary" onclick={refill} disabled={busy || !ocrText}>{#if busy}<LoaderCircle size={16} class="spin" /> {progress}{:else}<RotateCw size={16} /> Refill{/if}</button>
              <button class="secondary" onclick={() => (tab = 'assistant')}><Sparkles size={16} /> Help</button>
              {#if result?.xml && !result.problems.length}<button class="good" onclick={download}><Download size={16} /> Download</button>{/if}</div>
            {#if result?.problems?.length}<ul class="problems">{#each result.problems as p}<li>{p}</li>{/each}</ul>{/if}
            {#if friendlyErrors}<div class="friendly-errors"><b>Taxonomy validation messages</b><p>{friendlyErrors}</p></div>{/if}
          </section>
          </div>
          </section>
          {#if showPreview && pdfUrl}<section class="card pdf-card"><div class="pdf-title">Document preview <button class="secondary" onclick={() => (showPreview = false)}>Hide preview</button></div><iframe title="Uploaded PDF preview" src={pdfUrl}></iframe></section>{/if}</div>
        {/if}

      {:else if tab === 'library'}
        <section class="card library-card"><p class="meta">Your previous uploads are stored on this device.</p>{#if library.length}<div class="library-list">{#each library as item}<button class="library-item" onclick={() => { entry = item.entry; tab = 'dashboard'; }}><span><b>{item.name}</b><small>{item.entry} · {new Date(item.date).toLocaleString()}</small></span><span class="pill">{item.status}</span></button>{/each}</div>{:else}<p>No uploads yet. Upload a filing to start your library.</p>{/if}</section>

      {:else}
        <section class="card assistant">
          <div class="chat-window">{#if answer}<div class="bubble bubble-ai"><small>lulus.ai</small>{answer}</div>{:else}<div class="empty-chat">Ask about missing fields, errors, or where to find information in your document.</div>{/if}</div>
          <div class="chips">{#each CHIPS as c}<button class="secondary" onclick={() => ask(c)} disabled={chatBusy}>{c}</button>{/each}</div>
          <div class="chat-composer"><textarea bind:value={question} placeholder="Type a message…" onkeydown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask(); }}></textarea><button class="fit" onclick={() => ask()} disabled={chatBusy || !question.trim()}>{#if chatBusy}<LoaderCircle size={16} class="spin" />{:else}<Send size={16} />{/if}</button></div>
          {#if chatError}<p class="error">{chatError}</p>{/if}</section>
      {/if}
    </main>
  </div>
{/if}

<style>
  :global(*) { box-sizing:border-box } :global(body) { margin:0; background:#f5f6f8; color:#14181f; font:14px Inter,system-ui,sans-serif }
  :global(button), :global(input), :global(select), :global(textarea) { font:inherit }
  :global(.spin) { animation:spin 1s linear infinite } @keyframes spin { to { transform:rotate(360deg) } }
  .login-shell { min-height:100vh; display:grid; place-items:center; padding:24px }
  .login-card,.card { background:#fff; border:1px solid #dfe2e8; border-radius:2px; padding:24px }
  .login-card { width:min(380px,100%) } .logo { width:44px;height:44px;display:grid;place-items:center;border-radius:2px;background:#14181f;color:#fff;font-size:24px;font-weight:800;margin-bottom:20px }.logo.small{width:30px;height:30px;font-size:16px;margin:0}
  h1{font-size:26px;margin:0 0 4px} p,small{color:#6b7280}
  form,label{display:grid;gap:6px} form{margin-top:20px;gap:14px} input,select,textarea{width:100%;border:1px solid #cfd3db;border-radius:2px;padding:10px;background:#fff;color:#14181f} textarea{min-height:100px;resize:vertical}
  input:focus-visible,select:focus-visible,textarea:focus-visible,button:focus-visible{outline:2px solid #14181f;outline-offset:1px}
  button{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:1px solid #14181f;border-radius:2px;padding:10px 14px;background:#14181f;color:#fff;cursor:pointer;font-weight:600}button:disabled{opacity:.4;cursor:default}.secondary{background:#fff;color:#14181f;border-color:#cfd3db}.good{background:#14794f;border-color:#14794f}.wide{width:100%}.fit{width:max-content}
  .app-shell{display:grid;grid-template-columns:210px minmax(0,1fr);min-height:100vh}.sidebar{background:#14181f;color:#c9ced8;padding:22px 12px;display:flex;flex-direction:column;gap:28px}.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:17px;color:#fff}.brand .logo{background:#fff;color:#14181f}.sidebar nav{display:grid;gap:4px}.sidebar nav button,.signout{background:transparent;border-color:transparent;justify-content:flex-start;color:#c9ced8;font-weight:500}.sidebar nav button.active,.sidebar nav button:hover,.signout:hover{background:#262c37;color:#fff}.signout{margin-top:auto}
  .content{width:100%;max-width:none;padding:28px clamp(20px,3vw,48px)}.content header{margin-bottom:22px}
  .metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}.metrics div{background:#fff;border:1px solid #dfe2e8;border-radius:2px;padding:16px}.metrics strong{display:block;font-size:20px;margin-top:6px}
  .card{margin-bottom:16px}.upload-card{display:grid;gap:12px}
  .filing-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,46%);gap:16px;align-items:start}.form-layout{display:block}.form-pane{min-width:0}.pane-tools{justify-content:flex-end}.form-info{margin:14px 0;padding:16px;background:#f5f6f8;border:1px solid #dfe2e8}.form-info h2{margin:4px 0;font-size:19px}.form-info p{margin:6px 0}.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#6b7280;font-weight:700}.pdf-card{padding:0;overflow:hidden;position:sticky;top:16px}.pdf-title{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;font-weight:700;border-bottom:1px solid #dfe2e8}.pdf-card iframe{display:block;width:100%;height:760px;border:0;background:#eef0f4}.friendly-errors{margin-top:16px;padding:12px;background:#fff8e8;border:1px solid #eed28a;color:#5d4700}.friendly-errors p{white-space:pre-wrap;color:#5d4700}.library-list{display:grid;gap:8px}.library-item{width:100%;display:flex;justify-content:space-between;text-align:left;background:#fff;color:#14181f;border:1px solid #dfe2e8}.library-item small{display:block;margin-top:4px}.chat-window{min-height:320px;padding:18px;background:#e9edef;border-radius:8px;display:flex;align-items:flex-end}.bubble{max-width:82%;padding:12px 14px;border-radius:4px 14px 14px 14px;background:#fff;box-shadow:0 1px 2px #0001;white-space:pre-wrap}.bubble small{display:block;color:#14794f;font-weight:700;margin-bottom:5px}.empty-chat{color:#6b7280;text-align:center;width:100%}.chat-composer{display:flex;gap:8px;align-items:flex-end}.chat-composer textarea{min-height:52px}.chat-composer button{height:52px}.library-card{max-width:760px}
  .banner{display:flex;align-items:center;gap:8px;border-radius:2px;padding:10px 12px;margin:0 0 16px}.banner.ok{background:#e4f4ec;color:#14794f}.banner.bad{background:#fbeaea;color:#b42323}
  .progress{height:6px;background:#e6e8ee;overflow:hidden}.progress span{display:block;height:100%;background:#14181f;transition:width .3s}.meta{margin:8px 0 14px;font-size:13px}
  .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.grow{flex:1}.search{position:relative;display:flex;align-items:center}.search :global(svg){position:absolute;left:10px;color:#6b7280}.search input{padding-left:34px}.check{display:flex;grid-auto-flow:column;align-items:center;gap:6px;white-space:nowrap}.check input{width:auto}
  .field{display:grid;gap:6px;padding:12px 0;border-bottom:1px solid #eceef3}.field:last-child{border:0}.field label{display:flex;align-items:center;gap:8px;font-weight:600}.field.invalid input,.field.invalid select,.field.invalid textarea{border-color:#d93b3b;background:#fff8f8}
  .pill{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:2px 6px;border-radius:2px;background:#e6e8ee;color:#555d6e}.pill.regex,.pill.ai{background:#e6ecf8;color:#2a4a9a}.pill.manual{background:#e4f4ec;color:#14794f}.pill.bad{background:#d93b3b;color:#fff;margin-left:6px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.actions{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}
  .problems{margin:16px 0 0;padding-left:18px;color:#b42323;font-size:13px;word-break:break-word}
  .assistant{max-width:640px;display:grid;gap:12px}.chips{display:flex;gap:8px;flex-wrap:wrap}.chips button{font-size:12px;padding:6px 10px}.answer{white-space:pre-wrap;background:#f5f6f8;border:1px solid #dfe2e8;border-radius:2px;padding:14px}.error{color:#c92a2a;margin:0}
  @media(max-width:900px){.filing-columns{grid-template-columns:1fr}.pdf-card{position:static}.pdf-card iframe{height:520px}}
  @media(max-width:760px){.app-shell{grid-template-columns:1fr}.sidebar{gap:14px}.content{padding:22px 16px}.metrics,.grid{grid-template-columns:1fr}}
</style>
