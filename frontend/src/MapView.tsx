import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { Link } from "react-router-dom";
import { Crosshair, Layers, LocateFixed, Minus, Plus, X } from "lucide-react";
import "./MapView.css";

type MapViewProps = {
  incidents: any[];
  resources: any[];
  focusId?: string;
  onSelect?: (id: string) => void;
  compact?: boolean;
};
type Point = { x: number; y: number; lat: number; lng: number };
type Camera = { x: number; y: number; w: number; h: number };

const WIDTH = 1000;
const HEIGHT = 580;
const DEFAULT_CAMERA = { x: 0, y: 0, w: WIDTH, h: HEIGHT };
const colors: Record<string, string> = {
  critical: "#ff6577",
  high: "#ffb35b",
  medium: "#f1d36d",
  low: "#6fe6ed",
  unknown: "#b9c5d4",
};

function position(entity: any): Point | null {
  const source =
    entity.coordinates ??
    entity.location?.coordinates ??
    entity.location ??
    entity;
  const latitude =
    source?.lat ??
    source?.latitude ??
    (Array.isArray(source) ? source[1] : undefined);
  const longitude =
    source?.lng ??
    source?.lon ??
    source?.longitude ??
    (Array.isArray(source) ? source[0] : undefined);
  if (
    latitude === undefined ||
    longitude === undefined ||
    String(latitude).trim() === "" ||
    String(longitude).trim() === ""
  )
    return null;
  const lat = Number(latitude);
  const lng = Number(longitude);
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lng) ||
    lat < -90 ||
    lat > 90 ||
    lng < -180 ||
    lng > 180
  )
    return null;
  return {
    lat,
    lng,
    x: ((lng - 88) / 1.2) * WIDTH,
    y: ((23.2 - lat) / 1.2) * HEIGHT,
  };
}

function band(entity: any): string {
  const value = String(
    entity.priority_band ??
      entity.priorityBand ??
      entity.priority?.band ??
      entity.priority ??
      "unknown",
  ).toLowerCase();
  return colors[value] ? value : "unknown";
}

function fitted(points: Point[]): Camera {
  if (!points.length) return DEFAULT_CAMERA;
  const minX = Math.min(...points.map((p) => p.x));
  const maxX = Math.max(...points.map((p) => p.x));
  const minY = Math.min(...points.map((p) => p.y));
  const maxY = Math.max(...points.map((p) => p.y));
  const w = Math.max(
    240,
    (maxX - minX) * 1.45,
    (maxY - minY) * 1.45 * (WIDTH / HEIGHT),
  );
  const h = w * (HEIGHT / WIDTH);
  return { x: (minX + maxX - w) / 2, y: (minY + maxY - h) / 2, w, h };
}

function line(coords: number[][]): string {
  return coords
    .map(([lng, lat]) => {
      const p = position({ lat, lng })!;
      return `${p.x},${p.y}`;
    })
    .join(" ");
}

const river = line([
  [88.44, 23.29],
  [88.39, 23.15],
  [88.37, 23.02],
  [88.34, 22.9],
  [88.4, 22.8],
  [88.36, 22.69],
  [88.31, 22.6],
  [88.29, 22.48],
  [88.22, 22.34],
  [88.19, 22.16],
  [88.15, 21.92],
]);
const roads = [
  [
    [88.18, 22.13],
    [88.29, 22.48],
    [88.35, 22.58],
    [88.43, 22.66],
    [88.49, 22.91],
    [88.53, 23.21],
  ],
  [
    [87.97, 22.67],
    [88.23, 22.62],
    [88.35, 22.58],
    [88.6, 22.56],
    [88.93, 22.55],
    [89.25, 22.7],
  ],
  [
    [88.31, 22.6],
    [88.39, 22.73],
    [88.58, 22.84],
    [88.8, 23.03],
    [89.11, 23.26],
  ],
  [
    [88.22, 23.24],
    [88.27, 22.97],
    [88.31, 22.76],
    [88.31, 22.6],
    [88.44, 22.33],
    [88.51, 21.99],
  ],
  [
    [88.01, 22.28],
    [88.29, 22.48],
    [88.57, 22.45],
    [88.86, 22.39],
    [89.23, 22.29],
  ],
];
const places = [
  { name: "KOLKATA", lat: 22.5726, lng: 88.3639, major: true },
  { name: "HOWRAH", lat: 22.5958, lng: 88.2636 },
  { name: "BARRACKPORE", lat: 22.766, lng: 88.378 },
  { name: "BARASAT", lat: 22.722, lng: 88.482 },
  { name: "SOUTH 24 PARGANAS", lat: 22.22, lng: 88.65 },
  { name: "NORTH 24 PARGANAS", lat: 22.94, lng: 88.72 },
];

