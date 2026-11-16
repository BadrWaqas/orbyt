const PREFIX = "/card/";

/** The finding id in a /card/<id> address, or null on every other page. */
export function cardIdFromPath(pathname: string): string | null {
  if (!pathname.startsWith(PREFIX)) return null;
  const id = decodeURIComponent(pathname.slice(PREFIX.length).replace(/\/+$/, ""));
  return id || null;
}
