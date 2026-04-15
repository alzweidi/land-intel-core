'use client';

import maplibregl from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import {
  saveSiteGeometry,
  type GeometryConfidence,
  type GeometryFeature,
  type GeometrySourceType,
  type SiteDetail
} from '@/lib/landintel-api';

import styles from './site-geometry-editor.module.css';

type Ring = Array<[number, number]>;

type SiteGeometryEditorProps = {
  site: SiteDetail;
};

type SiteRevision = SiteDetail['revision_history'][number];

const RASTER_STYLE = {
  version: 8,
  sources: {
    basemap: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors'
    }
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: {
        'background-color': '#d7d0c4'
      }
    },
    {
      id: 'basemap',
      type: 'raster',
      source: 'basemap'
    }
  ]
} as const;

function currentRevision(site: SiteDetail): SiteRevision {
  const revision = site.revision_history.find((item) => item.is_current) ?? site.revision_history[0];
  if (!revision) {
    throw new Error(`Site ${site.site_id} has no geometry revision`);
  }

  return revision;
}

function extractVertices(site: SiteDetail): Ring {
  const revision = currentRevision(site);
  const geometry = revision?.geometry_geojson_4326.geometry ?? site.geometry_geojson_4326.geometry;

  if (geometry.type === 'Polygon') {
    const ring = geometry.coordinates[0] ?? [];
    return ring.slice(0, Math.max(0, ring.length - 1)) as Ring;
  }

  if (geometry.type === 'MultiPolygon') {
    const polygon = geometry.coordinates[0] ?? [];
    const ring = polygon[0] ?? [];
    return ring.slice(0, Math.max(0, ring.length - 1)) as Ring;
  }

  return [];
}

function closeRing(vertices: Ring): number[][][] {
  if (vertices.length < 3) {
    return [[]];
  }

  const closed = [...vertices, vertices[0]];
  return [closed];
}

function createPolygonGeometry(site: SiteDetail, vertices: Ring): GeometryFeature | null {
  if (vertices.length < 3) {
    return null;
  }

  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: closeRing(vertices) as number[][][]
    },
    properties: {
      site_id: site.site_id,
      editor: 'phase2'
    }
  };
}

function geoJsonString(feature: GeometryFeature | null): string {
  return JSON.stringify(feature, null, 2);
}

function parseGeoJson(value: string): Ring | null {
  try {
    const parsed = JSON.parse(value) as GeometryFeature | { type?: string; geometry?: { type?: string; coordinates?: unknown } };
    if (!parsed || parsed.type !== 'Feature' || !parsed.geometry || parsed.geometry.type !== 'Polygon') {
      return null;
    }

    const coordinates = parsed.geometry.coordinates;
    if (!Array.isArray(coordinates) || !Array.isArray(coordinates[0])) {
      return null;
    }

    const ring = coordinates[0]
      .map((point) => {
        if (!Array.isArray(point) || point.length < 2) {
          return null;
        }

        const [lon, lat] = point;
        if (typeof lon !== 'number' || typeof lat !== 'number') {
          return null;
        }

        return [lon, lat] as [number, number];
      })
      .filter((point): point is [number, number] => Boolean(point));

    if (ring.length < 3) {
      return null;
    }

    return ring.slice(0, -1);
  } catch {
    return null;
  }
}

function pointCollection(vertices: Ring): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: 'FeatureCollection',
    features: vertices.map((point, index) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: point
      },
      properties: {
        index: index + 1
      }
    }))
  };
}

function lineCollection(vertices: Ring): GeoJSON.FeatureCollection<GeoJSON.LineString> {
  return {
    type: 'FeatureCollection',
    features:
      vertices.length >= 2
        ? [
            {
              type: 'Feature',
              geometry: {
                type: 'LineString',
                coordinates: vertices
              },
              properties: {}
            }
          ]
        : []
  };
}

function polygonCollection(feature: GeometryFeature | null): GeoJSON.FeatureCollection<GeoJSON.Geometry> {
  if (!feature) {
    return { type: 'FeatureCollection', features: [] };
  }

  return {
    type: 'FeatureCollection',
    features: [feature as unknown as GeoJSON.Feature<GeoJSON.Geometry>]
  };
}

function fitToGeometry(map: maplibregl.Map, feature: GeometryFeature | null): void {
  if (!feature) {
    return;
  }

  const geometry = feature.geometry;
  const points =
    geometry.type === 'Point'
      ? [geometry.coordinates]
      : geometry.type === 'Polygon'
        ? geometry.coordinates.flat()
        : geometry.coordinates.flatMap((polygon) => polygon.flat());

  if (points.length === 0) {
    return;
  }

  const bounds = points.reduce(
    (acc, point) => {
      const [lon, lat] = point;
      return acc.extend([lon, lat]);
    },
    new maplibregl.LngLatBounds(points[0] as [number, number], points[0] as [number, number])
  );

  map.fitBounds(bounds, { padding: 40, duration: 0 });
}

