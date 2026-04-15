'use client';

import maplibregl from 'maplibre-gl';
import type { CSSProperties } from 'react';
import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';

import type { SiteSummary } from '@/lib/landintel-api';

import styles from './site-map.module.css';

type SiteMapProps = {
  sites: SiteSummary[];
  selectedSiteId?: string;
  className?: string;
  height?: number;
};

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

const polygonGeometryFilter = [
  'any',
  ['==', ['geometry-type'], 'Polygon'],
  ['==', ['geometry-type'], 'MultiPolygon']
] as const;

function confidenceTone(confidence: SiteSummary['geometry_confidence']): string {
  if (confidence === 'HIGH') {
    return '#1f6a4a';
  }

  if (confidence === 'MEDIUM') {
    return '#a46b1c';
  }

  if (confidence === 'LOW') {
    return '#a05555';
  }

  return '#7b6d5f';
}

function toFeatureCollection(sites: SiteSummary[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: sites.map((site) => ({
      type: 'Feature' as const,
      properties: {
        site_id: site.site_id,
        display_name: site.display_name,
        confidence: site.geometry_confidence,
        warnings: site.warnings.join(' | ')
      },
      geometry: site.geometry_geojson_4326.geometry as GeoJSON.Geometry
    })) as GeoJSON.Feature[]
  };
}

function geometryPoints(geometry: GeoJSON.Geometry): Array<[number, number]> {
  switch (geometry.type) {
    case 'Point':
      return [geometry.coordinates as [number, number]];
    case 'MultiPoint':
      return geometry.coordinates as Array<[number, number]>;
    case 'LineString':
      return geometry.coordinates as Array<[number, number]>;
    case 'MultiLineString':
      return (geometry.coordinates as Array<Array<[number, number]>>).flat();
    case 'Polygon':
      return (geometry.coordinates as Array<Array<[number, number]>>).flat();
    case 'MultiPolygon':
      return (geometry.coordinates as Array<Array<Array<[number, number]>>>).flat(2);
    default:
      return [];
  }
}

function fitToSites(map: maplibregl.Map, sites: SiteSummary[]): void {
  const points = sites.flatMap((site) => geometryPoints(site.geometry_geojson_4326.geometry));

  if (points.length === 0) {
    return;
  }

  const bounds = points.reduce(
    (acc, point) => acc.extend(point as [number, number]),
    new maplibregl.LngLatBounds(points[0] as [number, number], points[0] as [number, number])
  );

  map.fitBounds(bounds, { padding: 40, duration: 0 });
}

