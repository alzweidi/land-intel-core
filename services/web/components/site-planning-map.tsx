'use client';

import maplibregl from 'maplibre-gl';
import { useEffect, useRef } from 'react';

import type {
  ConstraintFactRecord,
  GeometryFeature,
  PlanningHistoryRecord,
  PolicyFactRecord,
  SiteDetail
} from '@/lib/landintel-api';

import styles from './site-map.module.css';

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

function toFeatureCollection(
  features: GeometryFeature[],
  kind: string
): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: features.map((feature, index) => ({
      type: 'Feature' as const,
      id: `${kind}-${index}`,
      properties: {
        kind
      },
      geometry: feature.geometry as GeoJSON.Geometry
    }))
  };
}

function planningFeatures(records: PlanningHistoryRecord[]): GeometryFeature[] {
  return records
    .map((record) => record.planning_application.site_geom_4326 ?? record.planning_application.site_point_4326)
    .filter((feature): feature is GeometryFeature => feature !== null);
}

function policyFeatures(records: PolicyFactRecord[]): GeometryFeature[] {
  return records.map((record) => record.policy_area.geom_4326);
}

function constraintFeatures(records: ConstraintFactRecord[]): GeometryFeature[] {
  return records.map((record) => record.constraint_feature.geom_4326);
}

export function SitePlanningMap({ site }: { site: SiteDetail }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: RASTER_STYLE as unknown as maplibregl.StyleSpecification,
      center: [site.centroid_4326.lon, site.centroid_4326.lat],
      zoom: 14,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false
    });

    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();

    map.on('load', () => {
      const siteCollection = toFeatureCollection([site.geometry_geojson_4326], 'site');
      const planningCollection = toFeatureCollection(
        planningFeatures(site.planning_history ?? []),
        'planning'
      );
      const policyCollection = toFeatureCollection(policyFeatures(site.policy_facts ?? []), 'policy');
      const constraintCollection = toFeatureCollection(
        constraintFeatures(site.constraint_facts ?? []),
        'constraint'
      );

      map.addSource('site', { type: 'geojson', data: siteCollection });
      map.addSource('planning', { type: 'geojson', data: planningCollection });
      map.addSource('policy', { type: 'geojson', data: policyCollection });
      map.addSource('constraint', { type: 'geojson', data: constraintCollection });

      map.addLayer({
        id: 'policy-fill',
        type: 'fill',
        source: 'policy',
        paint: {
          'fill-color': '#5e8d55',
          'fill-opacity': 0.18
        }
      });
      map.addLayer({
        id: 'constraint-fill',
        type: 'fill',
        source: 'constraint',
        paint: {
          'fill-color': '#b06a52',
          'fill-opacity': 0.18
        }
      });
      map.addLayer({
        id: 'planning-fill',
        type: 'fill',
        source: 'planning',
        paint: {
          'fill-color': '#4e82b4',
          'fill-opacity': 0.2
        }
      });
      map.addLayer({
        id: 'site-fill',
        type: 'fill',
        source: 'site',
        paint: {
          'fill-color': '#0f6d57',
          'fill-opacity': 0.24
        }
      });
      map.addLayer({
        id: 'policy-outline',
        type: 'line',
        source: 'policy',
        paint: {
          'line-color': '#6fa75d',
          'line-width': 1.5
        }
      });
      map.addLayer({
        id: 'constraint-outline',
        type: 'line',
        source: 'constraint',
        paint: {
          'line-color': '#d08260',
          'line-width': 1.4
        }
      });
      map.addLayer({
        id: 'planning-outline',
        type: 'line',
        source: 'planning',
        paint: {
          'line-color': '#7fb1df',
          'line-width': 1.4
        }
      });
      map.addLayer({
        id: 'site-outline',
        type: 'line',
        source: 'site',
        paint: {
          'line-color': '#1ce0af',
          'line-width': 2.8
        }
      });
      map.addLayer({
        id: 'planning-points',
        type: 'circle',
        source: 'planning',
        filter: ['==', ['geometry-type'], 'Point'] as unknown as maplibregl.FilterSpecification,
        paint: {
          'circle-color': '#7fb1df',
          'circle-radius': 6,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2
        }
      });
      map.addLayer({
        id: 'constraint-points',
        type: 'circle',
        source: 'constraint',
        filter: ['==', ['geometry-type'], 'Point'] as unknown as maplibregl.FilterSpecification,
        paint: {
          'circle-color': '#d08260',
          'circle-radius': 6,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2
        }
      });

      const allPoints = [
        ...geometryPoints(site.geometry_geojson_4326.geometry as GeoJSON.Geometry),
        ...planningCollection.features.flatMap((feature) => geometryPoints(feature.geometry)),
        ...policyCollection.features.flatMap((feature) => geometryPoints(feature.geometry)),
        ...constraintCollection.features.flatMap((feature) => geometryPoints(feature.geometry))
      ];

      if (allPoints.length > 0) {
        const bounds = allPoints.reduce(
          (acc, point) => acc.extend(point),
          new maplibregl.LngLatBounds(allPoints[0], allPoints[0])
        );
        map.fitBounds(bounds, { padding: 40, duration: 0 });
      }
      mapRef.current = map;
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [site]);

  return (
    <div className={styles.shell} style={{ minHeight: 420 }}>
      <div className={styles.map} ref={containerRef} />
      <div className={styles.overlay}>
        <div className={styles.card}>
          <div className={styles.label}>Planning Context</div>
          <div className={styles.help}>
            Site geometry is shown in teal. Policy areas, planning history, and constraint layers are
            overlays only and do not imply authoritative legal boundaries.
          </div>
          <div className={styles.legendRow}>
            <span className={styles.legendItem}>Site</span>
            <span className={styles.legendItem}>Planning</span>
            <span className={styles.legendItem}>Policy</span>
            <span className={styles.legendItem}>Constraints</span>
          </div>
        </div>
        <div className={styles.card}>
          <div className={styles.label}>Counts</div>
          <div className={styles.help}>
            {(site.planning_history ?? []).length} planning records
            <br />
            {(site.policy_facts ?? []).length} policy overlays
            <br />
            {(site.constraint_facts ?? []).length} constraint overlays
          </div>
        </div>
      </div>
    </div>
  );
}
