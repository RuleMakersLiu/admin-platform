/**
 * XSS attack-vector regression suite for the HTML sanitizer.
 *
 * Safety net: locks the CURRENT (safe) behavior of prepareSandboxHtml — the only
 * live DOMPurify entry point (used by components/chat/CanvasPanel) — so any
 * future change to the DOMPurify config can be proven not to reopen an attack
 * vector. Strategy: feed real XSS payloads, parse the sanitized output with
 * jsdom, and assert no executable surface survives (no <script>, no on* handlers,
 * no javascript:/vbscript:/data: schemes on links/media) while benign content
 * (text, safe https images, tables, inline styles) is preserved.
 *
 * Pure-DOM test — does not depend on @testing-library/react.
 */
import { describe, it, expect } from 'vitest';
import { JSDOM } from 'jsdom';
import {
  prepareSandboxHtml,
  detectContentType,
  extractHtmlBlocks,
} from '@/utils/sanitize';

/** Run html through the sandbox sanitizer; return the parsed body document. */
function sanitize(html: string): Document {
  const fullDoc = prepareSandboxHtml(html);
  return new JSDOM(fullDoc).window.document;
}

/** Every (name, value) attribute across all elements in the body. */
function allAttrs(doc: Document): Array<{ name: string; value: string }> {
  const out: Array<{ name: string; value: string }> = [];
  doc.body.querySelectorAll('*').forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      out.push({ name: attr.name, value: attr.value });
    }
  });
  return out;
}

/** True if any attribute looks like an inline event handler (onclick, onerror…). */
function hasEventHandlers(doc: Document): boolean {
  return allAttrs(doc).some((a) => /^on/i.test(a.name));
}

describe('prepareSandboxHtml — XSS attack vectors are neutralized', () => {
  it('strips <script> blocks and their executable content', () => {
    const doc = sanitize('<p>hi</p><script>alert(1)</script>');
    expect(doc.querySelectorAll('script')).toHaveLength(0);
    expect(doc.body.textContent ?? '').not.toContain('alert(1)');
    expect(doc.body.textContent ?? '').toContain('hi');
  });

  it('strips inline event handlers (onerror, onclick, onload, …)', () => {
    const doc = sanitize(
      '<img src=x onerror=alert(1)><div onclick=alert(2)>x</div><body onload=alert(3)>'
    );
    expect(hasEventHandlers(doc)).toBe(false);
  });

  it('strips event handlers regardless of casing', () => {
    const doc = sanitize('<img src=x OnErRoR=alert(1)>');
    expect(hasEventHandlers(doc)).toBe(false);
  });

  it('blocks javascript: URLs in href', () => {
    const doc = sanitize('<a href="javascript:alert(1)">click</a>');
    const href = doc.querySelector('a')?.getAttribute('href') ?? '';
    expect(href).not.toMatch(/javascript:/i);
  });

  it('blocks javascript: URLs in src', () => {
    const doc = sanitize('<img src="javascript:alert(1)">');
    const src = doc.querySelector('img')?.getAttribute('src') ?? '';
    expect(src).not.toMatch(/javascript:/i);
  });

  it('blocks vbscript: URLs', () => {
    const doc = sanitize('<a href="vbscript:msgbox(1)">x</a>');
    const href = doc.querySelector('a')?.getAttribute('href') ?? '';
    expect(href).not.toMatch(/vbscript:/i);
  });

  it('removes <iframe>/<object>/<embed> (no data: HTML smuggling)', () => {
    const doc = sanitize(
      '<iframe src="data:text/html,<script>alert(1)</script>"></iframe>' +
        '<object data="y"></object><embed src="z">'
    );
    expect(doc.querySelectorAll('iframe,object,embed,frame,frameset')).toHaveLength(0);
  });

  it('removes <svg> vectors (svg not in allowlist)', () => {
    const doc = sanitize('<svg onload="alert(1)"><script>alert(2)</script></svg>');
    expect(doc.querySelectorAll('svg')).toHaveLength(0);
    expect(doc.body.textContent ?? '').not.toContain('alert');
  });

  it('strips <meta> refresh / http-equiv redirects', () => {
    // Scope to body: prepareSandboxHtml's wrapper legitimately injects metas
    // (charset / viewport / CSP) into <head>; user-supplied <meta> lands in body
    // and must be stripped.
    const doc = sanitize(
      '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">'
    );
    expect(doc.body.querySelectorAll('meta')).toHaveLength(0);
  });

  it('strips <form>/<input>/<button> (formaction attacks)', () => {
    const doc = sanitize(
      '<form action="javascript:alert(1)"><button formaction="javascript:alert(2)">go</button></form>'
    );
    expect(doc.querySelectorAll('form,button,input,select,textarea')).toHaveLength(0);
  });

  it('strips <base> (base-URL hijack)', () => {
    const doc = sanitize('<base href="https://evil.com/">');
    expect(doc.querySelectorAll('base')).toHaveLength(0);
  });

  it('strips <link> (stylesheet/rel-based import)', () => {
    const doc = sanitize('<link rel="stylesheet" href="javascript:alert(1)">');
    expect(doc.querySelectorAll('link')).toHaveLength(0);
  });

  it('keeps no attribute whose value carries a script scheme', () => {
    const doc = sanitize(
      '<a href="javascript:alert(1)"><img src="javascript:alert(2)"></a>'
    );
    const scripted = allAttrs(doc).filter((a) =>
      /javascript:|vbscript:/i.test(a.value)
    );
    expect(scripted).toEqual([]);
  });
});

