/* MedExplain multilingual UI layer.
 * The medicine names, source OCR text, numeric results and units are intentionally
 * preserved. Only reviewed interface phrases are translated by the local dictionaries.
 */
(() => {
  const supported = new Set(['en', 'hi', 'pa']);
  // Attach the session CSRF token to same-origin state-changing fetch requests.
  if (!window.__medexFetchCsrfInstalled) {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
      const url = typeof input === 'string' ? input : input.url;
      const method = (init.method || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
      const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
      const token = document.querySelector('meta[name="csrf-token"]')?.content;
      if (token && ['POST','PUT','PATCH','DELETE'].includes(method) && new URL(url, location.href).origin === location.origin) headers.set('X-CSRF-Token', token);
      return nativeFetch(input, { ...init, headers });
    };
    window.__medexFetchCsrfInstalled = true;
  }
  let currentLanguage = window.MEDEX_INITIAL_LANGUAGE || localStorage.getItem('medex_language') || 'en';
  let dictionary = {};
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  const skippedTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'PRE', 'CODE', 'TEXTAREA']);

  async function loadDictionary(language) {
    if (!supported.has(language)) language = 'en';
    const response = await fetch(`/api/translations/${language}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Could not load ${language} translations`);
    return response.json();
  }

  function translateTextNode(node) {
    const parent = node.parentElement;
    if (!parent || skippedTags.has(parent.tagName) || parent.closest('pre,code,script,style,textarea,[data-no-translate]')) return;
    if (!originalText.has(node)) originalText.set(node, node.nodeValue);
    const source = originalText.get(node);
    if (currentLanguage === 'en') {
      if (node.nodeValue !== source) node.nodeValue = source;
      return;
    }
    const trimmed = source.trim();
    if (!trimmed) return;
    let translated = dictionary[trimmed];
    if (translated === undefined) {
      translated = trimmed;
      // Translate only reviewed UI phrases embedded in dynamic status strings.
      const keys = Object.keys(dictionary).sort((a, b) => b.length - a.length);
      for (const key of keys) {
        if (key.length < 5 || !translated.includes(key)) continue;
        translated = translated.split(key).join(dictionary[key]);
      }
    }
    if (translated !== trimmed) {
      const leading = source.match(/^\s*/)?.[0] || '';
      const trailing = source.match(/\s*$/)?.[0] || '';
      const nextValue = leading + translated + trailing;
      if (node.nodeValue !== nextValue) node.nodeValue = nextValue;
    } else if (node.nodeValue !== source && currentLanguage === 'en') {
      node.nodeValue = source;
    }
  }

  function translateAttributes(root = document) {
    const attributes = ['placeholder', 'title', 'aria-label'];
    const elements = root.nodeType === Node.ELEMENT_NODE ? [root, ...root.querySelectorAll('*')] : [...root.querySelectorAll('*')];
    for (const element of elements) {
      if (skippedTags.has(element.tagName) || element.closest('[data-no-translate]')) continue;
      for (const attribute of attributes) {
        if (!element.hasAttribute(attribute)) continue;
        let saved = originalAttributes.get(element);
        if (!saved) { saved = {}; originalAttributes.set(element, saved); }
        if (!(attribute in saved)) saved[attribute] = element.getAttribute(attribute);
        const source = saved[attribute];
        element.setAttribute(attribute, currentLanguage === 'en' ? source : (dictionary[source] || source));
      }
    }
  }

  function applyTranslations(root = document) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(translateTextNode);
    translateAttributes(root);
    document.documentElement.lang = currentLanguage;
    document.title = currentLanguage === 'hi' ? 'MedExplain — स्वास्थ्य को समझें' : currentLanguage === 'pa' ? 'MedExplain — ਸਿਹਤ ਨੂੰ ਸਮਝੋ' : 'MedExplain — Health, made clear';
  }

  async function setLanguage(language, persist = true) {
    if (!supported.has(language)) language = 'en';
    try {
      dictionary = await loadDictionary(language);
      currentLanguage = language;
      localStorage.setItem('medex_language', language);
      const selector = document.getElementById('langSelect');
      if (selector) selector.value = language;
      applyTranslations(document);
      if (persist) {
        const response = await fetch('/api/language', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ language })
        });
        if (!response.ok) throw new Error('Could not save language preference');
      }
      document.dispatchEvent(new CustomEvent('medex:languagechange', { detail: { language } }));
    } catch (error) {
      console.error('MedExplain language error:', error);
      const message = language === 'hi' ? 'भाषा लोड नहीं हो सकी।' : language === 'pa' ? 'ਭਾਸ਼ਾ ਲੋਡ ਨਹੀਂ ਹੋ ਸਕੀ।' : 'Could not load language.';
      const toast = document.getElementById('toast');
      if (toast) { toast.textContent = message; toast.classList.add('show'); }
    }
  }

  window.MedExplainI18n = {
    get language() { return currentLanguage; },
    t(key) { return dictionary[key] || key; },
    setLanguage
  };

  document.addEventListener('DOMContentLoaded', () => {
    const selector = document.getElementById('langSelect');
    if (selector) selector.addEventListener('change', event => setLanguage(event.target.value, true));
    const preferred = supported.has(currentLanguage) ? currentLanguage : 'en';
    setLanguage(preferred, true);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData') translateTextNode(record.target);
        record.addedNodes?.forEach(node => {
          if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
          else if (node.nodeType === Node.ELEMENT_NODE) applyTranslations(node);
        });
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  });
})();
