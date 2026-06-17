import React, { useEffect, useMemo, useState } from 'react';

const STORAGE_KEYS = {
  theme: 'devtoolkit-theme',
  favorites: 'devtoolkit-favorites',
  recents: 'devtoolkit-recents',
};

const initialTools = [
  { id: 'json-formatter', category: 'Data', name: 'JSON Formatter', description: 'Format and prettify JSON payloads.', shortcut: '1' },
  { id: 'json-validator', category: 'Data', name: 'JSON Validator', description: 'Validate JSON and show parse errors.', shortcut: '2' },
  { id: 'jwt-decoder', category: 'Security', name: 'JWT Decoder', description: 'Decode headers and payloads from a JWT.', shortcut: '3' },
  { id: 'uuid-generator', category: 'Generators', name: 'UUID Generator', description: 'Generate fast RFC4122 UUIDs.', shortcut: '4' },
  { id: 'timestamp-converter', category: 'Time', name: 'Timestamp Converter', description: 'Convert Unix timestamps and ISO dates.', shortcut: '5' },
  { id: 'sha256', category: 'Security', name: 'SHA-256 Hash Generator', description: 'Hash text into SHA-256 hex output.', shortcut: '6' },
  { id: 'regex-tester', category: 'Text', name: 'Regex Tester', description: 'Test expressions against sample text.', shortcut: '7' },
  { id: 'color-converter', category: 'Design', name: 'Color Converter', description: 'Convert HEX, RGB, and HSL values.', shortcut: '8' },
  { id: 'text-diff', category: 'Text', name: 'Text Diff Checker', description: 'Compare two blocks of text.', shortcut: '9' },
];

const allCategories = ['All', ...new Set(initialTools.map((tool) => tool.category))];

const loadState = (key, fallback) => {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const toHex = (value) => value.toString(16).padStart(2, '0');

const parseColor = (input) => {
  const trimmed = input.trim();
  if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(trimmed)) {
    const hex = trimmed.slice(1);
    const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
    return {
      hex: `#${full.toUpperCase()}`,
      rgb: {
        r: parseInt(full.slice(0, 2), 16),
        g: parseInt(full.slice(2, 4), 16),
        b: parseInt(full.slice(4, 6), 16),
      },
    };
  }
  const match = trimmed.match(/^rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)$/i);
  if (match) {
    return {
      rgb: { r: clamp(Number(match[1]), 0, 255), g: clamp(Number(match[2]), 0, 255), b: clamp(Number(match[3]), 0, 255) },
    };
  }
  return null;
};

const rgbToHsl = ({ r, g, b }) => {
  const red = r / 255;
  const green = g / 255;
  const blue = b / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l };
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = max;
  switch (max) {
    case red:
      h = (green - blue) / d + (green < blue ? 6 : 0);
      break;
    case green:
      h = (blue - red) / d + 2;
      break;
    default:
      h = (red - green) / d + 4;
  }
  return { h: Math.round(h * 60), s: Math.round(s * 100), l: Math.round(l * 100) };
};

const diffLines = (left, right) => {
  const a = left.split('\n');
  const b = right.split('\n');
  const max = Math.max(a.length, b.length);
  return Array.from({ length: max }, (_, index) => ({
    left: a[index] ?? '',
    right: b[index] ?? '',
    type: (a[index] ?? '') === (b[index] ?? '') ? 'same' : !a[index] ? 'add' : !b[index] ? 'remove' : 'change',
  }));
};

