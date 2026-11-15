/** The /method page, in plain words. The full constants and their sources are in METHODS.md. */
export const METHOD_STEPS = [
  {
    title: "Collect the clear, windy days",
    text: "The Sentinel-5P satellite passes over each source about once a day, around 13:30 local time. We keep the passes where the sky is clear and the wind is at least 2 metres a second, so the plume has a clear direction.",
  },
  {
    title: "Turn every day to face the same way",
    text: "Each day's image is rotated so the wind blows from left to right, and distance from the source becomes travel time downwind. Every day then shares one clock.",
  },
  {
    title: "Average the days",
    text: "Averaging cancels the noise. What is left is one curve: it rises at the source and fades downwind as the NO2 breaks down.",
  },
  {
    title: "Fit the curve",
    text: "A standard curve (an exponentially modified Gaussian) is fitted to it. Its height gives the emission rate. Its decay gives the lifetime of NO2 in the plume, a check that the shape is physical.",
  },
  {
    title: "Convert and add the uncertainty",
    text: "NO2 is converted to NOx and corrected for the satellite reading low near point sources, with constants from the published literature. The days are then resampled 200 times to get an interval. A systematic uncertainty of 35%, measured against US stack monitors, is added before any verdict.",
  },
] as const;

export function MethodBody() {
  return (
    <>
      <p>
        Every satellite estimate on Orbyt Earth comes from the same method, version ph-emg-1.1. It
        estimates the NOx a source released in a year, in tonnes as NO<sub>2</sub> mass, the same
        convention as the European register and the US stack monitors. It is an estimate from clear,
        windy middays. It is not the annual total, and it says nothing about permits or compliance.
      </p>

      <h2>Five steps</h2>
      <ol>
        {METHOD_STEPS.map((s) => (
          <li key={s.title}>
            <strong className="text-text">{s.title}.</strong> {s.text}
          </li>
        ))}
      </ol>

      <h2>When we say nothing</h2>
      <p>An estimate has to pass five quality checks. If it fails any of them it is shown as inconclusive, never as a number.</p>
      <ul>
        <li>At least 40 usable days.</li>
        <li>The curve fits the data well.</li>
        <li>The plume starts at the plant, within half an hour of travel time.</li>
        <li>The lifetime is physical, between 1 and 8 hours.</li>
        <li>The signal is at least three times the noise.</li>
      </ul>
      <p>
        We also choose sources with care. A source is dropped if a second large source or a big city
        sits close enough to blur the plume, or if a nearby hotspot of NO<sub>2</sub> would be mistaken
        for it. A source that fails only the second-source check is kept as a cluster, compared with
        the total of everything the register lists inside 20 km, and graded C.
      </p>

      <h2>How a verdict is reached</h2>
      <p>
        The ratio is our estimate divided by the reported total for the same area and year. Its
        interval combines the sampling noise of the days with a 35% systematic term. A source is
        &quot;higher than reported&quot; only when the whole interval sits above 1.25 times the reported
        figure, and &quot;lower than reported&quot; only when it sits below 0.8. Both need two separate years
        to agree. Anything between is &quot;consistent with reported&quot;. In practice that means a gap
        has to be about 2.5 times before the site flags it.
      </p>
      <p>
        Grade A means no flags and at least 80 clear days. Grade B means one flag or 40 to 79 days.
        Grade C means a cluster or two or more flags.
      </p>

      <h2>How we tested it</h2>
      <p>
        We ran the method on 33 US power plants whose stacks measure NOx every hour, for 2023 and
        2024. Seven of the 66 estimates passed every check. Those seven agreed with the monitors with
        no bias we could detect, and they scatter by about 35%, which is where the systematic term
        comes from. The 13 plants that pass all the isolation checks are on the map as test sites.
      </p>
      <p>
        The test also set a practical floor. No estimate passed when the area&apos;s reported total was
        under 4,000 tonnes a year, and almost none under 6,000. Sources below that stay on the site
        and are labelled &quot;below reliable detection&quot;.
      </p>

      <h2>What this cannot do</h2>
      <ul>
        <li>It sees one moment a day, in clear and windy weather, so it misses the rest of the year.</li>
        <li>It uses one average correction for how the satellite sees NO<sub>2</sub>. This is the largest simplification.</li>
        <li>Wind comes from a 28 km grid at one height. A test of a higher wind level is still running.</li>
        <li>Sources that do not report, and cities or industry in the area, add to the estimate.</li>
        <li>Seven passing estimates fix the uncertainty only loosely.</li>
      </ul>

      <h2>Data</h2>
      <ul>
        <li>NO<sub>2</sub>: Copernicus Sentinel-5P TROPOMI, July 2022 on.</li>
        <li>Wind: ERA5 hourly, ECMWF.</li>
        <li>Reported emissions: EEA Industrial Reporting database.</li>
        <li>US monitors: EPA CAMPD hourly stack monitors, with the 2023 National Emissions Inventory for sources the monitors cannot see.</li>
      </ul>
      <p>
        Every constant, its source and the validation tables are in METHODS.md in the{" "}
        <a className="nav-link" href="https://github.com/BadrWaqas/orbyt">
          project repository
        </a>
        .
      </p>
    </>
  );
}