export function SiteGeometryEditor({ site }: SiteGeometryEditorProps) {
  const [siteState, setSiteState] = useState(site);
  const [vertices, setVertices] = useState<Ring>(() => extractVertices(site));
  const [geometryText, setGeometryText] = useState(() => geoJsonString(createPolygonGeometry(site, extractVertices(site))));
  const [sourceType, setSourceType] = useState<GeometrySourceType>(currentRevision(site).geom_source_type);
  const [confidence, setConfidence] = useState<GeometryConfidence>(currentRevision(site).geom_confidence);
  const [note, setNote] = useState(currentRevision(site).note);
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [message, setMessage] = useState<string>('');
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const siteStateRef = useRef(siteState);
  const verticesRef = useRef(vertices);

  useEffect(() => {
    siteStateRef.current = siteState;
    verticesRef.current = vertices;
  }, [siteState, vertices]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: RASTER_STYLE as unknown as maplibregl.StyleSpecification,
      center: [-0.1, 51.5],
      zoom: 10.4,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchZoomRotate: true
    });

    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();

    map.on('load', () => {
      const initialSite = siteStateRef.current;
      const initialVertices = verticesRef.current;

      map.addSource('current', {
        type: 'geojson',
        data: polygonCollection(initialSite.geometry_geojson_4326)
      });
      map.addSource('draft-fill', {
        type: 'geojson',
        data: polygonCollection(createPolygonGeometry(initialSite, initialVertices))
      });
      map.addSource('draft-line', {
        type: 'geojson',
        data: lineCollection(initialVertices)
      });
      map.addSource('draft-points', {
        type: 'geojson',
        data: pointCollection(initialVertices)
      });

      map.addLayer({
        id: 'current-fill',
        type: 'fill',
        source: 'current',
        paint: {
          'fill-color': '#0f6d57',
          'fill-opacity': 0.16
        }
      });

      map.addLayer({
        id: 'current-outline',
        type: 'line',
        source: 'current',
        paint: {
          'line-color': '#0f6d57',
          'line-width': 1.6
        }
      });

      map.addLayer({
        id: 'current-point',
        type: 'circle',
        source: 'current',
        paint: {
          'circle-color': '#0f6d57',
          'circle-radius': 6,
          'circle-stroke-color': '#fff7eb',
          'circle-stroke-width': 2
        }
      });

      map.addLayer({
        id: 'draft-fill',
        type: 'fill',
        source: 'draft-fill',
        paint: {
          'fill-color': '#a46b1c',
          'fill-opacity': 0.26
        }
      });

      map.addLayer({
        id: 'draft-outline',
        type: 'line',
        source: 'draft-fill',
        paint: {
          'line-color': '#a46b1c',
          'line-width': 2.4
        }
      });

      map.addLayer({
        id: 'draft-line',
        type: 'line',
        source: 'draft-line',
        paint: {
          'line-color': '#20303a',
          'line-width': 2,
          'line-dasharray': [1.2, 0.8]
        }
      });

      map.addLayer({
        id: 'draft-points',
        type: 'circle',
        source: 'draft-points',
        paint: {
          'circle-color': '#f4a945',
          'circle-radius': 5,
          'circle-stroke-color': '#18222a',
          'circle-stroke-width': 1.3
        }
      });

      fitToGeometry(map, createPolygonGeometry(initialSite, initialVertices));
      mapRef.current = map;
    });

    map.on('click', (event) => {
      const currentSite = siteStateRef.current;
      setVertices((currentVertices) => {
        const nextVertices = [...currentVertices, [event.lngLat.lng, event.lngLat.lat] as [number, number]];
        setGeometryText(geoJsonString(createPolygonGeometry(currentSite, nextVertices)));
        return nextVertices;
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }

    const currentSource = map.getSource('current') as maplibregl.GeoJSONSource | undefined;
    currentSource?.setData(polygonCollection(siteState.geometry_geojson_4326) as never);

    const draftFeature = createPolygonGeometry(siteState, vertices);
    const draftFill = map.getSource('draft-fill') as maplibregl.GeoJSONSource | undefined;
    const draftLine = map.getSource('draft-line') as maplibregl.GeoJSONSource | undefined;
    const draftPoints = map.getSource('draft-points') as maplibregl.GeoJSONSource | undefined;

    draftFill?.setData(polygonCollection(draftFeature) as never);
    draftLine?.setData(lineCollection(vertices) as never);
    draftPoints?.setData(pointCollection(vertices) as never);
  }, [siteState, vertices]);

  function resetToCurrent(): void {
    const nextVertices = extractVertices(siteState);
    setVertices(nextVertices);
    setGeometryText(geoJsonString(createPolygonGeometry(siteState, nextVertices)));
    setSourceType(currentRevision(siteState).geom_source_type);
    setConfidence(currentRevision(siteState).geom_confidence);
    setNote(currentRevision(siteState).note);
    setStatus('idle');
    setMessage('Reset to the current saved revision.');
  }

  function clearDraft(): void {
    setVertices([]);
    setGeometryText(geoJsonString(null));
    setStatus('idle');
    setMessage('Draft cleared.');
  }

  function applyGeoJsonText(): void {
    const parsed = parseGeoJson(geometryText);
    if (!parsed) {
      setStatus('error');
      setMessage('GeoJSON text must be a Polygon feature with at least three vertices.');
      return;
    }

    setVertices(parsed);
    setGeometryText(geoJsonString(createPolygonGeometry(siteState, parsed)));
    setStatus('idle');
    setMessage('Loaded draft geometry from GeoJSON text.');
  }

  async function handleSave(): Promise<void> {
    const geometry = createPolygonGeometry(siteState, vertices);
    if (!geometry) {
      setStatus('error');
      setMessage('Add at least three vertices before saving a revision.');
      return;
    }

    setStatus('saving');
    setMessage('Saving geometry revision...');

    const result = await saveSiteGeometry(siteState.site_id, {
      geometry_geojson_4326: geometry,
      geom_source_type: sourceType,
      geom_confidence: confidence,
      revision_note: note
    });

    if (result.item) {
      setSiteState(result.item);
      setVertices(extractVertices(result.item));
      setGeometryText(geoJsonString(createPolygonGeometry(result.item, extractVertices(result.item))));
      setSourceType(currentRevision(result.item).geom_source_type);
      setConfidence(currentRevision(result.item).geom_confidence);
      setNote(currentRevision(result.item).note);
      setStatus('saved');
      setMessage(
        result.apiAvailable
          ? 'Saved to the API-backed site revision history.'
          : 'Saved against the local preview fallback because the API was unavailable.'
      );
      return;
    }

    setStatus('error');
    setMessage('Save failed: no site record was available.');
  }

  const currentRevisionSummary = currentRevision(siteState);

  return (
    <section className={styles.shell}>
      <div className={styles.header}>
        <div>
          <div className={styles.label}>Geometry editor</div>
          <h3 className={styles.title}>{siteState.display_name}</h3>
        </div>
        <div className={styles.badges}>
          <span className={styles.badge}>Source {currentRevisionSummary.geom_source_type}</span>
          <span className={styles.badge}>Confidence {currentRevisionSummary.geom_confidence}</span>
          <span className={styles.badge}>{siteState.site_area_sqm === null ? 'Area pending' : `${siteState.site_area_sqm.toLocaleString('en-GB')} sqm`}</span>
        </div>
      </div>

      <div className={styles.mapShell}>
        <div className={styles.map} ref={containerRef} />
        <div className={styles.mapNote}>
          Click the map to add vertices. Keep the draft conservative and use the text box when you need exact vertex control.
        </div>
      </div>

      <div className={styles.formGrid}>
        <label className={styles.field}>
          <span>Geometry source type</span>
          <select value={sourceType} onChange={(event) => setSourceType(event.target.value as GeometrySourceType)}>
            <option value="SOURCE_POLYGON">SOURCE_POLYGON</option>
            <option value="SOURCE_MAP_DIGITISED">SOURCE_MAP_DIGITISED</option>
            <option value="TITLE_UNION">TITLE_UNION</option>
            <option value="ANALYST_DRAWN">ANALYST_DRAWN</option>
            <option value="APPROXIMATE_BBOX">APPROXIMATE_BBOX</option>
            <option value="POINT_ONLY">POINT_ONLY</option>
          </select>
        </label>
        <label className={styles.field}>
          <span>Geometry confidence</span>
          <select value={confidence} onChange={(event) => setConfidence(event.target.value as GeometryConfidence)}>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
            <option value="INSUFFICIENT">INSUFFICIENT</option>
          </select>
        </label>
        <label className={styles.fieldWide}>
          <span>Revision note</span>
          <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Explain why the geometry changed" />
        </label>
      </div>

      <div className={styles.editorGrid}>
        <label className={styles.fieldWide}>
          <span>Draft GeoJSON</span>
          <textarea value={geometryText} onChange={(event) => setGeometryText(event.target.value)} />
        </label>
        <div className={styles.actions}>
          <button className="button button--ghost" type="button" onClick={resetToCurrent}>
            Reset to current
          </button>
          <button className="button button--ghost" type="button" onClick={clearDraft}>
            Clear draft
          </button>
          <button className="button button--ghost" type="button" onClick={applyGeoJsonText}>
            Load GeoJSON
          </button>
          <button className="button button--solid" type="button" onClick={handleSave} disabled={status === 'saving'}>
            Save revision
          </button>
        </div>
      </div>

      <div className={styles.footer}>
        <div className={styles.status} data-status={status}>
          {message || 'Ready.'}
        </div>
        <div className={styles.statusHint}>
          The saved revision is visible immediately, but the page still labels the geometry as evidence, not authority.
        </div>
      </div>
    </section>
  );
}
