// transit_search card plugin — JIT loaded from
// ~/.mywant/custom-types/mywant-transit-plugin/view/plugin.jsx
//
// Collapsed: one rail, departure on the left, arrival on the right, a dot for
//   every station in between — stations and times only.
// Expanded:  every route candidate the search returned, stacked vertically with
//   line names, fare and duration.
//
// window.React and window.__mywant are provided by the host app. Tailwind
// classes are not available here (the host compiles them from its own sources),
// so styling is a self-contained <style> block plus inline styles.
const React = window.React;

// ── line colours ─────────────────────────────────────────────────────────────
// Real line colours make a route readable at a glance. Anything unknown falls
// back to a hashed hue so two lines never collapse onto the same colour.
const LINE_COLORS = [
  [/山手/, '#9ACD32'],
  [/京浜東北/, '#00B2E5'],
  // 総武 first: 中央・総武線 is the yellow one, every other 中央 (快速 / 特快 /
  // 青梅直通) is orange.
  [/中央.*緩行|総武/, '#FFD400'],
  [/中央/, '#F15A22'],
  [/埼京/, '#00B48D'],
  [/湘南新宿/, '#E21F26'],
  [/横須賀/, '#0067C0'],
  [/新幹線/, '#2B5FA0'],
  [/丸ノ内/, '#F62E36'],
  [/銀座/, '#FF9500'],
  [/日比谷/, '#B5B5AC'],
  [/東西/, '#009BBF'],
  [/千代田/, '#00BB85'],
  [/有楽町/, '#C1A470'],
  [/半蔵門/, '#8F76D6'],
  [/南北/, '#00AC9B'],
  [/副都心/, '#9C5E31'],
  [/浅草/, '#E85298'],
  [/三田/, '#006AB8'],
  [/新宿線/, '#6CBB5A'],
  [/大江戸/, '#B6007A'],
  [/京王/, '#DD0077'],
  [/小田急/, '#0071BC'],
  [/東急/, '#DA0442'],
  [/西武/, '#0080C7'],
  [/東武/, '#0F6CC1'],
  [/京急/, '#00A7DB'],
  [/京成/, '#0855A0'],
  [/りんかい/, '#00609A'],
  [/ゆりかもめ/, '#0071BC'],
  [/モノレール/, '#0B318F'],
];

const isWalk = (line) => !line || /徒歩/.test(line);

function lineColor(line) {
  if (isWalk(line)) return '#9CA3AF';
  for (const [re, color] of LINE_COLORS) {
    if (re.test(line)) return color;
  }
  let hash = 0;
  for (let i = 0; i < line.length; i++) hash = (hash * 31 + line.charCodeAt(i)) | 0;
  return `hsl(${Math.abs(hash) % 360}, 62%, 48%)`;
}

// ── data shaping ─────────────────────────────────────────────────────────────

/** Segments → the stations drawn on the rail (n segments give n+1 stations). */
function toNodes(itinerary) {
  if (!itinerary.length) return [];
  const nodes = [{ name: itinerary[0].from, depart: itinerary[0].depart_time }];
  itinerary.forEach((seg, i) => {
    nodes.push({
      name: seg.to,
      arrive: seg.arrive_time,
      depart: itinerary[i + 1] ? itinerary[i + 1].depart_time : undefined,
    });
  });
  return nodes;
}

/** Yahoo appends the operator to transfer stations ("新宿(東京メトロ)") — drop it. */
const shortName = (name) => String(name || '').replace(/[（(][^）)]*[）)]?\s*$/, '') || String(name || '');

const asSegments = (value) =>
  Array.isArray(value) ? value.filter((s) => s && typeof s === 'object' && s.from) : [];

const asRoutes = (value) =>
  Array.isArray(value) ? value.filter((r) => r && typeof r === 'object' && r.itinerary) : [];

/** Wants searched before `routes` existed only kept route 0 — rebuild it. */
function fallbackRoutes(want, itinerary) {
  if (!itinerary.length) return [];
  const cur = want.state?.current ?? {};
  return [{
    index: 1,
    departure: cur.departure || itinerary[0].depart_time || '',
    arrival: cur.arrival || itinerary[itinerary.length - 1].arrive_time || '',
    duration_minutes: Number(cur.duration_minutes) || 0,
    fare: Number(cur.fare) || 0,
    transfers: Number(cur.transfers) || Math.max(0, itinerary.length - 1),
    itinerary,
  }];
}

