// next/dynamic for the standalone bundle: a lazy component (the orb is client-only anyway).
import { lazy, Suspense, type ComponentType } from "react";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function dynamic<P extends object>(loader: () => Promise<{ default: ComponentType<P> } | any>) {
  const C = lazy(loader);
  return function Dynamic(props: P) {
    return <Suspense fallback={null}><C {...props} /></Suspense>;
  };
}
