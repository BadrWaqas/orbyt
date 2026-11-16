import raw from "./chapters.json";

// The scroll story (M7.4, PLAN.md 9.5): five chapters, each one screen tall, that fly the same
// globe as the rest of the site. chapters.json holds the words and the camera; this file gives
// them types and fills in the numbers from the data, so no figure in the text is written by hand.

export interface ChapterCamera {
  /** A longitude and latitude, or "showcase" for the first story facility. */
  center: [number, number] | "showcase";
  /** A zoom, or "opening" for the module's opening view, whatever the window size. */
  zoom: number | "opening";
  pitch: number;
  bearing: number;
}

export interface ChapterShow {
  markers: boolean;
  /** The facility whose panel and plume are open, or null for none. */
  facility: "showcase" | null;
  /** The NO2 layer: the annual mean, or the months playing. */
  time: "annual" | "play";
}

export interface Chapter {
  id: string;
  title: string;
  body: string;
  camera: ChapterCamera;
  show: ChapterShow;
}

export const chapters = raw as Chapter[];

/** Numbers the chapters mention, taken from the data at run time. */
export interface ChapterFacts {
  reporters: number;
  year: string;
}

/** The body with its {placeholders} filled in. */
export function chapterBody(chapter: Chapter, facts: ChapterFacts): string {
  return chapter.body.replace(/\{(\w+)\}/g, (_, key: keyof ChapterFacts) => {
    const value = facts[key];
    return typeof value === "number" ? value.toLocaleString("en-IE") : String(value);
  });
}
