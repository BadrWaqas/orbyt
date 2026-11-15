import { useFields, useManifest } from "../data/findings";
import { NO2_ATTRIBUTION } from "../modules/pollution-hunter/no2";

const BASE = "/data/v1/pollution-hunter";

const DOWNLOADS = [
  { href: `${BASE}/findings.csv`, name: "findings.csv", text: "One row per facility, for spreadsheets." },
  { href: `${BASE}/findings.parquet`, name: "findings.parquet", text: "The same rows, for DuckDB, pandas and R." },
  { href: `${BASE}/findings.json`, name: "findings.json", text: "The file the globe and the leaderboard read." },
  { href: "/data/v1/manifest.json", name: "manifest.json", text: "Data version, method version and build time." },
];

function Fields() {
  const fields = useFields();
  if (fields.status === "loading") return <p className="text-text-3">Loading the field list.</p>;
  if (fields.status === "error") {
    return (
      <p>
        Could not load the field list.{" "}
        <button type="button" className="text-button underline underline-offset-4" onClick={fields.retry}>
          Try again
        </button>
      </p>
    );
  }
  return (
    <table className="fields">
      <caption className="sr-only">Columns of findings.csv and findings.parquet</caption>
      <thead>
        <tr>
          <th scope="col">Column</th>
          <th scope="col">What it holds</th>
        </tr>
      </thead>
      <tbody>
        {fields.data.map((f) => (
          <tr key={f.name}>
            <th scope="row">{f.name}</th>
            <td className="text-text-2">{f.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The /data page: the files behind every number, and what each column means. */
export function DataBody() {
  const manifest = useManifest();
  const module = manifest.status === "ready" ? manifest.data.modules[0] : null;
  return (
    <>
      <p>
        Every number on Orbyt Earth is in a file you can download and check. The files are plain and
        open, and you can use them for anything, with the credit under &quot;Sources&quot; below.
      </p>
      {manifest.status === "ready" && module && (
        <p className="text-[14px] leading-5 text-text-3">
          Data version {manifest.data.data_version}, method {module.method_version}, built{" "}
          {manifest.data.built_at.slice(0, 10)}.
        </p>
      )}

      <h2>Downloads</h2>
      <ul className="download-list">
        {DOWNLOADS.map((d) => (
          <li key={d.name}>
            <a href={d.href} download>
              {d.name}
              <span>{d.text}</span>
            </a>
          </li>
        ))}
      </ul>
      <p>
        Each facility with a satellite estimate also has a detail file, at{" "}
        <code>{BASE}/finding/&lt;finding_id&gt;.json</code>. It holds the stacked curve, the daily
        detections and the rolling estimates.
      </p>

      <h2>Columns</h2>
      <p>
        There is one row for each facility and year. A blank cell means the value does not exist,
        for example no estimate where the quality checks failed. Tonnes are NOx expressed as NO
        <sub>2</sub> mass. Intervals marked &quot;sampling&quot; cover the noise from the days used and
        not the systematic uncertainty.
      </p>
      <Fields />

      <h2>Sources</h2>
      <ul>
        <li>Satellite NO<sub>2</sub>: {NO2_ATTRIBUTION}.</li>
        <li>Reported emissions, Europe: EEA Industrial Reporting database, under the EEA&apos;s open data terms.</li>
        <li>US stack monitors: EPA Clean Air Markets Program Data, a US government work in the public domain.</li>
        <li>Wind: ERA5 hourly, Copernicus Climate Change Service.</li>
      </ul>
      <p>
        Estimates are uncertain and are not findings of non-compliance. How they are made is on the{" "}
        <a className="nav-link" href="/method">
          method page
        </a>
        .
      </p>
    </>
  );
}