describe('prepareSandboxHtml — benign content is preserved', () => {
  it('keeps paragraphs, emphasis, and text', () => {
    const doc = sanitize('<p>Hello <strong>world</strong></p>');
    expect(doc.querySelector('p')).not.toBeNull();
    expect(doc.querySelector('strong')).not.toBeNull();
    expect(doc.body.textContent).toContain('Hello world');
  });

  it('keeps safe https images with alt text', () => {
    const doc = sanitize('<img src="https://example.com/a.png" alt="pic">');
    const img = doc.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe('https://example.com/a.png');
    expect(img?.getAttribute('alt')).toBe('pic');
  });

  it('keeps safe https links', () => {
    const doc = sanitize('<a href="https://example.com">link</a>');
    expect(doc.querySelector('a')?.getAttribute('href')).toBe('https://example.com');
  });

  it('keeps tables with cell content', () => {
    const doc = sanitize('<table><tbody><tr><td>cell</td></tr></tbody></table>');
    expect(doc.querySelector('table td')?.textContent).toContain('cell');
  });

  it('preserves benign inline style attribute (sandbox allows style)', () => {
    const doc = sanitize('<div style="color:red">x</div>');
    const style = doc.querySelector('div')?.getAttribute('style') ?? '';
    expect(style).toContain('red');
  });

  it('returns a full <!DOCTYPE html> document with CSP meta', () => {
    const out = prepareSandboxHtml('<p>x</p>');
    expect(out).toContain('<!DOCTYPE html>');
    expect(out).toMatch(/Content-Security-Policy/i);
  });
});

describe('detectContentType', () => {
  it('classifies a full html document', () => {
    expect(
      detectContentType('<!DOCTYPE html><html><body><div></div></body></html>')
    ).toBe('html');
  });
  it('classifies markdown by heading', () => {
    expect(detectContentType('# Title\n\nbody text')).toBe('markdown');
  });
  it('falls back to text for plain content', () => {
    expect(detectContentType('just plain text without markup')).toBe('text');
  });
  it('returns text for empty input', () => {
    expect(detectContentType('')).toBe('text');
  });
});

describe('extractHtmlBlocks', () => {
  it('extracts ```html fenced blocks', () => {
    const blocks = extractHtmlBlocks('intro\n```html\n<div>x</div>\n```\n');
    expect(blocks).toHaveLength(1);
    expect(blocks[0].language).toBe('html');
    expect(blocks[0].code).toContain('<div>x</div>');
  });
  it('extracts ```svg blocks', () => {
    const blocks = extractHtmlBlocks('```svg\n<svg></svg>\n```');
    expect(blocks).toHaveLength(1);
    expect(blocks[0].language).toBe('svg');
  });
  it('ignores non-html fenced blocks', () => {
    expect(extractHtmlBlocks('```python\nprint(1)\n```')).toHaveLength(0);
  });
  it('returns empty for content without code fences', () => {
    expect(extractHtmlBlocks('no code here')).toHaveLength(0);
  });
});
