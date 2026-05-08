# Gemini Playwright Automation — Debug Notes

## Overview

This document records the key issues and solutions discovered while getting Playwright-based Gemini automation working in a headless Docker environment.

---

## 1. Chrome Args for Headless Docker

**Working configuration:**

```python
args=[
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-gpu",
    "--no-zygote",
    "--window-size=1920,1080",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]
```

**Critical**: Do NOT include `--disable-software-rasterizer`. Combining it with `--disable-gpu` removes all rendering backends, causing immediate `Page crashed` errors for GPU-accelerated sites like Gemini and ChatGPT.

---

## 2. `innerText` vs `textContent` — The Root Cause of Most Failures

### Problem

Playwright's headless Chromium (with `--disable-gpu`) renders pages but does not fully compute CSS layout for all elements. Elements that are technically present in the DOM may be reported as "not visible" by the browser's layout engine.

`innerText` is layout-dependent — it returns an empty string for elements that are hidden or whose layout has not been computed.

`textContent` is layout-independent — it always returns the text regardless of visibility.

### Impact

- **JS text injection check**: After injecting text into the Quill editor, checking `editor.innerText.trim().length > 0` always returned 0, making all 3 injection methods appear to fail.
- **Response extraction**: Extracting response text via `element.innerText` returned empty even when `<p>` tags contained real content.

### Fix

Replace all `innerText` with `textContent` in JS evaluated inside `page.evaluate()`.

```javascript
// WRONG - returns empty for not-visible elements
if (editor.innerText.trim().length > 0) return true;

// CORRECT - layout-independent
if ((editor.textContent || '').trim().length > 0) return true;
```

---

## 3. Quill Editor Text Injection

Gemini uses a **Quill rich text editor** (`rich-textarea .ql-editor`), which is a `contenteditable` div — NOT a regular `<input>` or `<textarea>`. Standard Playwright `fill()` does not work.

### Selector

```javascript
const editor = document.querySelector('rich-textarea .ql-editor')
            || document.querySelector('[contenteditable="true"]');
```

Note: Despite the `rich-textarea` custom element, `.ql-editor` is in the **regular DOM**, not a shadow DOM. No `pierce/` prefix needed.

### 3-Method Injection (in order of preference)

```javascript
if (!editor) return false;
editor.focus();

// Method 1: execCommand (most natural, triggers Quill's internal handlers)
editor.innerHTML = '';
document.execCommand('insertText', false, text);
if ((editor.textContent || '').trim().length > 0) return true;

// Method 2: ClipboardEvent paste simulation
try {
    const dt = new DataTransfer();
    dt.setData('text/plain', text);
    editor.dispatchEvent(new ClipboardEvent('paste', {
        clipboardData: dt, bubbles: true, cancelable: true
    }));
    if ((editor.textContent || '').trim().length > 0) return true;
} catch(e) {}

// Method 3: Direct innerHTML (always succeeds as final fallback)
const escaped = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
editor.innerHTML = '<p>' + escaped + '</p>';
editor.classList.remove('ql-blank');
['input', 'keyup', 'change', 'compositionend'].forEach(type => {
    editor.dispatchEvent(new Event(type, { bubbles: true }));
});
return (editor.textContent || '').trim().length > 0;
```

Method 3 should always return `true`. If it returns `false`, the issue is `innerText` vs `textContent` (see Section 2).

---

## 4. Response Extraction

Gemini's response is rendered as multiple `<p>` tags inside a response container. The old code took the single longest `innerText` element, which failed for two reasons:
1. `innerText` returned empty (layout issue — see Section 2)
2. Taking only one element missed multi-paragraph responses

### Fix: Concatenate all `<p>` and `<li>` paragraphs using `textContent`

```javascript
const paras = [...document.querySelectorAll('p, li')];
const paraText = paras
    .map(p => (p.textContent || '').trim())
    .filter(t => t.length > 5)
    .join('\n');
if (paraText.length > 50) return paraText;

// Final fallback: full body text
const bodyText = (document.body.textContent || document.body.innerText || '').trim();
if (bodyText.length > 100) return bodyText.slice(-4000);
```

---

## 5. HTML Saving for Debug

When extraction fails, save the full page HTML for offline debugging:

```python
await _save_html(page, -1, f"{llm_name}_extract_fail")
```

This saves to `/data/screenshots/{llm_name}_extract_fail_{timestamp}.html`. The Admin web UI (`backend/static/admin.html`, served by FastAPI) has an HTML viewer to browse these files without needing to access the server directly.

---

## 6. Page Crash Diagnosis

If you see `Page crashed` immediately after navigation:

1. Check Chrome args — `--disable-software-rasterizer` + `--disable-gpu` = crash
2. Check memory: `free -h` — Docker containers sharing host RAM with concurrency=5 may OOM
3. Check disk: `df -h` — Postgres will crash if disk is full; Docker won't pull new images

---

## 7. Celery Queue Issue

The worker listens to multiple queues including the default `celery` queue and LLM-specific queues (`llm_gemini`, `llm_chatgpt`, etc.).

When triggering queries manually from the server (e.g., via Django shell or celery task dispatch), use `queue='celery'` — the LLM-specific queue name requires the DB to resolve the LLM name, which needs `psycopg2` (sync driver), not `asyncpg`.

---

## 8. Lessons Learned

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| JS injection always "fails" | `innerText` empty for hidden elements | Use `textContent` |
| Response extraction empty | Same `innerText` issue | Use `textContent` |
| Page crashed on GPU sites | `--disable-software-rasterizer` + `--disable-gpu` | Remove `--disable-software-rasterizer` |
| Quill editor not fillable | `contenteditable` div, not input | 3-method JS injection |
| Multi-paragraph response truncated | Taking only longest single element | Concatenate all `<p>` + `<li>` |
| Container not updating | `build: ./admin_console` (local only) | Push to ACR, use `image:` in compose |
| 502 after restart | nginx cached old container IP | `docker compose restart nginx` |
| Disk full → postgres crash | Docker image accumulation | `docker system prune -af` |