function App() {
  const [theme, setTheme] = useState(() => loadState(STORAGE_KEYS.theme, 'dark'));
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All');
  const [favorites, setFavorites] = useState(() => loadState(STORAGE_KEYS.favorites, []));
  const [recents, setRecents] = useState(() => loadState(STORAGE_KEYS.recents, []));
  const [activeTool, setActiveTool] = useState('json-formatter');
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(STORAGE_KEYS.theme, JSON.stringify(theme));
  }, [theme]);

  useEffect(() => localStorage.setItem(STORAGE_KEYS.favorites, JSON.stringify(favorites)), [favorites]);
  useEffect(() => localStorage.setItem(STORAGE_KEYS.recents, JSON.stringify(recents.slice(0, 6))), [recents]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === 'Escape') setPaletteOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const tools = useMemo(
    () =>
      initialTools.filter((tool) => {
        const matchesCategory = category === 'All' || tool.category === category;
        const matchesSearch =
          tool.name.toLowerCase().includes(search.toLowerCase()) ||
          tool.description.toLowerCase().includes(search.toLowerCase());
        return matchesCategory && matchesSearch;
      }),
    [search, category],
  );

  const currentTool = initialTools.find((tool) => tool.id === activeTool) ?? initialTools[0];

  const openTool = (toolId) => {
    setActiveTool(toolId);
    setRecents((list) => [toolId, ...list.filter((item) => item !== toolId)].slice(0, 6));
    setPaletteOpen(false);
  };

  const toggleFavorite = (toolId) => {
    setFavorites((list) => (list.includes(toolId) ? list.filter((item) => item !== toolId) : [toolId, ...list]));
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">DevToolKit</p>
          <h1>Developer dashboard</h1>
          <p className="muted">Search, launch, and reuse focused utilities from one place.</p>
        </div>
        <div className="stack">
          <button className="primary" onClick={() => setPaletteOpen(true)}>Open command palette</button>
          <button className="secondary" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            Toggle {theme === 'dark' ? 'light' : 'dark'} mode
          </button>
        </div>
        <section className="panel">
          <h2>Favorites</h2>
          <div className="chip-row">
            {favorites.length ? favorites.map((id) => <button key={id} className="chip" onClick={() => openTool(id)}>{initialTools.find((tool) => tool.id === id)?.name}</button>) : <span className="muted">No favorites yet.</span>}
          </div>
        </section>
        <section className="panel">
          <h2>Recent tools</h2>
          <div className="chip-row">
            {recents.length ? recents.map((id) => <button key={id} className="chip" onClick={() => openTool(id)}>{initialTools.find((tool) => tool.id === id)?.name}</button>) : <span className="muted">Your last tools appear here.</span>}
          </div>
        </section>
      </aside>

      <main className="content">
        <header className="hero">
          <div>
            <p className="eyebrow">Modern dashboard</p>
            <h2>Fast access to essential developer tools</h2>
          </div>
          <div className="searchbar">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tools..." />
            <span>Ctrl+K</span>
          </div>
        </header>

        <nav className="filters">
          {allCategories.map((item) => (
            <button key={item} className={item === category ? 'filter active' : 'filter'} onClick={() => setCategory(item)}>{item}</button>
          ))}
        </nav>

        <section className="grid">
          {tools.map((tool) => (
            <article key={tool.id} className="tool-card" onClick={() => openTool(tool.id)}>
              <div className="tool-head">
                <span>{tool.category}</span>
                <button
                  className={favorites.includes(tool.id) ? 'favorite active' : 'favorite'}
                  onClick={(event) => {
                    event.stopPropagation();
                    toggleFavorite(tool.id);
                  }}
                >
                  ♥
                </button>
              </div>
              <h3>{tool.name}</h3>
              <p>{tool.description}</p>
              <span className="shortcut">Shortcut {tool.shortcut}</span>
            </article>
          ))}
        </section>

        <section className="workspace panel">
          <div className="tool-head">
            <h2>{currentTool.name}</h2>
            <button className="secondary" onClick={() => toggleFavorite(currentTool.id)}>
              {favorites.includes(currentTool.id) ? 'Remove favorite' : 'Add favorite'}
            </button>
          </div>
          <ToolPanel toolId={currentTool.id} />
        </section>
      </main>

      {paletteOpen && (
        <div className="palette-backdrop" onClick={() => setPaletteOpen(false)}>
          <div className="palette" onClick={(event) => event.stopPropagation()}>
            <input autoFocus placeholder="Type to search tools..." value={search} onChange={(e) => setSearch(e.target.value)} />
            <div className="palette-list">
              {tools.map((tool) => (
                <button key={tool.id} onClick={() => openTool(tool.id)}>
                  <strong>{tool.name}</strong>
                  <span>{tool.category}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ToolPanel({ toolId }) {
  const [json, setJson] = useState('{\n  "name": "DevToolKit",\n  "status": "ready"\n}');
  const [jwt, setJwt] = useState('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiRGV2VG9vbEtpdCIsInJvbGUiOiJkZXZlbG9wZXIifQ.signature');
  const [uuid, setUuid] = useState(crypto.randomUUID());
  const [timestamp, setTimestamp] = useState(Math.floor(Date.now() / 1000).toString());
  const [text, setText] = useState('Hello world');
  const [regex, setRegex] = useState('[A-Za-z]+');
  const [sample, setSample] = useState('Hello 123 world');
  const [color, setColor] = useState('#1F8BFF');
  const [left, setLeft] = useState('line one\nline two');
  const [right, setRight] = useState('line one\nline 2');
  const [hash, setHash] = useState('');
  const [output, setOutput] = useState('');

  useEffect(() => {
    if (toolId === 'uuid-generator') setUuid(crypto.randomUUID());
  }, [toolId]);

  useEffect(() => {
    const run = async () => {
      try {
        switch (toolId) {
          case 'json-formatter':
            setOutput(JSON.stringify(JSON.parse(json), null, 2));
            break;
          case 'json-validator':
            JSON.parse(json);
            setOutput('Valid JSON');
            break;
          case 'jwt-decoder': {
            const [, payload = ''] = jwt.split('.');
            setOutput(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
            break;
          }
          case 'uuid-generator':
            setOutput(uuid);
            break;
          case 'timestamp-converter':
            setOutput(new Date(Number(timestamp) * 1000).toISOString());
            break;
          case 'sha256': {
            const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
            const value = Array.from(new Uint8Array(digest), (byte) => toHex(byte)).join('');
            setHash(value);
            setOutput(value);
            break;
          }
          case 'regex-tester': {
            const matches = sample.match(new RegExp(regex, 'g')) ?? [];
            setOutput(matches.length ? matches.join(', ') : 'No matches');
            break;
          }
          case 'color-converter': {
            const parsed = parseColor(color);
            if (!parsed) {
              setOutput('Enter HEX or rgb()');
              break;
            }
            const rgb = parsed.rgb;
            const hsl = rgbToHsl(rgb);
            setOutput(`${parsed.hex ?? `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`} | RGB ${rgb.r}, ${rgb.g}, ${rgb.b} | HSL ${hsl.h}, ${hsl.s}%, ${hsl.l}%`);
            break;
          }
          case 'text-diff':
            setOutput(diffLines(left, right).filter((line) => line.type !== 'same').length ? 'Differences found' : 'No differences');
            break;
          default:
            setOutput('Ready');
        }
      } catch (error) {
        setOutput(error instanceof Error ? error.message : 'Unable to process input');
      }
    };
    run();
  }, [toolId, json, jwt, uuid, timestamp, text, regex, sample, color, left, right]);

  if (toolId === 'json-formatter' || toolId === 'json-validator') {
    return (
      <div className="tool-body">
        <textarea value={json} onChange={(e) => setJson(e.target.value)} />
        <pre className="output">{output}</pre>
      </div>
    );
  }
  if (toolId === 'jwt-decoder') return (
    <div className="tool-body">
      <textarea value={jwt} onChange={(e) => setJwt(e.target.value)} />
      <pre className="output">{output}</pre>
    </div>
  );
  if (toolId === 'uuid-generator') return <div className="tool-body"><div className="mono">{uuid}</div><button className="secondary" onClick={() => setUuid(crypto.randomUUID())}>New UUID</button></div>;
  if (toolId === 'timestamp-converter') return <div className="tool-body"><input value={timestamp} onChange={(e) => setTimestamp(e.target.value)} /><pre className="output">{output}</pre></div>;
  if (toolId === 'sha256') return <div className="tool-body"><textarea value={text} onChange={(e) => setText(e.target.value)} /><pre className="output">{output || hash}</pre></div>;
  if (toolId === 'regex-tester') return (
    <div className="split">
      <input value={regex} onChange={(e) => setRegex(e.target.value)} />
      <textarea value={sample} onChange={(e) => setSample(e.target.value)} />
      <pre className="output">{output}</pre>
    </div>
  );
  if (toolId === 'color-converter') return <div className="tool-body"><input value={color} onChange={(e) => setColor(e.target.value)} /><pre className="output">{output}</pre></div>;
  if (toolId === 'text-diff') return (
    <div className="split">
      <textarea value={left} onChange={(e) => setLeft(e.target.value)} />
      <textarea value={right} onChange={(e) => setRight(e.target.value)} />
      <pre className="output">{output}</pre>
    </div>
  );
  return <div className="output">{output}</div>;
}

export default App;