export default function MapView({
  incidents = [],
  resources = [],
  focusId,
  onSelect,
  compact = false,
}: MapViewProps) {
  const [camera, setCamera] = useState<Camera>(DEFAULT_CAMERA);
  const [category, setCategory] = useState("all");
  const [priority, setPriority] = useState("all");
  const [showResources, setShowResources] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(focusId ?? null);
  const [dragging, setDragging] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    camera: Camera;
    moved: boolean;
  } | null>(null);
  const initialized = useRef(false);
  const lastFocused = useRef("");
  const mapId = useId().replaceAll(":", "");
  const points = useMemo(
    () => incidents.map((entity) => ({ entity, point: position(entity) })),
    [incidents],
  );
  const visible = points.filter(
    ({ entity }) =>
      (category === "all" || entity.category === category) &&
      (priority === "all" || band(entity) === priority),
  );
  const mapped = visible.filter((item) => item.point !== null) as {
    entity: any;
    point: Point;
  }[];
  const resourcePoints = resources
    .map((entity) => ({ entity, point: position(entity) }))
    .filter((item) => item.point !== null) as { entity: any; point: Point }[];
  const categories = [
    ...new Set(incidents.map((entity) => entity.category).filter(Boolean)),
  ] as string[];
  const selected = incidents.find((entity) => String(entity.id) === selectedId);
  const selectedPoint = selected ? position(selected) : null;
  const scale = camera.w / WIDTH;

  useEffect(() => {
    if (!initialized.current && points.some((item) => item.point)) {
      const valid = points.map((item) => item.point).filter(Boolean) as Point[];
      setCamera(fitted(valid));
      initialized.current = true;
    }
  }, [points]);

  useEffect(() => {
    if (!focusId) return;
    const target = points.find(
      (item) => String(item.entity.id) === focusId,
    )?.point;
    const focusKey = `${focusId}:${target?.lat}:${target?.lng}`;
    if (lastFocused.current === focusKey) return;
    lastFocused.current = focusKey;
    setSelectedId(focusId);
    if (target)
      setCamera({ x: target.x - 220, y: target.y - 127.6, w: 440, h: 255.2 });
  }, [focusId, points]);

  const zoom = (factor: number) =>
    setCamera((previous) => {
      const w = Math.max(90, Math.min(5000, previous.w * factor));
      const h = (w * HEIGHT) / WIDTH;
      return {
        x: previous.x + (previous.w - w) / 2,
        y: previous.y + (previous.h - h) / 2,
        w,
        h,
      };
    });

  const beginPan = (event: ReactPointerEvent<SVGSVGElement>) => {
    if ((event.target as Element).closest("[data-map-marker]")) return;
    drag.current = { x: event.clientX, y: event.clientY, camera, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pan = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const dx = event.clientX - drag.current.x;
    const dy = event.clientY - drag.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) {
      drag.current.moved = true;
      setDragging(true);
    }
    setCamera({
      ...drag.current.camera,
      x: drag.current.camera.x - (dx * drag.current.camera.w) / rect.width,
      y: drag.current.camera.y - (dy * drag.current.camera.h) / rect.height,
    });
  };
  const endPan = () => {
    drag.current = null;
    setDragging(false);
  };
  const select = (entity: any) => {
    setSelectedId(String(entity.id));
    onSelect?.(String(entity.id));
  };

  return (
    <div className={`ms-map${compact ? " ms-map--compact" : ""}`}>
      {!compact && (
        <div className="ms-map-filters">
          <label>
            Category
            <select
              aria-label="Filter map by category"
              value={category}
              onChange={(event) => {
                setCategory(event.target.value);
                setSelectedId(null);
              }}
            >
              <option value="all">All categories</option>
              {categories.map((value) => (
                <option key={value} value={value}>
                  {value.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Priority
            <select
              aria-label="Filter map by priority"
              value={priority}
              onChange={(event) => {
                setPriority(event.target.value);
                setSelectedId(null);
              }}
            >
              <option value="all">All priorities</option>
              {["critical", "high", "medium", "low"].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className={`ms-map-resource-toggle${showResources ? " is-active" : ""}`}
            aria-pressed={showResources}
            onClick={() => setShowResources((value) => !value)}
          >
            <Layers size={15} /> Resources
          </button>
          <span className="ms-map-filter-count">
            {mapped.length} mapped incident{mapped.length === 1 ? "" : "s"}
          </span>
        </div>
      )}
      <div className="ms-map-canvas">
        <div className="ms-map-location">
          <span className="ms-map-location-dot" />
          <span>
            OPERATIONAL AREA
            <span className="ms-map-location-sub">
              Geographic incident overview
            </span>
          </span>
        </div>
        <svg
          ref={svgRef}
          className={dragging ? "is-dragging" : ""}
          role="group"
          aria-label="Interactive schematic incident map. Drag to pan or use arrow keys; zoom controls are beside the map."
          tabIndex={0}
          viewBox={`${camera.x} ${camera.y} ${camera.w} ${camera.h}`}
          onPointerDown={beginPan}
          onPointerMove={pan}
          onPointerUp={endPan}
          onPointerCancel={endPan}
          onKeyDown={(event) => {
            if (event.target !== event.currentTarget) return;
            const amount = camera.w * 0.1;
            if (
              ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
                event.key,
              )
            ) {
              event.preventDefault();
              setCamera((previous) => ({
                ...previous,
                x:
                  previous.x +
                  (event.key === "ArrowLeft"
                    ? -amount
                    : event.key === "ArrowRight"
                      ? amount
                      : 0),
                y:
                  previous.y +
                  (event.key === "ArrowUp"
                    ? -amount
                    : event.key === "ArrowDown"
                      ? amount
                      : 0),
              }));
            }
            if (event.key === "+" || event.key === "=") {
              event.preventDefault();
              zoom(0.75);
            }
            if (event.key === "-") {
              event.preventDefault();
              zoom(1.333);
            }
          }}
        >
          <defs>
            <pattern
              id={`${mapId}-grid`}
              width="65"
              height="65"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 65 0 L 0 0 0 65"
                fill="none"
                stroke="#91a2b5"
                strokeOpacity=".065"
                strokeWidth="1"
              />
            </pattern>
            <pattern
              id={`${mapId}-fine-grid`}
              width="13"
              height="13"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 13 0 L 0 0 0 13"
                fill="none"
                stroke="#91a2b5"
                strokeOpacity=".025"
                strokeWidth=".5"
              />
            </pattern>
            <radialGradient id={`${mapId}-glow`}>
              <stop offset="0" stopColor="#244c55" stopOpacity=".4" />
              <stop offset="1" stopColor="#101c2b" stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect
            x={camera.x}
            y={camera.y}
            width={camera.w}
            height={camera.h}
            fill="#101c2b"
          />
          <rect
            x={camera.x}
            y={camera.y}
            width={camera.w}
            height={camera.h}
            fill={`url(#${mapId}-fine-grid)`}
          />
          <rect
            x={camera.x}
            y={camera.y}
            width={camera.w}
            height={camera.h}
            fill={`url(#${mapId}-grid)`}
          />
          <ellipse
            cx="380"
            cy="330"
            rx="510"
            ry="360"
            fill={`url(#${mapId}-glow)`}
          />
          <path
            d="M 35 50 L 250 28 L 410 100 L 390 230 L 530 300 L 740 285 L 850 410 L 760 530 L 410 555 L 215 420 L 50 370 Z"
            fill="#d0eadb"
            fillOpacity=".025"
            stroke="#88aaa6"
            strokeOpacity=".12"
            strokeWidth="1"
            strokeDasharray="6 7"
          />
          <path
            d="M 460 35 L 660 70 L 770 180 L 710 300 M 530 300 L 460 420 L 410 555 M 50 370 L 215 300 L 390 230"
            fill="none"
            stroke="#88aaa6"
            strokeOpacity=".12"
            strokeWidth="1"
            strokeDasharray="6 7"
          />
          <polyline
            points={river}
            stroke="#285967"
            strokeWidth="23"
            fill="none"
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity=".5"
          />
          <polyline
            points={river}
            stroke="#478493"
            strokeWidth="1"
            fill="none"
            strokeLinejoin="round"
            opacity=".4"
          />
          {roads.map((coords, index) => (
            <g key={index}>
              <polyline
                points={line(coords)}
                stroke="#080f1a"
                strokeWidth="6"
                fill="none"
                strokeLinejoin="round"
              />
              <polyline
                points={line(coords)}
                stroke="#425063"
                strokeWidth="2"
                fill="none"
                strokeLinejoin="round"
              />
            </g>
          ))}
          {places.map((place) => {
            const point = position(place)!;
            return (
              <text
                key={place.name}
                x={point.x}
                y={point.y - 13}
                textAnchor="middle"
                fill={place.major ? "#acbfce" : "#566e82"}
                fontFamily="inherit"
                fontSize={place.major ? 12 : 9}
                fontWeight={place.major ? 600 : 500}
                letterSpacing={place.major ? 3 : 1.7}
              >
                {place.name}
              </text>
            );
          })}
          <text
            x="225"
            y="155"
            fill="#497789"
            fontSize="9"
            letterSpacing="2"
            transform="rotate(68 225 155)"
          >
            HOOGHLY RIVER
          </text>
          {showResources &&
            resourcePoints.map(({ entity, point }) => (
              <g
                key={`resource-${entity.id}`}
                role="img"
                aria-label={`${entity.name ?? entity.type ?? "Resource"}, ${entity.status ?? "status unknown"}`}
                transform={`translate(${point.x},${point.y}) scale(${scale})`}
              >
                <title>
                  {entity.name ?? entity.type ?? "Resource"} ·{" "}
                  {entity.status ?? "Unknown"}
                </title>
                <rect
                  x="-5"
                  y="-5"
                  width="10"
                  height="10"
                  rx="2"
                  fill="#101c2b"
                  stroke="#8aa1b8"
                  strokeWidth="1.5"
                />
                <path
                  d="M -2 0 H 2 M 0 -2 V 2"
                  stroke="#8aa1b8"
                  strokeWidth="1"
                />
              </g>
            ))}
          {mapped.map(({ entity, point }) => {
            const color = colors[band(entity)];
            const active = String(entity.id) === selectedId;
            return (
              <g
                key={entity.id}
                data-map-marker="true"
                className="ms-map-marker"
                role="button"
                tabIndex={0}
                aria-label={`Select ${entity.title ?? entity.name ?? entity.id}, ${band(entity)} priority`}
                aria-pressed={active}
                onClick={(event) => {
                  event.stopPropagation();
                  select(entity);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    event.stopPropagation();
                    select(entity);
                  }
                }}
                transform={`translate(${point.x},${point.y}) scale(${scale})`}
              >
                <title>
                  {entity.title ?? entity.name ?? entity.id} · {band(entity)}{" "}
                  priority
                </title>
                <circle
                  r={active ? 20 : 17}
                  fill={color}
                  opacity={active ? 0.2 : 0.08}
                />
                <circle
                  r={active ? 13 : 11}
                  fill="none"
                  stroke={color}
                  strokeWidth="1"
                  opacity={active ? 0.9 : 0.28}
                />
                <circle r="6" fill={color} stroke="#101c2b" strokeWidth="2" />
                {active && (
                  <>
                    <path
                      d="M -27 0 H -21 M 21 0 H 27 M 0 -27 V -21 M 0 21 V 27"
                      stroke={color}
                      strokeWidth="1.5"
                    />
                    <circle
                      r="29"
                      fill="none"
                      stroke={color}
                      strokeOpacity=".3"
                      strokeDasharray="2 5"
                    />
                  </>
                )}
              </g>
            );
          })}
        </svg>
        <div className="ms-map-controls">
          <button
            type="button"
            aria-label="Zoom in"
            title="Zoom in"
            onClick={() => zoom(0.75)}
          >
            <Plus size={17} />
          </button>
          <button
            type="button"
            aria-label="Zoom out"
            title="Zoom out"
            onClick={() => zoom(1.333)}
          >
            <Minus size={17} />
          </button>
          <button
            type="button"
            aria-label="Fit map to filtered incidents"
            title="Fit to filtered incidents"
            onClick={() => setCamera(fitted(mapped.map((item) => item.point)))}
          >
            <LocateFixed size={17} />
          </button>
          {compact && (
            <button
              type="button"
              aria-label={showResources ? "Hide resources" : "Show resources"}
              aria-pressed={showResources}
              title="Toggle resources"
              onClick={() => setShowResources((value) => !value)}
            >
              <Layers size={17} />
            </button>
          )}
        </div>
        <div className="ms-map-compass" aria-hidden="true">
          <span>N</span>
          <Crosshair size={19} />
        </div>
        {selected && (
          <div className="ms-map-popup" aria-live="polite">
            <button
              type="button"
              className="ms-map-popup-close"
              aria-label="Close incident popup"
              onClick={() => setSelectedId(null)}
            >
              <X size={15} />
            </button>
            <div className="ms-map-popup-meta">
              <span style={{ color: colors[band(selected)] }}>
                {band(selected)} priority
              </span>
              <span>
                {String(selected.status ?? "Unknown status").replaceAll(
                  "_",
                  " ",
                )}
              </span>
            </div>
            <strong>{selected.title ?? selected.name ?? selected.id}</strong>
            <span className="ms-map-popup-coordinates">
              {selectedPoint
                ? `${Math.abs(selectedPoint.lat).toFixed(4)}° ${selectedPoint.lat < 0 ? "S" : "N"} · ${Math.abs(selectedPoint.lng).toFixed(4)}° ${selectedPoint.lng < 0 ? "W" : "E"}`
                : "Coordinates unavailable"}
            </span>
            <Link to={`/incidents/${selected.id}`}>
              View incident <span aria-hidden="true">↗</span>
            </Link>
          </div>
        )}
        {!mapped.length && (
          <div className="ms-map-empty">
            {visible.length
              ? "No valid coordinates for the selected incidents."
              : "No incidents match these filters."}
          </div>
        )}
        <div className="ms-map-legend">
          <span>
            <i style={{ background: colors.critical }} />
            Critical
          </span>
          <span>
            <i style={{ background: colors.high }} />
            High
          </span>
          <span>
            <i style={{ background: colors.medium }} />
            Medium
          </span>
          <span>
            <i style={{ background: colors.low }} />
            Low
          </span>
          {showResources && (
            <span>
              <i className="ms-map-legend-resource" />
              Resource
            </span>
          )}
        </div>
        <div className="ms-map-attribution">
          Schematic map · geographic coordinates · no live tiles
        </div>
      </div>
      {!compact && visible.length > mapped.length && (
        <p className="ms-map-coordinate-warning">
          {visible.length - mapped.length} incident
          {visible.length - mapped.length === 1 ? " has" : "s have"} missing or
          invalid coordinates and cannot be placed on the map.
        </p>
      )}
    </div>
  );
}
