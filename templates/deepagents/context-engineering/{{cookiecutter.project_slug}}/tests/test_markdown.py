"""Render the real vendored browser parser offline and check the HTML boundary."""
from pathlib import Path
import shutil
import subprocess

import pytest


NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is unavailable; optional offline Markdown checks skipped")
STATIC = Path(__file__).resolve().parents[1] / "src" / "{{cookiecutter.project_slug}}" / "static"

SCRIPT = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const [staticPath, scenario] = process.argv.slice(1);
const context = vm.createContext({atob, btoa, TextDecoder, TextEncoder});
context.window = context;
for (const filename of ['markdown-it.min.js', 'markdown.js']) {
  const source = path.join(staticPath, filename);
  if (fs.existsSync(source)) vm.runInContext(fs.readFileSync(source, 'utf8'), context);
}
assert.equal(typeof context.ContextMarkdown?.render, 'function', 'The shipped UI must expose a Markdown renderer');
const render = context.ContextMarkdown.render;
if (scenario === 'rich') {
  const output = render('# Research report\n\n中文 **证据** with `memory.md`.\n\n| Model | Result |\n| --- | --- |\n| A | Complete |\n\n- First\n- Second\n\n> Read back the evidence.\n\n```python\nprint("<script>")\n```');
  assert.match(output, /<h1>Research report<\/h1>/);
  assert.match(output, /<strong>证据<\/strong>/);
  assert.match(output, /<code>memory\.md<\/code>/);
  assert.match(output, /<table>[\s\S]*<td>A<\/td>/);
  assert.match(output, /<ul>[\s\S]*<li>Second<\/li>/);
  assert.match(output, /<blockquote>/);
  assert.match(output, /<pre><code class="language-python">print\(&quot;&lt;script&gt;&quot;\)/);
} else if (scenario === 'unsafe') {
  const output = render('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[bad](javascript:alert(1)) [entity](javascript&#x3A;alert(1)) [data](data:text/html,payload) [file](file:///etc/passwd) [relative](//example.com)\n\n```html\n<img src=x onerror=alert(1)>\n```');
  assert.doesNotMatch(output, /<script|<img|onerror="|href="(?:javascript:|data:|file:|\/\/)/i);
  assert.match(output, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(output, /&lt;img src=x onerror=alert\(1\)&gt;/);
  for (const destination of [
    'JaVaScRiPt:alert(1)', 'jav&#x61;script&#58;alert(1)',
    'java%09script:alert(1)', '\u200bjavascript:alert(1)',
    'javascript\uff1aalert(1)', 'vbscript:msgbox(1)',
    'data:image/svg+xml,payload', '//example.com/path', '/api/memory'
  ]) {
    assert.doesNotMatch(render(`[Unsafe](${destination})`), /<a\b/i, `Unsafe destination must not be navigable: ${destination}`);
    assert.doesNotMatch(render(`![Unsafe](${destination})`), /<a\b|<img\b/i, `Unsafe image must not load: ${destination}`);
  }
  const attributes = render('```html\"onclick=\"alert(1)\n<script>example</script>\n```\n\n[Quoted](https://example.com/?q=%22onclick%3D%22alert(1))');
  assert.doesNotMatch(attributes, /<script|\sonclick=/i);
  assert.match(attributes, /&lt;script&gt;example&lt;\/script&gt;/);
} else if (scenario === 'links') {
  const output = render('[Source](https://example.com/?a=1&b=2) [Mail](mailto:reader@example.com)\n\n![Chart <safe>](https://example.com/chart.png)');
  assert.match(output, /href="https:\/\/example\.com\/\?a=1&amp;b=2"/);
  assert.match(output, /target="_blank"/);
  assert.match(output, /rel="noopener noreferrer"/);
  assert.match(output, /href="mailto:reader@example\.com"/);
  assert.doesNotMatch(output, /<img/);
  assert.match(output, /Chart &lt;safe&gt;/);
} else if (scenario === 'files') {
  function element() {
    return {innerHTML:'stale', textContent:'', classList:{toggle(){}}};
  }
  const markdown = element();
  context.ContextMarkdown.renderInto(markdown, '# Read back', {filename:'/reports/brief.MD'});
  assert.match(markdown.innerHTML, /<h1>Read back<\/h1>/);
  const code = element();
  context.ContextMarkdown.renderInto(code, '<script>example</script>\n# Python comment', {filename:'/src/example.py'});
  assert.equal(code.textContent, '<script>example</script>\n# Python comment');
  assert.equal(code.innerHTML, '', 'Plain file rendering must clear stale rich content');
  assert.equal(render(null), '', 'Empty output must clear the current answer');
} else { throw new Error(`Unknown scenario: ${scenario}`); }
"""


@pytest.mark.parametrize("scenario", ["rich", "unsafe", "links", "files"])
def test_markdown_renders_documents_without_executing_model_output(scenario):
    result = subprocess.run([NODE, "-e", SCRIPT, str(STATIC), scenario], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
