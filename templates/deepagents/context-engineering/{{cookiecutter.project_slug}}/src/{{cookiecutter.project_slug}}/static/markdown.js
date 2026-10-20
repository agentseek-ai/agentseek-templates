/* Safe presentation of untrusted model answers and virtual Markdown files. */
(function (root) {
  'use strict';

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[character]));
  }

  // Only explicit public web/mail links are navigable. Relative and local file
  // paths belong to the virtual workspace, not the host browser's origin.
  function safeLink(value) {
    return /^(?:https?:\/\/|mailto:)/i.test(value) && !/[\u0000-\u0020\u007f]/.test(value);
  }

  const parser = typeof root.markdownit === 'function'
    ? root.markdownit({html: false, linkify: false, typographer: false, breaks: false})
    : null;

  if (parser) {
    parser.validateLink = safeLink;
    const defaultLink = parser.renderer.rules.link_open || function (tokens, index, options, env, renderer) {
      return renderer.renderToken(tokens, index, options);
    };
    parser.renderer.rules.link_open = function (tokens, index, options, env, renderer) {
      tokens[index].attrSet('target', '_blank');
      tokens[index].attrSet('rel', 'noopener noreferrer');
      return defaultLink(tokens, index, options, env, renderer);
    };
    // Keep image references useful without automatically requesting remote
    // resources supplied by a model or a downloaded document.
    parser.renderer.rules.image = function (tokens, index, options, env, renderer) {
      const token = tokens[index];
      const label = renderer.renderInlineAsText(token.children || [], options, env) || 'Image';
      const source = token.attrGet('src') || '';
      return safeLink(source)
        ? '<a href="' + escapeHtml(source) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(label) + '</a>'
        : escapeHtml(label);
    };
  }

  function render(text) {
    const value = text == null ? '' : String(text);
    return parser ? parser.render(value) : escapeHtml(value).replace(/\n/g, '<br>');
  }

  function renderInto(element, text, options = {}) {
    const rich = !options.filename || /\.(?:md|markdown)$/i.test(options.filename);
    element.classList.toggle('markdown-body', rich);
    element.classList.toggle('plain-body', !rich);
    element.innerHTML = '';
    if (rich) {
      element.textContent = '';
      element.innerHTML = render(text);
    } else {
      element.textContent = text == null ? '' : String(text);
    }
  }

  root.ContextMarkdown = Object.freeze({render, renderInto});
}(typeof window === 'undefined' ? globalThis : window));
