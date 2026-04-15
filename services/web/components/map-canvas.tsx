export function MapCanvas() {
  return (
    <div className="map-canvas" aria-label="Static map placeholder">
      <div className="map-grid" />
      <div className="map-orbit map-orbit--one" />
      <div className="map-orbit map-orbit--two" />
      <div className="map-pulse map-pulse--one" />
      <div className="map-pulse map-pulse--two" />
      <div className="map-marker map-marker--site">
        <span className="map-marker__label">Site candidate</span>
      </div>
      <div className="map-marker map-marker--policy">
        <span className="map-marker__label">Policy layer</span>
      </div>
      <div className="map-marker map-marker--history">
        <span className="map-marker__label">Planning history</span>
      </div>
      <div className="map-legend">
        <span>MapLibre shell only</span>
        <span>EPSG:27700 ready later</span>
      </div>
    </div>
  );
}