export function SiteMap({ sites, selectedSiteId, className, height = 460 }: SiteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const router = useRouter();

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
      map.addSource('sites', {
        type: 'geojson',
        data: toFeatureCollection(sites) as unknown as GeoJSON.FeatureCollection,
        promoteId: 'site_id'
      });

      map.addLayer({
        id: 'sites-fill',
        type: 'fill',
        source: 'sites',
        filter: polygonGeometryFilter as unknown as maplibregl.FilterSpecification,
        paint: {
          'fill-color': [
            'case',
            ['==', ['get', 'confidence'], 'HIGH'],
            confidenceTone('HIGH'),
            ['==', ['get', 'confidence'], 'MEDIUM'],
            confidenceTone('MEDIUM'),
            ['==', ['get', 'confidence'], 'LOW'],
            confidenceTone('LOW'),
            confidenceTone('INSUFFICIENT')
          ],
          'fill-opacity': 0.28
        }
      });

      map.addLayer({
        id: 'sites-outline',
        type: 'line',
        source: 'sites',
        filter: polygonGeometryFilter as unknown as maplibregl.FilterSpecification,
        paint: {
          'line-color': '#20303a',
          'line-width': 1.4
        }
      });

      map.addLayer({
        id: 'sites-point',
        type: 'circle',
        source: 'sites',
        filter: ['==', ['geometry-type'], 'Point'] as unknown as maplibregl.FilterSpecification,
        paint: {
          'circle-color': '#20303a',
          'circle-radius': 6,
          'circle-stroke-color': '#fff7eb',
          'circle-stroke-width': 2
        }
      });

      map.addLayer({
        id: 'sites-label',
        type: 'symbol',
        source: 'sites',
        layout: {
          'text-field': ['get', 'display_name'],
          'text-size': 11,
          'text-offset': [0, 1.1],
          'text-anchor': 'top',
          'text-variable-anchor': ['top', 'bottom'],
          'text-allow-overlap': false
        },
        paint: {
          'text-color': '#18222a',
          'text-halo-color': 'rgba(255, 250, 242, 0.95)',
          'text-halo-width': 1.4
        }
      });

      map.addLayer({
        id: 'sites-selected-fill',
        type: 'fill',
        source: 'sites',
        filter: [
          'all',
          polygonGeometryFilter,
          ['==', ['get', 'site_id'], selectedSiteId ?? '__none__']
        ] as unknown as maplibregl.FilterSpecification,
        paint: {
          'fill-color': '#0f6d57',
          'fill-opacity': 0.38
        }
      });

      map.addLayer({
        id: 'sites-selected-outline',
        type: 'line',
        source: 'sites',
        filter: [
          'all',
          polygonGeometryFilter,
          ['==', ['get', 'site_id'], selectedSiteId ?? '__none__']
        ] as unknown as maplibregl.FilterSpecification,
        paint: {
          'line-color': '#0f6d57',
          'line-width': 3
        }
      });

      map.addLayer({
        id: 'sites-selected-point',
        type: 'circle',
        source: 'sites',
        filter: [
          'all',
          ['==', ['geometry-type'], 'Point'],
          ['==', ['get', 'site_id'], selectedSiteId ?? '__none__']
        ] as unknown as maplibregl.FilterSpecification,
        paint: {
          'circle-color': '#0f6d57',
          'circle-radius': 8,
          'circle-stroke-color': '#fff7eb',
          'circle-stroke-width': 2
        }
      });

      fitToSites(map, sites);
      mapRef.current = map;
      const onClick = (event: maplibregl.MapLayerMouseEvent): void => {
        const feature = event.features?.[0];
        const siteId = feature?.properties?.site_id;
        if (typeof siteId === 'string') {
          router.push(`/sites/${encodeURIComponent(siteId)}`);
        }
      };

      map.on('click', 'sites-fill', onClick);
      map.on('click', 'sites-outline', onClick);
      map.on('click', 'sites-point', onClick);

      map.on('mouseenter', 'sites-fill', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'sites-fill', () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('mouseenter', 'sites-outline', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'sites-outline', () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('mouseenter', 'sites-point', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'sites-point', () => {
        map.getCanvas().style.cursor = '';
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [router, sites, selectedSiteId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }

    const source = map.getSource('sites') as maplibregl.GeoJSONSource | undefined;
    source?.setData(toFeatureCollection(sites) as never);

    const selectedFilter = ['==', ['get', 'site_id'], selectedSiteId ?? '__none__'] as const;
    map.setFilter(
      'sites-selected-fill',
      [
        'all',
        polygonGeometryFilter,
        selectedFilter
      ] as never
    );
    map.setFilter(
      'sites-selected-outline',
      [
        'all',
        polygonGeometryFilter,
        selectedFilter
      ] as never
    );
    map.setFilter(
      'sites-selected-point',
      ['all', ['==', ['geometry-type'], 'Point'], selectedFilter] as never
    );
    fitToSites(map, sites);
  }, [sites, selectedSiteId]);

  const shellStyle = { minHeight: `${height}px` } as CSSProperties;

  return (
    <div className={[styles.shell, className].filter(Boolean).join(' ')} style={shellStyle}>
      <div className={styles.map} ref={containerRef} />
      <div className={styles.overlay}>
        <div className={styles.card}>
          <div className={styles.label}>MapLibre / EPSG:4326 display only</div>
          <div className={styles.help}>Click a candidate to open the site detail. Geometry remains clearly labelled as evidence.</div>
        </div>
        <div className={styles.card}>
          <div className={styles.label}>Confidence legend</div>
          <div className={styles.legendRow}>
            <span className={styles.legendItem} style={{ color: confidenceTone('HIGH') }}>
              HIGH
            </span>
            <span className={styles.legendItem} style={{ color: confidenceTone('MEDIUM') }}>
              MEDIUM
            </span>
            <span className={styles.legendItem} style={{ color: confidenceTone('LOW') }}>
              LOW
            </span>
            <span className={styles.legendItem} style={{ color: confidenceTone('INSUFFICIENT') }}>
              INSUFFICIENT
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
