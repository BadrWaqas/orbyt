import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { markHiddenForCss } from "./app/visibility";
import { cardIdFromPath } from "./share/cardId";
import "./design/index.css";

markHiddenForCss();

// The share card has its own hidden route and loads on its own, so the app never pays for it.
const CardPage = lazy(() => import("./share/CardPage"));
const cardId = cardIdFromPath(window.location.pathname);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {cardId ? (
      <Suspense fallback={null}>
        <CardPage id={cardId} />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);
