import { useEffect } from "react";

import { useFindingDetail, useFindings } from "../data/findings";
import { HomeShareCard, ShareCard } from "./ShareCard";
import "./card.css";

// The hidden route /card/<finding id> (PLAN.md 9.6). It draws the share card at 1200 x 630 and
// nothing else. scripts/make-share-cards.mjs opens it once per finding and photographs it.
// /card/home is the card for the home link. The script waits for data-card-ready on <html>.

/** Tell the script the picture is complete: fonts are in and the plume has decoded. */
function useReadyFlag(ready: boolean) {
  useEffect(() => {
    document.documentElement.dataset.cardReady = "false";
    if (!ready) return;
    let cancelled = false;
    const images = Array.from(document.images);
    // Ask for the two families by name: a font is only fetched once something asks for it, and
    // fonts.ready alone can answer before that has happened.
    const fonts = [
      document.fonts.load('600 24px "Mona Sans Variable"'),
      document.fonts.load('400 24px "Mona Sans Variable"'),
      document.fonts.load('400 24px "Source Serif 4 Variable"'),
    ];
    Promise.all([...fonts, ...images.map((img) => img.decode().catch(() => undefined))])
      .then(() => document.fonts.ready)
      .then(() => {
        if (!cancelled) document.documentElement.dataset.cardReady = "true";
      });
    return () => {
      cancelled = true;
    };
  }, [ready]);
}

function FindingCard({ id }: { id: string }) {
  const list = useFindings();
  const finding = list.status === "ready" ? list.data.findings.find((f) => f.id === id) ?? null : null;
  const needsDetail = finding?.observed ? finding.id : null;
  const detail = useFindingDetail(needsDetail);

  const detailReady = !needsDetail || (detail.status === "ready" && detail.data.id === needsDetail);
  const evidence = detail.status === "ready" && needsDetail ? (detail.data.evidence ?? null) : null;
  useReadyFlag(finding !== null && detailReady);

  if (list.status === "error") return <p style={{ color: "#fff" }}>Could not load the findings.</p>;
  if (list.status === "ready" && !finding) return <p style={{ color: "#fff" }}>No finding called {id}.</p>;
  if (!finding || !detailReady) return null;
  return <ShareCard finding={finding} evidence={evidence} />;
}

export default function CardPage({ id }: { id: string }) {
  if (id === "home") return <HomeCard />;
  return <FindingCard id={id} />;
}

function HomeCard() {
  useReadyFlag(true);
  return <HomeShareCard />;
}