// ── styles ───────────────────────────────────────────────────────────────────
const CSS = `
.ts-grid { display:grid; align-items:center; row-gap:2px; width:100%; }
.ts-name { justify-self:center; max-width:7em; padding:0 2px;
           overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ts-name-end { font-weight:600; color:#1f2937; }
.ts-name-mid { font-size:0.8em; color:#6b7280; }
.ts-time { justify-self:center; text-align:center; line-height:1.15;
           font-variant-numeric:tabular-nums; }
.ts-time-end { font-size:0.85em; color:#374151; }
.ts-time-mid { font-size:0.74em; color:#9ca3af; }
.ts-depart { color:#059669; }
.ts-line { justify-self:center; width:100%; text-align:center; font-size:0.72em;
           overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ts-stack { height:100%; overflow-y:auto; display:flex; flex-direction:column;
            gap:10px; padding:8px 12px; }
.ts-route { display:flex; flex-direction:column; gap:8px; padding:10px 12px;
            border:1px solid rgba(0,0,0,0.08); border-radius:10px;
            background:rgba(255,255,255,0.72); box-shadow:0 1px 2px rgba(0,0,0,0.05); }
.ts-head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.ts-badge { flex-shrink:0; font-size:0.7em; font-weight:600; padding:1px 8px;
            border-radius:999px; background:#cffafe; color:#155e75; }
.ts-meta { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; font-size:0.8em; }
.ts-meta-main { font-weight:600; color:#374151; font-variant-numeric:tabular-nums; }
.ts-meta-sub { color:#6b7280; font-variant-numeric:tabular-nums; }
.ts-empty { text-align:center; color:#9ca3af; padding:0 12px; }

.dark .ts-name-end { color:#f3f4f6; }
.dark .ts-name-mid { color:#9ca3af; }
.dark .ts-time-end { color:#e5e7eb; }
.dark .ts-time-mid { color:#6b7280; }
.dark .ts-depart { color:#34d399; }
.dark .ts-route { border-color:rgba(255,255,255,0.12); background:rgba(31,41,55,0.55);
                  box-shadow:none; }
.dark .ts-badge { background:rgba(14,116,144,0.5); color:#a5f3fc; }
.dark .ts-meta-main { color:#e5e7eb; }
.dark .ts-meta-sub { color:#9ca3af; }
`;

// ── rail ─────────────────────────────────────────────────────────────────────

/**
 * Laid out as a grid whose columns alternate station / segment: station columns
 * size to their label so names can never overlap, segment columns take the
 * slack so the rail stretches over whatever width is left.
 */
