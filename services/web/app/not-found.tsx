import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="page-stack">
      <div className="page-head">
        <div>
          <div className="eyebrow">404</div>
          <h1 className="page-title">Surface not found</h1>
          <p className="page-summary">The route does not exist in the current shell. Return to listings or the control room.</p>
        </div>
      </div>
      <Link className="button button--solid" href="/">
        Return home
      </Link>
    </div>
  );
}
