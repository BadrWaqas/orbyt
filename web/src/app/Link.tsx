import type { AnchorHTMLAttributes, MouseEvent } from "react";

import { hrefFor, navigate, type View } from "./route";

interface Props extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  to: View;
  /** Runs in place of the plain change of view, for links that start something on the way. */
  onNavigate?: () => void;
}

/**
 * A link to another view. It is a real anchor with a real address, so it can be opened in a new
 * tab or copied. A plain click changes the view without loading the page again.
 */
export function Link({ to, onNavigate, onClick, ...rest }: Props) {
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    if (onNavigate) onNavigate();
    else navigate(to);
  };
  return <a href={hrefFor(to)} onClick={handle} {...rest} />;
}