function RouteRail({ itinerary, detailed }) {
  const nodes = toNodes(itinerary);
  if (nodes.length < 2) return null;

  const columns = nodes.map((_, i) => (i === 0 ? 'auto' : 'minmax(1em, 1fr) auto')).join(' ');
  const isEnd = (i) => i === 0 || i === nodes.length - 1;

  const dot = (_node, i) => {
    const color = lineColor(itinerary[Math.min(i, itinerary.length - 1)].line);
    const size = isEnd(i) ? '0.7em' : '0.4em';
    return (
      <span
        key={`dot-${i}`}
        style={{
          justifySelf: 'center',
          width: size,
          height: size,
          borderRadius: '50%',
          boxSizing: 'content-box',
          background: isEnd(i) ? '#fff' : color,
          border: `${isEnd(i) ? 0.2 : 0.14}em solid ${color}`,
        }}
      />
    );
  };

  const bar = (i) => {
    const line = itinerary[i].line;
    const color = lineColor(line);
    return (
      <span
        key={`bar-${i}`}
        style={{
          width: '100%',
          height: '0.22em',
          borderRadius: '999px',
          background: isWalk(line)
            ? `repeating-linear-gradient(90deg, ${color} 0 0.25em, transparent 0.25em 0.5em)`
            : color,
        }}
      />
    );
  };

  const name = (node, i) => (
    <span
      key={`name-${i}`}
      className={`ts-name ${isEnd(i) ? 'ts-name-end' : 'ts-name-mid'}`}
      title={node.name}
    >
      {shortName(node.name)}
    </span>
  );

  const time = (node, i) => {
    // The collapsed rail shows one time per station; the detailed one also shows
    // how long you wait at a transfer (arrival above, departure below).
    const both = detailed && node.arrive && node.depart && node.arrive !== node.depart;
    return (
      <span key={`time-${i}`} className={`ts-time ${isEnd(i) ? 'ts-time-end' : 'ts-time-mid'}`}>
        {both
          ? [node.arrive, <br key="br" />, <span key="dep" className="ts-depart">{node.depart}</span>]
          : (i === 0 ? node.depart : node.arrive) || ''}
      </span>
    );
  };

  const lineName = (i) => {
    const { line, direction } = itinerary[i];
    return (
      <span
        key={`line-${i}`}
        className="ts-line"
        style={{ color: lineColor(line) }}
        title={direction ? `${line} ${direction}` : line}
      >
        {line || '徒歩'}
      </span>
    );
  };

  // Cells are emitted row by row; the grid drops them into the alternating
  // station / segment columns declared above.
  const row = (stationCell, segmentCell) =>
    nodes.flatMap((node, i) =>
      i === 0
        ? [stationCell(node, i)]
        : [segmentCell ? segmentCell(i - 1) : <span key={`gap-${i}`} />, stationCell(node, i)],
    );

  return (
    <div className="ts-grid" style={{ gridTemplateColumns: columns }}>
      {detailed && row((_n, i) => <span key={`lgap-${i}`} />, lineName)}
      {row(name)}
      {row(dot, bar)}
      {row(time)}
    </div>
  );
}

function RouteMeta({ route }) {
  return (
    <div className="ts-meta">
      <span className="ts-meta-main">{route.departure} → {route.arrival}</span>
      {route.duration_minutes > 0 && <span className="ts-meta-sub">{route.duration_minutes}分</span>}
      {route.fare > 0 && <span className="ts-meta-sub">¥{Number(route.fare).toLocaleString()}</span>}
      <span className="ts-meta-sub">乗換{route.transfers || 0}回</span>
    </div>
  );
}

// ── plugin ───────────────────────────────────────────────────────────────────

function TransitSearchContentSection({ want, isExpanded }) {
  const cur = want.state?.current ?? {};
  const itinerary = asSegments(cur.itinerary || want.state?.final_result);
  const stored = asRoutes(cur.routes);
  const routes = stored.length ? stored : fallbackRoutes(want, itinerary);

  const style = <style key="css">{CSS}</style>;

  if (!routes.length) {
    const from = cur.from || want.spec?.params?.from || '';
    const to = cur.to || want.spec?.params?.to || '';
    return window.__mywant.createCardLayout({
      centerContent: true,
      content: (
        <div className="ts-empty">
          {style}
          {from || to ? `${from || '?'} → ${to || '?'}` : '経路検索'}
          <div style={{ fontSize: '0.8em', opacity: 0.7 }}>検索中…</div>
        </div>
      ),
    });
  }

  // Collapsed: stations and times only — readable in one glance, nothing else.
  if (!isExpanded) {
    return window.__mywant.createCardLayout({
      centerContent: true,
      content: (
        <div style={{ width: '100%', padding: '0 12px' }}>
          {style}
          <RouteRail itinerary={routes[0].itinerary} />
        </div>
      ),
    });
  }

  // Expanded: every transfer pattern the search returned, stacked vertically.
  return window.__mywant.createCardLayout({
    content: (
      <div className="ts-stack">
        {style}
        {routes.map((route, i) => (
          <div className="ts-route" key={route.index ?? i}>
            <div className="ts-head">
              <span className="ts-badge">ルート{route.index ?? i + 1}</span>
              <RouteMeta route={route} />
            </div>
            <RouteRail itinerary={route.itinerary} detailed />
          </div>
        ))}
      </div>
    ),
  });
}

window.__mywant.registerPlugin({
  types: ['transit_search'],
  ContentSection: TransitSearchContentSection,
  hideFinalResult: true,
});
